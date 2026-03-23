# 00 — SETUP: First-Time AWS Environment Setup

> Run this prompt ONCE after cloning the repo into a new AWS account.
> It creates all AWS resources needed before you can onboard data.

## Purpose

Interactive, guided setup of all AWS prerequisites using MCP tools and CLI. Run this before any other prompt (ROUTE, ONBOARD, etc.). Claude will create resources step-by-step, verify each one, and present a final checklist.

## When to Use

- First time cloning the repo into a new AWS account
- Setting up a new region in an existing account
- Recovering after infrastructure was deleted
- Onboarding a new team member who needs their own dev environment

## Prerequisites

Before running this prompt, ensure:

1. **AWS CLI configured**: `aws sts get-caller-identity` returns your account
2. **uv installed**: `uv --version` returns 0.9+
3. **Python 3.12+**: `python3.12 --version` or `python3.13 --version`
4. **Claude Code**: Running in this project directory

## Prompt Template

```
Setup AWS environment for the Agentic Data Onboarding platform.

Account details:
- AWS Region: [us-east-1 / your region]
- Project name: [PROJECT_NAME, e.g., "data-onboarding"]
- Environment: [dev / staging / prod]

What I need created (check all that apply):
- [x] IAM roles (Glue service role, Lake Formation role)
- [x] S3 data lake bucket with zone folders (landing/bronze/silver/gold)
- [x] KMS encryption keys (one per zone)
- [x] Glue Data Catalog databases (landing_db, staging_db, publish_db)
- [x] Lake Formation LF-Tags (PII_Classification, PII_Type, Data_Sensitivity)
- [x] Lake Formation TBAC grants (Glue role gets full access)
- [ ] MWAA environment (skip if already exists)
- [ ] Airflow Variables (set after MWAA exists)
- [ ] QuickSight subscription (skip if not using dashboards)
- [ ] Amazon Verified Permissions policy store (Cedar policies)

Existing resources (skip creation):
- MWAA bucket: [BUCKET_NAME or "none"]
- Existing Glue role: [ROLE_NAME or "none"]
- Existing KMS keys: [ALIAS or "none"]
```

## What Claude Will Do

Claude uses MCP tools where available, CLI fallback otherwise. Each step verifies success before proceeding.

### Step 1: Verify Prerequisites

```
Action: Check AWS credentials, region, MCP server connectivity
MCP:    mcp__iam__list_roles (verify IAM access)
        mcp__cloudtrail__lookup_events (verify CloudTrail access)
CLI:    aws sts get-caller-identity
        claude mcp list
Output: Account ID, region, MCP server status table
Gate:   Must have valid credentials and at least iam + cloudtrail MCP connected
```

### Step 2: Create IAM Roles

```
Action: Create Glue service role with S3, KMS, Glue, LF permissions
MCP:    mcp__iam__create_role (create role)
        mcp__iam__put_role_policy (attach inline policy)
        mcp__iam__simulate_principal_policy (verify permissions work)
Output: Role ARN, attached policies, simulation results
Gate:   simulate_principal_policy returns "allowed" for s3:GetObject, glue:GetTable
```

Roles created:
- `{PROJECT}-glue-service-role` — Glue jobs, crawlers, data quality
- Trust policy: `glue.amazonaws.com`
- Permissions: S3 zone access, KMS encrypt/decrypt, Glue catalog, Lake Formation, CloudWatch logs

### Step 3: Create S3 Data Lake Bucket

```
Action: Create bucket with zone folders, encryption, versioning, public access block
MCP:    core MCP (S3 operations) or CLI fallback
CLI:    aws s3api create-bucket
        aws s3api put-bucket-encryption (SSE-KMS)
        aws s3api put-public-access-block
        aws s3api put-bucket-versioning (landing zone)
Output: Bucket name, zone folders created, encryption confirmed
Gate:   aws s3 ls s3://{BUCKET}/ shows zone folders
```

Bucket structure:
```
s3://{PROJECT}-{ACCOUNT_ID}-{REGION}/
  landing/
  bronze/
  silver/
  gold/
  quarantine/
  scripts/
  athena-results/
```

### Step 4: Create KMS Keys

```
Action: Create 4 zone-specific KMS keys with aliases and rotation
MCP:    core MCP (KMS operations) or CLI fallback
CLI:    aws kms create-key
        aws kms create-alias
        aws kms enable-key-rotation
Output: 4 key ARNs + aliases, rotation enabled
Gate:   aws kms describe-key returns each alias
```

Keys created:
- `alias/{PROJECT}-landing-key`
- `alias/{PROJECT}-staging-key`
- `alias/{PROJECT}-publish-key`
- `alias/{PROJECT}-catalog-key`

### Step 5: Create Glue Databases

```
Action: Create 3 zone databases in Glue Data Catalog
CLI:    aws glue create-database (3x)
Output: 3 databases created
Gate:   aws glue get-databases lists all 3
```

Databases: `landing_db`, `staging_db`, `publish_db`

### Step 6: Create Lake Formation LF-Tags

```
Action: Create 3 LF-Tags for column-level security
CLI:    aws lakeformation create-lf-tag (3x)
Output: 3 tags created with values
Gate:   aws lakeformation list-lf-tags shows all 3
```

Tags:
- `PII_Classification`: CRITICAL, HIGH, MEDIUM, LOW, NONE
- `PII_Type`: EMAIL, PHONE, SSN, CREDIT_CARD, NAME, ADDRESS, DOB, IP_ADDRESS, DRIVER_LICENSE, PASSPORT, NATIONAL_ID, FINANCIAL_ACCOUNT, NONE
- `Data_Sensitivity`: CRITICAL, HIGH, MEDIUM, LOW

### Step 7: Grant Lake Formation TBAC Permissions

```
Action: Grant Glue role access to all sensitivity levels (full access for ETL)
CLI:    aws lakeformation grant-permissions (LFTagPolicy resource)
MCP:    mcp__lambda__AWS_LambdaFn_LF_access_grant_new (if Lambda exists)
Output: TBAC grants confirmed
Gate:   aws lakeformation list-permissions shows grants for Glue role
```

### Step 8: Set Airflow Variables (if MWAA exists)

```
Action: Set required Airflow Variables via MWAA CLI token
CLI:    aws mwaa create-cli-token + curl
Output: Variables set: glue_script_s3_path, glue_iam_role, aws_account_id,
        kms_key_landing, kms_key_staging, kms_key_publish, kms_key_catalog,
        s3_landing_bucket, s3_staging_bucket, s3_publish_bucket
Gate:   airflow variables list shows all variables
```

### Step 9: Setup Cedar Policies (Optional)

```
Action: Create Amazon Verified Permissions policy store and sync Cedar policies
CLI:    python3 shared/scripts/setup_avp.py
Output: Policy store ID, 23 policies synced
Gate:   Script exits with 0, policy store accessible
```

### Step 10: Final Verification

```
Action: Run comprehensive check across all created resources
MCP:    iam (roles), cloudtrail (audit), redshift (if exists)
CLI:    aws s3 ls, aws glue get-databases, aws kms list-aliases,
        aws lakeformation list-lf-tags, aws lakeformation list-permissions

Output:
  ENVIRONMENT SETUP VERIFICATION: {PROJECT}
  ──────────────────────────────────────────
  AWS Credentials:  Account {ID}, Region {REGION}  [PASS]
  MCP Servers:      {N}/11 connected               [PASS]
  IAM Roles:        {PROJECT}-glue-service-role     [PASS/FAIL]
  S3 Bucket:        {BUCKET} with 7 zone folders    [PASS/FAIL]
  KMS Keys:         4 keys, rotation enabled        [PASS/FAIL]
  Glue Databases:   landing_db, staging_db, publish [PASS/FAIL]
  LF-Tags:          3 tags created                  [PASS/FAIL]
  TBAC Grants:      Glue role has full access       [PASS/FAIL]
  MWAA Variables:   {N} variables set               [PASS/SKIP]
  Cedar Policies:   23 policies synced              [PASS/SKIP]
  ──────────────────────────────────────────
  Overall: [ALL PASS / {N} FAILURES]

Gate: ALL required checks must PASS. SKIP is acceptable for optional items.
```

## Example Usage

### Minimal Setup (New Account, No MWAA Yet)

```
Setup AWS environment for the Agentic Data Onboarding platform.

Account details:
- AWS Region: us-east-1
- Project name: data-onboarding
- Environment: dev

What I need created:
- [x] IAM roles
- [x] S3 data lake bucket
- [x] KMS encryption keys
- [x] Glue databases
- [x] Lake Formation LF-Tags
- [x] Lake Formation TBAC grants
- [ ] MWAA environment (will set up later)
- [ ] Airflow Variables
- [ ] QuickSight
- [ ] Cedar policies

Existing resources: none
```

### Adding to Existing Account (MWAA Already Exists)

```
Setup AWS environment for the Agentic Data Onboarding platform.

Account details:
- AWS Region: us-east-1
- Project name: financial-analytics
- Environment: prod

What I need created:
- [x] IAM roles
- [x] S3 data lake bucket
- [x] KMS encryption keys
- [x] Glue databases
- [x] Lake Formation LF-Tags
- [x] Lake Formation TBAC grants
- [ ] MWAA environment (already exists)
- [x] Airflow Variables
- [x] QuickSight subscription
- [x] Cedar policies

Existing resources:
- MWAA bucket: amazon-sagemaker-123456789-us-east-1-abc123
- Existing Glue role: none
- Existing KMS keys: none
```

## After Setup Is Complete

You're ready to onboard data. Next steps:

1. **Check for existing data**: Use `prompts/01-route-check-existing.md`
2. **Generate test data**: Use `prompts/02-generate-synthetic-data.md`
3. **Build a pipeline**: Use `prompts/03-onboard-build-pipeline.md`
4. **Deploy to AWS**: Use `deploy_to_aws.py --mwaa-bucket=BUCKET`

## Teardown (Remove All Resources)

To clean up everything created by this prompt:

```bash
# Delete in reverse order (dependencies first)
aws lakeformation delete-lf-tag --tag-key PII_Classification
aws lakeformation delete-lf-tag --tag-key PII_Type
aws lakeformation delete-lf-tag --tag-key Data_Sensitivity
aws glue delete-database --name landing_db
aws glue delete-database --name staging_db
aws glue delete-database --name publish_db
aws kms schedule-key-deletion --key-id alias/{PROJECT}-landing-key --pending-window-in-days 7
# Repeat for other KMS keys
aws s3 rb s3://{BUCKET} --force
aws iam detach-role-policy --role-name {PROJECT}-glue-service-role --policy-arn ...
aws iam delete-role-policy --role-name {PROJECT}-glue-service-role --policy-name ...
aws iam delete-role --role-name {PROJECT}-glue-service-role
```
