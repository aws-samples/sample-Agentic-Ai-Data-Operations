import * as cdk from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as neptune from "aws-cdk-lib/aws-neptune";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as ssm from "aws-cdk-lib/aws-ssm";
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as athena from "aws-cdk-lib/aws-athena";
import * as logs from "aws-cdk-lib/aws-logs";
import * as path from "path";
import { Construct } from "constructs";

interface Props extends cdk.StackProps {
  configBucket: s3.Bucket;
  dataLakeBucketName: string; // existing bucket created outside this stack
  ontopEcrRepoName: string; // ECR repo holding the CodeBuild-built Ontop image
  ontopImageTag?: string; // default "latest"
  /**
   * KMS key ARN protecting the data-lake bucket. Required when the bucket is
   * encrypted with a customer-managed key — Ontop must be able to encrypt
   * Athena query results with it. Pass via stack context or cdk.json:
   *   { "context": { "dataLakeKmsKeyArn": "arn:aws:kms:...:key/..." } }
   * Look up your account's actual key with:
   *   aws s3api get-bucket-encryption --bucket <data-lake-bucket>
   */
  dataLakeKmsKeyArn?: string;
}

export class SparqlVirtualizationStack extends cdk.Stack {
  public readonly neptuneEndpoint: string;
  public readonly ontopEndpoint: string;
  public readonly obqcFunction: lambda.Function;

  constructor(scope: Construct, id: string, props: Props) {
    super(scope, id, props);

    const { configBucket, dataLakeBucketName, ontopEcrRepoName, dataLakeKmsKeyArn } = props;
    const ontopImageTag = props.ontopImageTag ?? "latest";

    // Reference existing data lake bucket (Bronze + Silver tables live there)
    const dataLakeBucket = s3.Bucket.fromBucketName(
      this,
      "DataLakeBucket",
      dataLakeBucketName
    );

    // -----------------------------
    // 1. VPC
    // -----------------------------
    const vpc = new ec2.Vpc(this, "Vpc", {
      maxAzs: 2,
      natGateways: 1,
      subnetConfiguration: [
        { name: "Public", subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        {
          name: "Private",
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
          cidrMask: 24,
        },
      ],
    });
    vpc.addGatewayEndpoint("S3Endpoint", {
      service: ec2.GatewayVpcEndpointAwsService.S3,
    });

    // -----------------------------
    // 2. Security Groups
    // -----------------------------
    const neptuneSg = new ec2.SecurityGroup(this, "NeptuneSg", {
      vpc,
      description: "Neptune DB - inbound 8182 from OBQC + Loader",
      allowAllOutbound: false,
    });
    const ontopSg = new ec2.SecurityGroup(this, "OntopSg", {
      vpc,
      description: "Ontop VKG - inbound 8080, outbound for Athena via NAT",
      allowAllOutbound: true,
    });
    const lambdaSg = new ec2.SecurityGroup(this, "LambdaSg", {
      vpc,
      description: "OBQC + Neptune Loader Lambda - egress to Neptune 8182",
      allowAllOutbound: false,
    });
    lambdaSg.addEgressRule(neptuneSg, ec2.Port.tcp(8182), "Lambda to Neptune");
    neptuneSg.addIngressRule(lambdaSg, ec2.Port.tcp(8182), "Neptune from Lambda");
    ontopSg.addIngressRule(
      ec2.Peer.ipv4(vpc.vpcCidrBlock),
      ec2.Port.tcp(8080),
      "Ontop SPARQL endpoint from VPC"
    );

    // -----------------------------
    // 3. Neptune cluster (single instance, dev sizing)
    // -----------------------------
    const subnetGroup = new neptune.CfnDBSubnetGroup(this, "NeptuneSubnetGroup", {
      dbSubnetGroupDescription: "Private subnets for Neptune",
      subnetIds: vpc.selectSubnets({
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      }).subnetIds,
    });

    const neptuneCluster = new neptune.CfnDBCluster(this, "NeptuneCluster", {
      dbClusterIdentifier: "adop-semantic-ontology",
      engineVersion: "1.3.2.1",
      dbSubnetGroupName: subnetGroup.ref,
      vpcSecurityGroupIds: [neptuneSg.securityGroupId],
      iamAuthEnabled: true,
      storageEncrypted: true,
      deletionProtection: false,
    });
    neptuneCluster.addDependency(subnetGroup);

    const neptuneInstance = new neptune.CfnDBInstance(this, "NeptuneInstance", {
      dbInstanceClass: "db.r6g.large",
      dbClusterIdentifier: neptuneCluster.ref,
      availabilityZone: vpc.availabilityZones[0],
    });
    neptuneInstance.addDependency(neptuneCluster);

    // Neptune bulk loader role: read ontology from config bucket
    const neptuneBulkRole = new iam.Role(this, "NeptuneBulkRole", {
      assumedBy: new iam.ServicePrincipal("rds.amazonaws.com"),
    });
    configBucket.grantRead(neptuneBulkRole, "ontology/*");
    neptuneCluster.addPropertyOverride("AssociatedRoles", [
      { RoleArn: neptuneBulkRole.roleArn },
    ]);

    const neptuneSparqlEndpoint = `https://${neptuneCluster.attrEndpoint}:8182/sparql`;
    this.neptuneEndpoint = neptuneSparqlEndpoint;

    // -----------------------------
    // 4. Athena workgroup
    // -----------------------------
    const athenaResultsPrefix = "athena-results";
    const athenaWg = new athena.CfnWorkGroup(this, "AthenaWg", {
      name: "adop-semantic-ontop",
      state: "ENABLED",
      workGroupConfiguration: {
        resultConfiguration: {
          outputLocation: `s3://${dataLakeBucket.bucketName}/${athenaResultsPrefix}/`,
        },
        enforceWorkGroupConfiguration: true,
        publishCloudWatchMetricsEnabled: true,
      },
    });

    // -----------------------------
    // 5. Ontop ECS Fargate
    // -----------------------------
    const cluster = new ecs.Cluster(this, "Cluster", { vpc });

    const ontopTaskRole = new iam.Role(this, "OntopTaskRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      description: "Ontop task: Athena, Glue (per-workload DB pattern), S3, KMS",
    });

    ontopTaskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:GetWorkGroup",
          "athena:GetQueryResultsStream",
        ],
        resources: [
          `arn:aws:athena:${this.region}:${this.account}:workgroup/${athenaWg.name}`,
        ],
      })
    );
    // Wildcard Glue scope on per-workload *_db pattern
    ontopTaskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetDatabase",
          "glue:GetDatabases",
          "glue:GetPartitions",
          "glue:GetPartition",
        ],
        resources: [
          `arn:aws:glue:${this.region}:${this.account}:catalog`,
          `arn:aws:glue:${this.region}:${this.account}:database/*_db`,
          `arn:aws:glue:${this.region}:${this.account}:table/*_db/*`,
        ],
      })
    );
    ontopTaskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["lakeformation:GetDataAccess"],
        resources: ["*"],
      })
    );
    dataLakeBucket.grantRead(ontopTaskRole);
    dataLakeBucket.grantWrite(ontopTaskRole, "athena-results/*");
    configBucket.grantRead(ontopTaskRole);

    // Data lake bucket is often encrypted with a customer-managed KMS key
    // (managed by the data onboarding agent's Phase 5). Ontop must be able to
    // use that key to write Athena query results. Look up the bucket's actual
    // key (`aws s3api get-bucket-encryption --bucket <data-lake-bucket>`) and
    // pass via the `dataLakeKmsKeyArn` prop. If the bucket uses SSE-S3 (AWS-
    // managed key), this prop is unnecessary.
    if (dataLakeKmsKeyArn) {
      ontopTaskRole.addToPolicy(
        new iam.PolicyStatement({
          actions: [
            "kms:Decrypt",
            "kms:Encrypt",
            "kms:GenerateDataKey",
            "kms:DescribeKey",
          ],
          resources: [dataLakeKmsKeyArn],
        })
      );
    }

    const ontopTaskDef = new ecs.FargateTaskDefinition(this, "OntopTaskDef", {
      cpu: 1024,
      memoryLimitMiB: 2048,
      taskRole: ontopTaskRole,
    });

    // Reference Ontop image built and pushed by CodeBuild (no local Docker required)
    const ontopRepo = ecr.Repository.fromRepositoryName(
      this,
      "OntopRepo",
      ontopEcrRepoName
    );

    const ontopContainer = ontopTaskDef.addContainer("ontop", {
      image: ecs.ContainerImage.fromEcrRepository(ontopRepo, ontopImageTag),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: "ontop",
        logRetention: logs.RetentionDays.ONE_WEEK,
      }),
      environment: {
        CONFIG_BUCKET: configBucket.bucketName,
        ONTOLOGY_S3_KEY: "ontology/ontology.ttl",
        R2RML_S3_KEY: "ontology/r2rml-mappings.ttl",
        ONTOP_ONTOLOGY_FILE: "/opt/ontop/input/ontology.ttl",
        ONTOP_MAPPING_FILE: "/opt/ontop/input/r2rml-mappings.ttl",
        JDBC_URL: `jdbc:awsathena://AwsRegion=${this.region};S3OutputLocation=s3://${dataLakeBucket.bucketName}/${athenaResultsPrefix}/;Catalog=AwsDataCatalog;Workgroup=${athenaWg.name};AwsCredentialsProviderClass=com.simba.athena.amazonaws.auth.DefaultAWSCredentialsProviderChain;`,
      },
    });
    ontopContainer.addPortMappings({ containerPort: 8080 });

    const ontopService = new ecs.FargateService(this, "OntopService", {
      cluster,
      taskDefinition: ontopTaskDef,
      desiredCount: 1,
      assignPublicIp: false,
      securityGroups: [ontopSg],
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      circuitBreaker: { enable: false },
      minHealthyPercent: 0,
      healthCheckGracePeriod: cdk.Duration.seconds(180),
    });

    const ontopAlb = new elbv2.ApplicationLoadBalancer(this, "OntopAlb", {
      vpc,
      internetFacing: false,
      securityGroup: ontopSg,
    });
    const ontopListener = ontopAlb.addListener("OntopListener", {
      port: 8080,
      protocol: elbv2.ApplicationProtocol.HTTP,
    });
    ontopListener.addTargets("OntopTarget", {
      port: 8080,
      targets: [ontopService],
      healthCheck: {
        path: "/",
        port: "8080",
        interval: cdk.Duration.seconds(30),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 5,
      },
    });

    const ontopSparqlEndpoint = `http://${ontopAlb.loadBalancerDnsName}:8080/sparql`;
    this.ontopEndpoint = ontopSparqlEndpoint;

    // -----------------------------
    // 6. OBQC Lambda
    // -----------------------------
    const obqcRole = new iam.Role(this, "ObqcRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaVPCAccessExecutionRole"
        ),
      ],
    });
    obqcRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["neptune-db:ReadDataViaQuery"],
        resources: [
          `arn:aws:neptune-db:${this.region}:${this.account}:${neptuneCluster.attrClusterResourceId}/*`,
        ],
      })
    );

    this.obqcFunction = new lambda.Function(this, "ObqcFn", {
      functionName: "adop-semantic-obqc",
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "handler.handler",
      code: lambda.Code.fromAsset(
        path.join(__dirname, "..", "..", "lambdas", "obqc")
      ),
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      role: obqcRole,
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [lambdaSg],
      environment: { NEPTUNE_SPARQL_ENDPOINT: neptuneSparqlEndpoint },
    });

    // -----------------------------
    // 7. Neptune Loader Lambda
    // -----------------------------
    const loaderRole = new iam.Role(this, "LoaderRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaVPCAccessExecutionRole"
        ),
      ],
    });
    loaderRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["neptune-db:*"],
        resources: [
          `arn:aws:neptune-db:${this.region}:${this.account}:${neptuneCluster.attrClusterResourceId}/*`,
        ],
      })
    );
    configBucket.grantRead(loaderRole);

    const loaderFn = new lambda.Function(this, "LoaderFn", {
      functionName: "adop-semantic-neptune-loader",
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "handler.handler",
      code: lambda.Code.fromAsset(
        path.join(__dirname, "..", "..", "lambdas", "neptune_loader")
      ),
      timeout: cdk.Duration.seconds(120),
      memorySize: 512,
      role: loaderRole,
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [lambdaSg],
      environment: {
        NEPTUNE_SPARQL_ENDPOINT: neptuneSparqlEndpoint,
        NEPTUNE_LOADER_S3_ROLE_ARN: neptuneBulkRole.roleArn,
        CONFIG_BUCKET: configBucket.bucketName,
      },
    });

    // -----------------------------
    // 8. SSM Params
    // -----------------------------
    new ssm.StringParameter(this, "NeptuneEpParam", {
      parameterName: "/adop-semantic/neptune-sparql-endpoint",
      stringValue: neptuneSparqlEndpoint,
    });
    new ssm.StringParameter(this, "OntopEpParam", {
      parameterName: "/adop-semantic/ontop-sparql-endpoint",
      stringValue: ontopSparqlEndpoint,
    });
    new ssm.StringParameter(this, "ObqcFnParam", {
      parameterName: "/adop-semantic/obqc-function-name",
      stringValue: this.obqcFunction.functionName,
    });
    new ssm.StringParameter(this, "LoaderFnParam", {
      parameterName: "/adop-semantic/neptune-loader-function-name",
      stringValue: loaderFn.functionName,
    });
    new ssm.StringParameter(this, "ConfigBucketParam", {
      parameterName: "/adop-semantic/config-bucket",
      stringValue: configBucket.bucketName,
    });

    // -----------------------------
    // 9. Outputs
    // -----------------------------
    new cdk.CfnOutput(this, "NeptuneSparqlEndpoint", { value: neptuneSparqlEndpoint });
    new cdk.CfnOutput(this, "OntopSparqlEndpoint", { value: ontopSparqlEndpoint });
    new cdk.CfnOutput(this, "ObqcFunctionArn", { value: this.obqcFunction.functionArn });
    new cdk.CfnOutput(this, "LoaderFunctionName", { value: loaderFn.functionName });
  }
}
