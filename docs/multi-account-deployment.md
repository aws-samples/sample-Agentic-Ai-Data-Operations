# Multi-Account Deployment Guide

> Single AWS account is the default for this platform. This guide describes
> the **optional** multi-account topology where the Glue Data Catalog and
> Lake Formation live in one account ("Account A") while Glue jobs, MWAA,
> IAM roles, and S3 data buckets live in another ("Account B"). Skip this
> guide entirely if everything deploys to one account.

## When to use it

- You have a central data-lake account that owns the Glue Data Catalog
  and Lake Formation policies, and one or more consumer accounts that run
  Glue jobs, MWAA, and analytics workloads against that catalog.
- Organizational, regulatory, or blast-radius reasons prevent collapsing
  the two accounts.

## Topology

```
          Account A (Data Lake)                  Account B (Consumer)
   ┌──────────────────────────────────┐   ┌────────────────────────────────┐
   │ Glue Data Catalog                │   │ Glue Jobs (PySpark)            │
   │   landing_db / staging_db /      │◀──┤   pass CatalogId=<A>           │
   │   publish_db                     │   │                                │
   │                                  │   │ MWAA Environment               │
   │ Lake Formation                   │   │   DAG Variable:                │
   │   LF-Tags: PII_*, Sensitivity    │◀──┤   glue_catalog_account_id=<A>  │
   │   grants to B's Glue role        │   │                                │
   │                                  │   │ S3 buckets + KMS keys          │
   │                                  │   │   Jobs write here (read-only   │
   │                                  │   │   from A's data via LF)        │
   │ Optional: S3 source buckets      │───┤ IAM role                       │
   │   (read via LF GetDataAccess)    │   │   trusts B's Glue; assumes A   │
   └──────────────────────────────────┘   └────────────────────────────────┘
                  ▲                                      │
                  │     sts:AssumeRole + ExternalId      │
                  └──────────────────────────────────────┘
```

## Scope today

**Supported**

- Read-only access from Account B jobs to Account A Glue databases,
  tables, and Lake Formation-registered S3 data.
- Column-level security via Lake Formation LF-Tags in Account A.
- Metadata discovery (Glue `GetTable`, `GetDatabase`) from Account B to
  Account A catalog.

**Not supported (yet)**

- **Write-back** from Account B Glue jobs into Account A's catalog. Write
  operations require AWS Resource Access Manager (RAM) to share the
  database + `lakeformation:RegisterResource` in Account B. Not automated
  by this repo — if you need it, set it up manually and file an issue.
- **Cross-account KMS** key sharing. Jobs in Account B must use their own
  KMS keys for all write paths. Reads from Account A data use Lake
  Formation's `GetDataAccess` vended credentials, which carry Account A's
  KMS decrypt authority scoped to the grantee role.
- **Cross-region** catalog reads. Both accounts must be in the same AWS
  region.

## Pre-requisites you set up manually in AWS

The agents in this repo generate the *consumer-side* artifacts under the
assumption that the cross-account trust + grants already exist. Create
these first.

### 1. Account A — create a catalog-reader role

IAM role `adop-catalog-reader` in Account A with:

**Permissions policy** (attach this policy):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetDatabases",
        "glue:GetTable",
        "glue:GetTables",
        "glue:GetPartition",
        "glue:GetPartitions",
        "glue:SearchTables",
        "lakeformation:GetDataAccess"
      ],
      "Resource": "*"
    }
  ]
}
```

**Trust policy** (who can assume this role):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::222222222222:role/AWSGlueServiceRole-ADOP"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "adop-b-to-a"
        }
      }
    }
  ]
}
```

Replace `222222222222` with your Account B, and pick any value for
`sts:ExternalId` (then use the same value in the workload config).

### 2. Account A — Lake Formation grants

As a Lake Formation administrator in Account A, grant the reader role
LF-Tag based access:

```bash
# Example: grant SELECT + DESCRIBE on everything tagged Sensitivity in (NONE, LOW, MEDIUM)
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::111111111111:role/adop-catalog-reader \
  --resource '{"LFTagPolicy": {
      "CatalogId": "111111111111",
      "ResourceType": "DATABASE",
      "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["NONE", "LOW", "MEDIUM"]}]
  }}' \
  --permissions "DESCRIBE"

aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::111111111111:role/adop-catalog-reader \
  --resource '{"LFTagPolicy": {
      "CatalogId": "111111111111",
      "ResourceType": "TABLE",
      "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["NONE", "LOW", "MEDIUM"]}]
  }}' \
  --permissions "SELECT" "DESCRIBE"
```

### 3. Account B — let the Glue service role assume Account A's role

Attach an inline policy to `AWSGlueServiceRole-ADOP` in Account B:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::111111111111:role/adop-catalog-reader"
    }
  ]
}
```

## Telling the platform to use multi-account mode

Three prompts ask the single-vs-multi question. Any of the three can
seed the topology; downstream prompts will read the same value.

| Prompt | When you're asked |
|---|---|
| `prompts/environment-setup-agent/01-setup-aws-infrastructure.md` | Once, when bootstrapping the repo's AWS platform. |
| `prompts/data-onboarding-agent/03-onboard-build-pipeline.md` | Per workload in the Phase 1 discovery block. |
| `prompts/devops-agent/iac-generator.md` | When generating IaC, as a Phase 0 question. |

All three persist into `workloads/{name}/config/deployment.yaml` under an
`account_topology:` block matching `shared/templates/account_topology.yaml`.

Expected shape when `mode == "multi"`:

```yaml
account_topology:
  mode: multi
  jobs_account_id: "222222222222"
  catalog_account_id: "111111111111"
  catalog_assume_role_arn: "arn:aws:iam::111111111111:role/adop-catalog-reader"
  catalog_external_id: "adop-b-to-a"
  region: us-east-1
```

## What the agents generate differently in multi-account mode

| Artifact | Single mode | Multi mode |
|---|---|---|
| Terraform / CDK | One `aws` provider | Two providers: default (B) + `aws.catalog` alias with `assume_role { role_arn = catalog_assume_role_arn }` |
| Glue table / LF references in IaC | Implicit caller account | `catalog_id = var.catalog_account_id` on `aws_glue_catalog_table` and `aws_lakeformation_*` resources |
| PySpark (`scripts/transform/*.py`) | No CatalogId config | `spark.conf.set("spark.sql.catalog.glue_catalog.glue.id", args["catalog_account_id"])` added to job setup |
| MWAA DAG | `aws_account_id` Variable | `glue_catalog_account_id` Variable read and threaded to every GlueJobOperator as `--catalog_account_id` |
| `deploy_to_aws.py` | `--account-id` (single) | `--catalog-account-id` + `--jobs-account-id` |
| `shared/metadata/glue_fetcher.GlueFetcher` | `catalog_id=None` (uses caller) | `catalog_id=<A>` passed by the Metadata Agent at Phase 3 |
| Cedar policies | Unchanged (account-neutral by design) | Unchanged |

## Post-deploy smoke test

After applying the generated IaC and uploading the DAG to MWAA, confirm
the cross-account path works:

```bash
# From Account B, assume A's reader role and list databases in A
aws sts assume-role \
  --role-arn arn:aws:iam::111111111111:role/adop-catalog-reader \
  --role-session-name smoke-test \
  --external-id adop-b-to-a \
  > /tmp/creds.json

AWS_ACCESS_KEY_ID=$(jq -r .Credentials.AccessKeyId /tmp/creds.json) \
AWS_SECRET_ACCESS_KEY=$(jq -r .Credentials.SecretAccessKey /tmp/creds.json) \
AWS_SESSION_TOKEN=$(jq -r .Credentials.SessionToken /tmp/creds.json) \
aws glue get-databases --catalog-id 111111111111
```

You should see the databases in Account A. If you get
`AccessDeniedException`, re-check (in order): the trust policy's
ExternalId, the LF grant to the reader role, and the Glue permissions on
the reader role.

## Known limits recap

- Read-only from A → B. Write-back to A requires RAM share — not automated.
- Same-region only.
- Cross-account KMS is not shared — write KMS in B, read KMS in A (handled by LF).
- Existing workloads (`financial_portfolios`, `healthcare_patients`,
  `claims`, etc.) are **not** retrofitted. Only NEW workloads generated
  after this guide shipped pick up the switch, or you explicitly
  regenerate an existing one.
