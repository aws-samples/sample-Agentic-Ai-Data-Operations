import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as kms from "aws-cdk-lib/aws-kms";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import * as codebuild from "aws-cdk-lib/aws-codebuild";
import { Construct } from "constructs";

export class StorageStack extends cdk.Stack {
  public readonly configBucket: s3.Bucket;
  public readonly kmsKey: kms.Key;
  public readonly ontopRepo: ecr.Repository;
  public readonly ontopBuildProject: codebuild.Project;

  constructor(scope: Construct, id: string, props: cdk.StackProps) {
    super(scope, id, props);

    this.kmsKey = new kms.Key(this, "AdopSemanticKey", {
      description: "KMS for ADOP semantic layer (S3, Neptune, OpenSearch)",
      enableKeyRotation: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    this.kmsKey.addAlias("alias/adop-semantic-dev");

    this.configBucket = new s3.Bucket(this, "ConfigBucket", {
      bucketName: `adop-semantic-${this.account}-${this.region}`,
      versioned: true,
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: this.kmsKey,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // ECR repo for Ontop image (built via CodeBuild, no local Docker)
    this.ontopRepo = new ecr.Repository(this, "OntopRepo", {
      repositoryName: "adop-semantic-ontop",
      imageScanOnPush: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      emptyOnDelete: true,
    });

    // CodeBuild project: zip → S3 → builds Docker image → pushes to ECR
    const buildRole = new iam.Role(this, "OntopBuildRole", {
      assumedBy: new iam.ServicePrincipal("codebuild.amazonaws.com"),
    });
    this.ontopRepo.grantPullPush(buildRole);
    buildRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["ecr:GetAuthorizationToken"],
        resources: ["*"],
      })
    );
    this.configBucket.grantRead(buildRole);
    buildRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        resources: ["*"],
      })
    );

    this.ontopBuildProject = new codebuild.Project(this, "OntopBuild", {
      projectName: "adop-semantic-ontop-build",
      role: buildRole,
      source: codebuild.Source.s3({
        bucket: this.configBucket,
        path: "codebuild/ontop-source.zip",
      }),
      environment: {
        buildImage: codebuild.LinuxBuildImage.AMAZON_LINUX_2_5,
        privileged: true, // required for Docker daemon
        computeType: codebuild.ComputeType.SMALL,
      },
      environmentVariables: {
        AWS_DEFAULT_REGION: { value: this.region },
        AWS_ACCOUNT_ID: { value: this.account },
        ECR_REPO: { value: this.ontopRepo.repositoryUri },
      },
      buildSpec: codebuild.BuildSpec.fromObject({
        version: "0.2",
        phases: {
          pre_build: {
            commands: [
              "echo Logging in to ECR...",
              "aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com",
            ],
          },
          build: {
            commands: [
              "cd ontop_config",
              "echo Building Ontop image...",
              "docker build -t $ECR_REPO:latest .",
            ],
          },
          post_build: {
            commands: [
              "echo Pushing Ontop image...",
              "docker push $ECR_REPO:latest",
            ],
          },
        },
      }),
    });

    new cdk.CfnOutput(this, "ConfigBucketName", { value: this.configBucket.bucketName });
    new cdk.CfnOutput(this, "KmsKeyArn", { value: this.kmsKey.keyArn });
    new cdk.CfnOutput(this, "OntopRepoUri", { value: this.ontopRepo.repositoryUri });
    new cdk.CfnOutput(this, "OntopBuildProjectName", { value: this.ontopBuildProject.projectName });
  }
}
