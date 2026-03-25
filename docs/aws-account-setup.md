# AWS Account Setup: Prerequisites for End-to-End Pipeline

This document covers every AWS prerequisite so the Landing -> Staging -> Publish pipeline runs without interruption.

> **Security**: All examples use placeholders (`${PROJECT}`, `${AWS_ACCOUNT_ID}`, `${REGION}`). Never commit real account IDs, bucket names, or key ARNs to source control.

---

## 1. IAM Roles & Policies

### 1a. Glue Service Role

Create a role that Glue jobs, crawlers, and Data Quality use to access S3, KMS, and CloudWatch.

```bash
aws iam create-role \
  --role-name ${PROJECT}-glue-service-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": { "Service": "glue.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }]
  }'
```

Attach the AWS-managed Glue policy:

```bash
aws iam attach-role-policy \
  --role-name ${PROJECT}-glue-service-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole
```

Attach a custom policy for S3 zone access and KMS:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3ZoneAccess",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::${PROJECT}-landing",
        "arn:aws:s3:::${PROJECT}-landing/*",
        "arn:aws:s3:::${PROJECT}-staging",
        "arn:aws:s3:::${PROJECT}-staging/*",
        "arn:aws:s3:::${PROJECT}-publish",
        "arn:aws:s3:::${PROJECT}-publish/*"
      ]
    },
    {
      "Sid": "KMSAccess",
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt",
        "kms:Encrypt",
        "kms:GenerateDataKey",
        "kms:DescribeKey",
        "kms:ReEncryptFrom",
        "kms:ReEncryptTo"
      ],
      "Resource": [
        "arn:aws:kms:${REGION}:${AWS_ACCOUNT_ID}:key/*"
      ],
      "Condition": {
        "ForAnyValue:StringEquals": {
          "kms:ResourceAliases": [
            "alias/landing-data-key",
            "alias/staging-data-key",
            "alias/publish-data-key",
            "alias/catalog-metadata-key"
          ]
        }
      }
    },
    {
      "Sid": "GlueCatalogAccess",
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetTable",
        "glue:GetPartitions",
        "glue:CreateTable",
        "glue:UpdateTable",
        "glue:BatchCreatePartition"
      ],
      "Resource": [
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:catalog",
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:database/landing_db",
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:database/staging_db",
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:database/publish_db",
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:table/landing_db/*",
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:table/staging_db/*",
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:table/publish_db/*"
      ]
    }
  ]
}
```

Save the above as `glue-s3-kms-policy.json` and attach:

```bash
aws iam put-role-policy \
  --role-name ${PROJECT}-glue-service-role \
  --policy-name ${PROJECT}-glue-s3-kms-access \
  --policy-document file://glue-s3-kms-policy.json
```

### 1b. Athena Execution Role

Athena needs read access to all zone buckets plus a query results bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AthenaQueryResults",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::${PROJECT}-athena-results",
        "arn:aws:s3:::${PROJECT}-athena-results/*"
      ]
    },
    {
      "Sid": "ReadZoneBuckets",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::${PROJECT}-landing",
        "arn:aws:s3:::${PROJECT}-landing/*",
        "arn:aws:s3:::${PROJECT}-staging",
        "arn:aws:s3:::${PROJECT}-staging/*",
        "arn:aws:s3:::${PROJECT}-publish",
        "arn:aws:s3:::${PROJECT}-publish/*"
      ]
    },
    {
      "Sid": "GlueCatalogRead",
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetTable",
        "glue:GetPartitions"
      ],
      "Resource": [
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:catalog",
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:database/*",
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:table/*/*"
      ]
    },
    {
      "Sid": "KMSDecrypt",
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:GenerateDataKey"
      ],
      "Resource": [
        "arn:aws:kms:${REGION}:${AWS_ACCOUNT_ID}:key/*"
      ],
      "Condition": {
        "ForAnyValue:StringEquals": {
          "kms:ResourceAliases": [
            "alias/landing-data-key",
            "alias/staging-data-key",
            "alias/publish-data-key"
          ]
        }
      }
    }
  ]
}
```

### 1c. QuickSight Service Role

QuickSight needs access to Athena and the Publish zone bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AthenaAccess",
      "Effect": "Allow",
      "Action": [
        "athena:StartQueryExecution",
        "athena:GetQueryExecution",
        "athena:GetQueryResults",
        "athena:StopQueryExecution"
      ],
      "Resource": "arn:aws:athena:${REGION}:${AWS_ACCOUNT_ID}:workgroup/primary"
    },
    {
      "Sid": "PublishBucketRead",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::${PROJECT}-publish",
        "arn:aws:s3:::${PROJECT}-publish/*"
      ]
    },
    {
      "Sid": "QueryResultsBucket",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::${PROJECT}-athena-results",
        "arn:aws:s3:::${PROJECT}-athena-results/*"
      ]
    },
    {
      "Sid": "GlueCatalogRead",
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetTable",
        "glue:GetPartitions"
      ],
      "Resource": [
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:catalog",
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:database/publish_db",
        "arn:aws:glue:${REGION}:${AWS_ACCOUNT_ID}:table/publish_db/*"
      ]
    },
    {
      "Sid": "KMSDecryptPublish",
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:${REGION}:${AWS_ACCOUNT_ID}:key/*",
      "Condition": {
        "ForAnyValue:StringEquals": {
          "kms:ResourceAliases": ["alias/publish-data-key"]
        }
      }
    }
  ]
}
```

---

## 2. S3 Buckets

Create three zone buckets with SSE-KMS default encryption. Each bucket uses the KMS key for its zone.

### 2a. Landing Bucket

```bash
aws s3api create-bucket \
  --bucket ${PROJECT}-landing \
  --region ${REGION} \
  --create-bucket-configuration LocationConstraint=${REGION}

aws s3api put-bucket-encryption \
  --bucket ${PROJECT}-landing \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "alias/landing-data-key"
      },
      "BucketKeyEnabled": true
    }]
  }'
```

### 2b. Staging Bucket

```bash
aws s3api create-bucket \
  --bucket ${PROJECT}-staging \
  --region ${REGION} \
  --create-bucket-configuration LocationConstraint=${REGION}

aws s3api put-bucket-encryption \
  --bucket ${PROJECT}-staging \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "alias/staging-data-key"
      },
      "BucketKeyEnabled": true
    }]
  }'
```

### 2c. Publish Bucket

```bash
aws s3api create-bucket \
  --bucket ${PROJECT}-publish \
  --region ${REGION} \
  --create-bucket-configuration LocationConstraint=${REGION}

aws s3api put-bucket-encryption \
  --bucket ${PROJECT}-publish \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "alias/publish-data-key"
      },
      "BucketKeyEnabled": true
    }]
  }'
```

### 2d. Athena Query Results Bucket

```bash
aws s3api create-bucket \
  --bucket ${PROJECT}-athena-results \
  --region ${REGION} \
  --create-bucket-configuration LocationConstraint=${REGION}

aws s3api put-bucket-encryption \
  --bucket ${PROJECT}-athena-results \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "alias/staging-data-key"
      },
      "BucketKeyEnabled": true
    }]
  }'
```

### 2e. Block Public Access (all buckets)

```bash
for BUCKET in ${PROJECT}-landing ${PROJECT}-staging ${PROJECT}-publish ${PROJECT}-athena-results; do
  aws s3api put-public-access-block \
    --bucket ${BUCKET} \
    --public-access-block-configuration \
      BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
done
```

### 2f. Enable Versioning (Landing zone -- immutability)

```bash
aws s3api put-bucket-versioning \
  --bucket ${PROJECT}-landing \
  --versioning-configuration Status=Enabled
```

---

## 3. KMS Keys

Create four customer-managed keys (CMKs), one per zone plus one for catalog metadata.

### 3a. Landing Data Key

```bash
LANDING_KEY_ID=$(aws kms create-key \
  --description "Encryption key for Landing zone data" \
  --key-usage ENCRYPT_DECRYPT \
  --key-spec SYMMETRIC_DEFAULT \
  --query 'KeyMetadata.KeyId' \
  --output text)

aws kms create-alias \
  --alias-name alias/landing-data-key \
  --target-key-id ${LANDING_KEY_ID}
```

### 3b. Staging Data Key

```bash
STAGING_KEY_ID=$(aws kms create-key \
  --description "Encryption key for Staging zone data" \
  --key-usage ENCRYPT_DECRYPT \
  --key-spec SYMMETRIC_DEFAULT \
  --query 'KeyMetadata.KeyId' \
  --output text)

aws kms create-alias \
  --alias-name alias/staging-data-key \
  --target-key-id ${STAGING_KEY_ID}
```

### 3c. Publish Data Key

```bash
PUBLISH_KEY_ID=$(aws kms create-key \
  --description "Encryption key for Publish zone data" \
  --key-usage ENCRYPT_DECRYPT \
  --key-spec SYMMETRIC_DEFAULT \
  --query 'KeyMetadata.KeyId' \
  --output text)

aws kms create-alias \
  --alias-name alias/publish-data-key \
  --target-key-id ${PUBLISH_KEY_ID}
```

### 3d. Catalog Metadata Key

```bash
CATALOG_KEY_ID=$(aws kms create-key \
  --description "Encryption key for Glue/SageMaker Catalog metadata" \
  --key-usage ENCRYPT_DECRYPT \
  --key-spec SYMMETRIC_DEFAULT \
  --query 'KeyMetadata.KeyId' \
  --output text)

aws kms create-alias \
  --alias-name alias/catalog-metadata-key \
  --target-key-id ${CATALOG_KEY_ID}
```

### 3e. Enable Key Rotation (all keys)

```bash
for KEY_ALIAS in alias/landing-data-key alias/staging-data-key alias/publish-data-key alias/catalog-metadata-key; do
  KEY_ID=$(aws kms describe-key --key-id ${KEY_ALIAS} --query 'KeyMetadata.KeyId' --output text)
  aws kms enable-key-rotation --key-id ${KEY_ID}
done
```

---

## 4. Glue Catalog

Create zone databases via Athena. The SQL file `prompts/environment-setup-agent/sql/create_zone_databases.sql` should contain:

```sql
CREATE DATABASE IF NOT EXISTS landing_db
  COMMENT 'Landing zone: raw, immutable data as ingested from source';

CREATE DATABASE IF NOT EXISTS staging_db
  COMMENT 'Staging zone: cleaned, validated, schema-enforced Apache Iceberg tables';

CREATE DATABASE IF NOT EXISTS publish_db
  COMMENT 'Publish zone: curated, business-ready Iceberg tables';
```

Run each statement via Athena CLI:

```bash
# Create the Landing database
aws athena start-query-execution \
  --query-string "CREATE DATABASE IF NOT EXISTS landing_db COMMENT 'Landing zone: raw, immutable data'" \
  --result-configuration OutputLocation=s3://${PROJECT}-athena-results/ddl/ \
  --work-group primary

# Create the Staging database
aws athena start-query-execution \
  --query-string "CREATE DATABASE IF NOT EXISTS staging_db COMMENT 'Staging zone: cleaned, validated Iceberg tables'" \
  --result-configuration OutputLocation=s3://${PROJECT}-athena-results/ddl/ \
  --work-group primary

# Create the Publish database
aws athena start-query-execution \
  --query-string "CREATE DATABASE IF NOT EXISTS publish_db COMMENT 'Publish zone: curated, business-ready Iceberg tables'" \
  --result-configuration OutputLocation=s3://${PROJECT}-athena-results/ddl/ \
  --work-group primary
```

Verify the databases exist:

```bash
aws athena start-query-execution \
  --query-string "SHOW DATABASES" \
  --result-configuration OutputLocation=s3://${PROJECT}-athena-results/ddl/ \
  --work-group primary
```

---

## 5. QuickSight Setup

### 5a. Subscribe to Enterprise Edition

```bash
aws quicksight create-account-subscription \
  --edition ENTERPRISE \
  --authentication-method IAM_AND_QUICKSIGHT \
  --aws-account-id ${AWS_ACCOUNT_ID} \
  --account-name ${PROJECT}-analytics \
  --notification-email ${ADMIN_EMAIL}
```

### 5b. Register an Admin User

```bash
aws quicksight register-user \
  --identity-type IAM \
  --email ${ADMIN_EMAIL} \
  --user-role ADMIN \
  --iam-arn arn:aws:iam::${AWS_ACCOUNT_ID}:user/${ADMIN_IAM_USER} \
  --aws-account-id ${AWS_ACCOUNT_ID} \
  --namespace default
```

### 5c. Create Athena Data Source

```bash
aws quicksight create-data-source \
  --aws-account-id ${AWS_ACCOUNT_ID} \
  --data-source-id ${PROJECT}-athena-source \
  --name "${PROJECT} Athena" \
  --type ATHENA \
  --data-source-parameters '{
    "AthenaParameters": {
      "WorkGroup": "primary"
    }
  }' \
  --permissions '[{
    "Principal": "arn:aws:quicksight:${REGION}:${AWS_ACCOUNT_ID}:user/default/${ADMIN_IAM_USER}",
    "Actions": [
      "quicksight:DescribeDataSource",
      "quicksight:DescribeDataSourcePermissions",
      "quicksight:PassDataSource",
      "quicksight:UpdateDataSource",
      "quicksight:UpdateDataSourcePermissions"
    ]
  }]'
```

### 5d. Purchase SPICE Capacity

```bash
# Check current SPICE capacity
aws quicksight describe-account-settings \
  --aws-account-id ${AWS_ACCOUNT_ID}

# Purchase additional SPICE capacity (in GB)
aws quicksight update-account-settings \
  --aws-account-id ${AWS_ACCOUNT_ID} \
  --default-namespace default
```

> **Note**: SPICE capacity is managed via the QuickSight console. The default allocation is 10 GB per user. For larger datasets, purchase additional capacity through the console or contact AWS support.

### 5e. Create a QuickSight Group for Dashboard Consumers

```bash
aws quicksight create-group \
  --aws-account-id ${AWS_ACCOUNT_ID} \
  --namespace default \
  --group-name ${PROJECT}-viewers \
  --description "Read-only access to ${PROJECT} dashboards"

aws quicksight create-group-membership \
  --aws-account-id ${AWS_ACCOUNT_ID} \
  --namespace default \
  --group-name ${PROJECT}-viewers \
  --member-name ${VIEWER_USER}
```

---

## 6. Airflow Variables

Set these variables in your Airflow environment (MWAA, Composer, or self-hosted). All values are references -- no secrets.

| Variable Name | Example Value | Description |
|---|---|---|
| `kms_key_landing` | `alias/landing-data-key` | KMS alias for Landing zone encryption |
| `kms_key_staging` | `alias/staging-data-key` | KMS alias for Staging zone encryption |
| `kms_key_publish` | `alias/publish-data-key` | KMS alias for Publish zone encryption |
| `kms_key_catalog` | `alias/catalog-metadata-key` | KMS alias for catalog metadata encryption |
| `s3_landing_bucket` | `${PROJECT}-landing` | Landing zone S3 bucket name |
| `s3_staging_bucket` | `${PROJECT}-staging` | Staging zone S3 bucket name |
| `s3_publish_bucket` | `${PROJECT}-publish` | Publish zone S3 bucket name |
| `s3_athena_results` | `${PROJECT}-athena-results` | Athena query results bucket |
| `glue_service_role` | `${PROJECT}-glue-service-role` | IAM role for Glue jobs/crawlers |
| `glue_script_s3_path` | `s3://data-lake-ACCOUNT-REGION/scripts/financial_portfolios` | S3 path to Glue ETL scripts (used in Glue job definitions) |
| `glue_iam_role` | `AWSGlueServiceRole-FinancialPortfolios` | IAM role name for Glue jobs (without ARN prefix) |
| `aws_account_id` | `133661573128` | AWS account ID (used for constructing ARNs and QuickSight calls) |
| `glue_landing_db` | `landing_db` | Glue Catalog database for Landing |
| `glue_staging_db` | `staging_db` | Glue Catalog database for Staging |
| `glue_publish_db` | `publish_db` | Glue Catalog database for Publish |
| `quicksight_account_id` | `${AWS_ACCOUNT_ID}` | AWS account ID for QuickSight API calls |
| `alert_sns_topic` | `arn:aws:sns:${REGION}:${AWS_ACCOUNT_ID}:${PROJECT}-alerts` | SNS topic for pipeline failure alerts |
| `environment` | `dev` | Environment tag (dev/staging/prod) |

Set via CLI (example for MWAA):

```bash
# Using Airflow CLI through MWAA
aws mwaa create-cli-token --name ${MWAA_ENV_NAME} | \
  jq -r '.CliToken' | \
  xargs -I {} curl -s "${MWAA_WEBSERVER_URL}/aws_mwaa/cli" \
    -H "Authorization: Bearer {}" \
    -H "Content-Type: text/plain" \
    -d "variables set s3_landing_bucket ${PROJECT}-landing"
```

Or set all at once via a JSON file:

```json
{
  "kms_key_landing": "alias/landing-data-key",
  "kms_key_staging": "alias/staging-data-key",
  "kms_key_publish": "alias/publish-data-key",
  "kms_key_catalog": "alias/catalog-metadata-key",
  "s3_landing_bucket": "${PROJECT}-landing",
  "s3_staging_bucket": "${PROJECT}-staging",
  "s3_publish_bucket": "${PROJECT}-publish",
  "s3_athena_results": "${PROJECT}-athena-results",
  "glue_service_role": "${PROJECT}-glue-service-role",
  "glue_script_s3_path": "s3://data-lake-ACCOUNT-REGION/scripts/${WORKLOAD}",
  "glue_iam_role": "AWSGlueServiceRole-${WORKLOAD}",
  "aws_account_id": "ACCOUNT_ID",
  "glue_landing_db": "landing_db",
  "glue_staging_db": "staging_db",
  "glue_publish_db": "publish_db",
  "environment": "dev"
}
```

```bash
airflow variables import airflow_variables.json
```

---

## 7. MWAA DAG Deployment

After building and testing your workload locally, deploy the Airflow DAG and its dependencies to MWAA.

### Option A: Automated (recommended)

```bash
python3 workloads/{WORKLOAD}/deploy_to_aws.py \
  --mwaa-bucket={MWAA_S3_BUCKET} \
  --region=us-east-1
```

This uploads the DAG file, shared utilities, workload config, and workload scripts in the correct order.

Use `--dry-run` first to preview what will be uploaded.

### Option B: Manual

```bash
# 1. Upload DAG file (must be at root of dags/ prefix)
aws s3 cp workloads/{WORKLOAD}/dags/{WORKLOAD}_dag.py \
  s3://{MWAA_BUCKET}/{DAGS_PREFIX}/{WORKLOAD}_dag.py

# 2. Upload shared utilities (required by DAG imports)
aws s3 sync shared/utils/ s3://{MWAA_BUCKET}/{DAGS_PREFIX}/shared/utils/ \
  --exclude '__pycache__/*' --exclude '*.pyc'
aws s3 sync shared/logging/ s3://{MWAA_BUCKET}/{DAGS_PREFIX}/shared/logging/ \
  --exclude '__pycache__/*' --exclude '*.pyc'

# 3. Upload __init__.py for import chain
aws s3 cp shared/__init__.py s3://{MWAA_BUCKET}/{DAGS_PREFIX}/shared/__init__.py

# 4. Upload workload config and scripts
aws s3 sync workloads/{WORKLOAD}/config/ \
  s3://{MWAA_BUCKET}/{DAGS_PREFIX}/workloads/{WORKLOAD}/config/
aws s3 sync workloads/{WORKLOAD}/scripts/ \
  s3://{MWAA_BUCKET}/{DAGS_PREFIX}/workloads/{WORKLOAD}/scripts/ \
  --exclude '__pycache__/*' --exclude '*.pyc'
```

### Finding your MWAA bucket and DAGs prefix

```bash
# List MWAA environments
aws mwaa list-environments

# Get bucket and DAGs path
aws mwaa get-environment --name {ENV_NAME} \
  --query 'Environment.{Bucket:SourceBucketArn,DagsPath:DagS3Path}' --output table
```

### Setting Airflow Variables

All `Variable.get()` calls in DAGs **must** have a `default_var` parameter, or the Variable must exist in MWAA before the DAG is uploaded. Without this, the DAG fails to parse and won't appear in the Airflow UI.

```bash
# Set variables via MWAA CLI token
ENV_NAME="your-mwaa-env"
TOKEN=$(aws mwaa create-cli-token --name $ENV_NAME --query CliToken --output text)
WEBSERVER=$(aws mwaa get-environment --name $ENV_NAME --query Environment.WebserverUrl --output text)

for VAR_CMD in \
  "variables set glue_script_s3_path s3://data-lake-ACCOUNT-REGION/scripts/WORKLOAD" \
  "variables set glue_iam_role AWSGlueServiceRole-WORKLOAD" \
  "variables set aws_account_id ACCOUNT_ID"; do
  curl -s "https://$WEBSERVER/aws_mwaa/cli" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: text/plain" \
    -d "$VAR_CMD" | jq -r '.stdout' | base64 -d
done
```

### Verification

```bash
# Check DAG appears (allow ~30 seconds after upload)
curl -s "https://$WEBSERVER/aws_mwaa/cli" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: text/plain" \
  -d "dags list" | jq -r '.stdout' | base64 -d | grep {WORKLOAD}

# Check for import errors
curl -s "https://$WEBSERVER/aws_mwaa/cli" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: text/plain" \
  -d "dags list-import-errors" | jq -r '.stdout' | base64 -d
```

Expected: DAG listed, no import errors.

---

## 8. Post-Deployment Verification

After all deployment steps complete, run this mandatory smoke test. Do NOT consider the deployment complete until all checks pass.

```bash
DATABASE="{DATABASE_NAME}"
WORKLOAD="{WORKLOAD_NAME}"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="data-lake-${ACCOUNT}-us-east-1"

echo "=== 1. Glue Catalog — tables exist ==="
aws glue get-tables --database-name $DATABASE \
  --query 'TableList[].{Name:Name,Cols:StorageDescriptor.Columns|length(@)}' \
  --output table

echo "=== 2. Athena — data queryable ==="
# Run COUNT(*) on each Gold table
for TABLE in $(aws glue get-tables --database-name $DATABASE \
  --query 'TableList[?starts_with(Name,`gold_`)].Name' --output text); do
  echo "  $TABLE:"
  aws athena start-query-execution \
    --query-string "SELECT COUNT(*) FROM ${DATABASE}.${TABLE}" \
    --work-group primary \
    --result-configuration "OutputLocation=s3://${BUCKET}/athena-results/"
done

echo "=== 3. LF-Tags — columns tagged ==="
for TABLE in $(aws glue get-tables --database-name $DATABASE \
  --query 'TableList[].Name' --output text); do
  echo "  $TABLE:"
  aws lakeformation get-resource-lf-tags \
    --resource "{\"Table\":{\"DatabaseName\":\"${DATABASE}\",\"Name\":\"${TABLE}\"}}" \
    --output table 2>/dev/null || echo "    No tags"
done

echo "=== 4. TBAC — role grants ==="
aws lakeformation list-permissions \
  --query 'PrincipalResourcePermissions[].{Principal:Principal.DataLakePrincipalIdentifier,Perms:Permissions}' \
  --output table

echo "=== 5. KMS — encryption active ==="
aws s3api get-bucket-encryption --bucket $BUCKET --output table 2>/dev/null || echo "  No encryption"

echo "=== 6. MWAA — DAG loaded ==="
# (use CLI token method from Step 7)

echo "=== 7. QuickSight — datasets ==="
aws quicksight list-data-sets --aws-account-id $ACCOUNT \
  --query "DataSetSummaries[?contains(Name,'${WORKLOAD}')].{Name:Name,Id:DataSetId}" \
  --output table 2>/dev/null || echo "  QuickSight not configured"

echo "=== 8. CloudTrail — audit events ==="
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventSource,AttributeValue=lakeformation.amazonaws.com \
  --max-results 5 \
  --query 'Events[].{Time:EventTime,Name:EventName}' --output table
```

**Summary table** (present to human after running):

```
POST-DEPLOYMENT VERIFICATION: {WORKLOAD}
──────────────────────────────────────────
Glue Catalog:    {N} tables verified       [PASS/FAIL]
Athena Queries:  {N} tables queryable      [PASS/FAIL]
LF-Tags:         {N} columns tagged        [PASS/FAIL]
TBAC Grants:     {N} roles verified        [PASS/FAIL]
KMS Encryption:  Key active, rotation on   [PASS/FAIL]
MWAA DAG:        Loaded, no import errors  [PASS/FAIL/SKIP]
QuickSight:      {N} datasets accessible   [PASS/FAIL/SKIP]
CloudTrail:      Audit events logged       [PASS/FAIL]
──────────────────────────────────────────
Overall: [ALL PASS / {N} FAILURES]
```

If ANY check fails, investigate before proceeding to production.

---

## 9. Verification Checklist

Run these commands to confirm every prerequisite is in place. All should succeed without errors.

### S3 Buckets

```bash
aws s3api head-bucket --bucket ${PROJECT}-landing
aws s3api head-bucket --bucket ${PROJECT}-staging
aws s3api head-bucket --bucket ${PROJECT}-publish
aws s3api head-bucket --bucket ${PROJECT}-athena-results
```

### S3 Encryption

```bash
aws s3api get-bucket-encryption --bucket ${PROJECT}-landing \
  --query 'ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.KMSMasterKeyID'
# Expected: alias/landing-data-key

aws s3api get-bucket-encryption --bucket ${PROJECT}-staging \
  --query 'ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.KMSMasterKeyID'
# Expected: alias/staging-data-key

aws s3api get-bucket-encryption --bucket ${PROJECT}-publish \
  --query 'ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.KMSMasterKeyID'
# Expected: alias/publish-data-key
```

### KMS Keys

```bash
aws kms describe-key --key-id alias/landing-data-key --query 'KeyMetadata.KeyState'
# Expected: "Enabled"

aws kms describe-key --key-id alias/staging-data-key --query 'KeyMetadata.KeyState'
# Expected: "Enabled"

aws kms describe-key --key-id alias/publish-data-key --query 'KeyMetadata.KeyState'
# Expected: "Enabled"

aws kms describe-key --key-id alias/catalog-metadata-key --query 'KeyMetadata.KeyState'
# Expected: "Enabled"
```

### KMS Key Rotation

```bash
for KEY_ALIAS in alias/landing-data-key alias/staging-data-key alias/publish-data-key alias/catalog-metadata-key; do
  KEY_ID=$(aws kms describe-key --key-id ${KEY_ALIAS} --query 'KeyMetadata.KeyId' --output text)
  echo "${KEY_ALIAS}:"
  aws kms get-key-rotation-status --key-id ${KEY_ID} --query 'KeyRotationEnabled'
done
# Expected: true for all
```

### IAM Roles

```bash
aws iam get-role --role-name ${PROJECT}-glue-service-role --query 'Role.Arn'
# Expected: arn:aws:iam::${AWS_ACCOUNT_ID}:role/${PROJECT}-glue-service-role
```

### Glue Catalog Databases

```bash
aws athena start-query-execution \
  --query-string "SHOW DATABASES" \
  --result-configuration OutputLocation=s3://${PROJECT}-athena-results/ddl/ \
  --work-group primary

# Wait for query to complete, then check results include:
# landing_db, staging_db, publish_db
```

Or directly via Glue:

```bash
aws glue get-database --name landing_db --query 'Database.Name'
aws glue get-database --name staging_db --query 'Database.Name'
aws glue get-database --name publish_db --query 'Database.Name'
```

### QuickSight

```bash
aws quicksight describe-account-settings --aws-account-id ${AWS_ACCOUNT_ID} \
  --query 'AccountSettings.Edition'
# Expected: "ENTERPRISE"

aws quicksight describe-data-source \
  --aws-account-id ${AWS_ACCOUNT_ID} \
  --data-source-id ${PROJECT}-athena-source \
  --query 'DataSource.Status'
# Expected: "CREATION_SUCCESSFUL"
```

### Summary

Once all checks pass, the pipeline infrastructure is ready. Proceed with:

1. Deploy Airflow DAGs to your MWAA environment
2. Upload workload config to S3 or Airflow Variables
3. Trigger the first pipeline run

---

## Appendix: Resource Naming Convention

| Resource Type | Naming Pattern | Example |
|---|---|---|
| S3 Bucket | `${PROJECT}-{zone}` | `myproject-landing` |
| KMS Alias | `alias/{zone}-data-key` | `alias/landing-data-key` |
| IAM Role | `${PROJECT}-{service}-role` | `myproject-glue-service-role` |
| Glue Database | `{zone}_db` | `landing_db` |
| Glue Crawler | `${PROJECT}-{workload}-{zone}-crawler` | `myproject-orders-staging-crawler` |
| Airflow DAG | `{workload}_dag` | `order_transactions_dag` |
| QuickSight Data Source | `${PROJECT}-athena-source` | `myproject-athena-source` |
| SNS Topic | `${PROJECT}-alerts` | `myproject-alerts` |
