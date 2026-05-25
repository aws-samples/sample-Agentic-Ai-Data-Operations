#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { StorageStack } from "../lib/storage-stack";
import { OpenSearchStack } from "../lib/opensearch-stack";
import { SparqlVirtualizationStack } from "../lib/sparql-virtualization-stack";

const app = new cdk.App();

const account = process.env.CDK_DEFAULT_ACCOUNT;
const region = process.env.CDK_DEFAULT_REGION || "us-west-2";
const env = { account, region };

// Read context values (set in cdk.json or via `cdk deploy -c key=value`).
// dataLakeBucketName: the existing data-lake bucket name (Phase 5 default
//   pattern is `fip-datalake-{account}-{region}`; override per environment).
// dataLakeKmsKeyArn: the customer-managed KMS key protecting the data-lake
//   bucket. Required when the bucket uses SSE-KMS with a non-semantic-layer
//   key. Look up via `aws s3api get-bucket-encryption --bucket <bucket>`.
const dataLakeBucketName =
  (app.node.tryGetContext("dataLakeBucketName") as string | undefined) ??
  `fip-datalake-${account}-${region}`;
const dataLakeKmsKeyArn = app.node.tryGetContext("dataLakeKmsKeyArn") as
  | string
  | undefined;

// Storage: S3 config bucket + KMS key + ECR repo + CodeBuild project (Ontop image)
const storage = new StorageStack(app, "AdopSemanticLayerStorage", { env });

// OpenSearch Serverless: ontology slice index
const opensearch = new OpenSearchStack(app, "AdopSemanticLayerOpenSearch", { env });

// VPC + Neptune + Ontop ECS + Lambdas (consumes ECR image built by CodeBuild)
const sparql = new SparqlVirtualizationStack(app, "AdopSemanticLayerSparql", {
  env,
  configBucket: storage.configBucket,
  dataLakeBucketName,
  dataLakeKmsKeyArn,
  ontopEcrRepoName: storage.ontopRepo.repositoryName,
  ontopImageTag: "latest",
});

sparql.addDependency(storage);

app.synth();
