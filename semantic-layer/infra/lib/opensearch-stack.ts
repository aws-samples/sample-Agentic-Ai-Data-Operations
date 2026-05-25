import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as oss from "aws-cdk-lib/aws-opensearchserverless";
import { Construct } from "constructs";

export class OpenSearchStack extends cdk.Stack {
  public readonly collectionName: string;
  public readonly collectionEndpoint: string;
  public readonly collectionArn: string;

  constructor(scope: Construct, id: string, props: cdk.StackProps) {
    super(scope, id, props);

    this.collectionName = "adop-semantic-slices";

    // Encryption policy (required before collection)
    const encPolicy = new oss.CfnSecurityPolicy(this, "EncPolicy", {
      name: "adop-semantic-enc",
      type: "encryption",
      policy: JSON.stringify({
        Rules: [
          {
            ResourceType: "collection",
            Resource: [`collection/${this.collectionName}`],
          },
        ],
        AWSOwnedKey: true,
      }),
    });

    // Network policy: public access (acceptable for dev; tighten with VPC endpoint for prod)
    const netPolicy = new oss.CfnSecurityPolicy(this, "NetPolicy", {
      name: "adop-semantic-net",
      type: "network",
      policy: JSON.stringify([
        {
          Rules: [
            {
              ResourceType: "collection",
              Resource: [`collection/${this.collectionName}`],
            },
            {
              ResourceType: "dashboard",
              Resource: [`collection/${this.collectionName}`],
            },
          ],
          AllowFromPublic: true,
        },
      ]),
    });

    // Collection (vectorsearch type)
    const collection = new oss.CfnCollection(this, "Collection", {
      name: this.collectionName,
      type: "VECTORSEARCH",
      description: "ADOP ontology-slice embeddings for NL-to-class retrieval",
    });
    collection.addDependency(encPolicy);
    collection.addDependency(netPolicy);

    // Data access policy: caller (Admin) + future agent role get full data access
    const dataAccess = new oss.CfnAccessPolicy(this, "DataAccess", {
      name: "adop-semantic-access",
      type: "data",
      policy: JSON.stringify([
        {
          Rules: [
            {
              ResourceType: "collection",
              Resource: [`collection/${this.collectionName}`],
              Permission: ["aoss:*"],
            },
            {
              ResourceType: "index",
              Resource: [`index/${this.collectionName}/*`],
              Permission: ["aoss:*"],
            },
          ],
          Principal: [
            `arn:aws:iam::${this.account}:role/Admin`,
            `arn:aws:iam::${this.account}:root`,
          ],
        },
      ]),
    });
    dataAccess.addDependency(collection);

    this.collectionEndpoint = collection.attrCollectionEndpoint;
    this.collectionArn = collection.attrArn;

    new cdk.CfnOutput(this, "CollectionName", { value: this.collectionName });
    new cdk.CfnOutput(this, "CollectionEndpoint", { value: this.collectionEndpoint });
    new cdk.CfnOutput(this, "CollectionArn", { value: this.collectionArn });
  }
}
