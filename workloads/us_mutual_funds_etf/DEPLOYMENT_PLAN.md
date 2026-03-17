# Deployment Plan — US Mutual Funds & ETF Workload

**Workload:** `us_mutual_funds_etf`
**Target:** AWS Account (S3, Glue, Lake Formation, MWAA)
**Mode:** DRY-RUN (local mode) — MCP calls execute live, CLI calls logged only
**Date:** 2026-03-16

---

## Deployment Overview

This workload generates synthetic US mutual fund and ETF data through a Bronze → Silver → Gold medallion pipeline using AWS Glue ETL jobs orchestrated by Apache Airflow.

**Total artifacts:**
- 11 Glue PySpark ETL scripts
- 1 Airflow DAG
- 4 config files (source, semantic, quality_rules, schedule)
- 209 tests (all passing)

**Infrastructure:**
- S3 bucket: `s3://your-datalake-bucket/`
- Glue databases: `finsights_silver`, `finsights_gold`
- Glue version: 4.0
- Iceberg format: v2
- MWAA environment: `finsights-airflow-prod`

---

## Step 5.1: Upload Scripts to S3

**Operation:** Upload all ETL job scripts
**Tool:** `aws s3 cp` CLI (core MCP not loaded)
**Status:** DRY-RUN

```bash
# Upload Bronze scripts
aws s3 cp workloads/us_mutual_funds_etf/scripts/bronze/bronze_data_generation.py \
  s3://your-datalake-bucket/scripts/bronze/bronze_data_generation.py

# Upload Silver scripts (4 files)
aws s3 cp workloads/us_mutual_funds_etf/scripts/silver/ \
  s3://your-datalake-bucket/scripts/silver/ --recursive \
  --exclude "*.pyc" --exclude "__pycache__/*"

# Upload Gold scripts (5 files)
aws s3 cp workloads/us_mutual_funds_etf/scripts/gold/ \
  s3://your-datalake-bucket/scripts/gold/ --recursive \
  --exclude "*.pyc" --exclude "__pycache__/*"

# Upload Quality scripts (1 file)
aws s3 cp workloads/us_mutual_funds_etf/scripts/quality/quality_functions.py \
  s3://your-datalake-bucket/scripts/quality/quality_functions.py
```

**Expected output:**
- 11 files uploaded to S3
- Total size: ~50 KB

---

## Step 5.2: Create Glue Data Catalog Databases

**Operation:** Create Silver and Gold Glue databases
**Tool:** `aws glue create-database` CLI (aws-dataprocessing MCP not loaded)
**Status:** DRY-RUN

```bash
# Create Silver database
aws glue create-database --database-input '{
  "Name": "finsights_silver",
  "Description": "Cleaned and validated fund data (Iceberg tables)",
  "LocationUri": "s3://your-datalake-bucket/silver/"
}'

# Create Gold database
aws glue create-database --database-input '{
  "Name": "finsights_gold",
  "Description": "Star schema for analytics (Iceberg tables)",
  "LocationUri": "s3://your-datalake-bucket/gold/"
}'
```

**Expected output:**
- `finsights_silver` database created
- `finsights_gold` database created

---

## Step 5.3: Register Glue ETL Jobs

**Operation:** Create 10 Glue jobs (8 ETL + 2 quality checks)
**Tool:** `aws glue create-job` CLI (aws-dataprocessing MCP not loaded)
**Status:** DRY-RUN

### Job 1: Bronze Data Generation

```bash
aws glue create-job --name bronze_data_generation \
  --role GlueServiceRole \
  --command '{
    "Name": "glueetl",
    "ScriptLocation": "s3://your-datalake-bucket/scripts/bronze/bronze_data_generation.py",
    "PythonVersion": "3"
  }' \
  --glue-version "4.0" \
  --worker-type "G.1X" \
  --number-of-workers 2 \
  --timeout 60 \
  --default-arguments '{
    "--enable-spark-ui": "true",
    "--spark-event-logs-path": "s3://your-datalake-bucket/logs/spark-events/",
    "--enable-job-insights": "true",
    "--enable-glue-datacatalog": "true",
    "--job-language": "python",
    "--TempDir": "s3://your-datalake-bucket/tmp/"
  }' \
  --description "Generate synthetic Bronze data (130 funds, 130 market records, 150 NAV records)"
```

### Jobs 2-4: Silver Zone Cleaning (3 jobs)

```bash
# silver_funds_clean
aws glue create-job --name silver_funds_clean \
  --role GlueServiceRole \
  --command '{"Name": "glueetl", "ScriptLocation": "s3://your-datalake-bucket/scripts/silver/silver_funds_clean.py", "PythonVersion": "3"}' \
  --glue-version "4.0" --worker-type "G.1X" --number-of-workers 2 --timeout 60 \
  --description "Clean fund master data (dedup, standardize, validate)"

# silver_market_data_clean
aws glue create-job --name silver_market_data_clean \
  --role GlueServiceRole \
  --command '{"Name": "glueetl", "ScriptLocation": "s3://your-datalake-bucket/scripts/silver/silver_market_data_clean.py", "PythonVersion": "3"}' \
  --glue-version "4.0" --worker-type "G.1X" --number-of-workers 2 --timeout 60 \
  --description "Clean market metrics (expense ratios, ratings, beta, sharpe)"

# silver_nav_clean
aws glue create-job --name silver_nav_clean \
  --role GlueServiceRole \
  --command '{"Name": "glueetl", "ScriptLocation": "s3://your-datalake-bucket/scripts/silver/silver_nav_clean.py", "PythonVersion": "3"}' \
  --glue-version "4.0" --worker-type "G.1X" --number-of-workers 2 --timeout 60 \
  --description "Clean NAV and returns data (outlier clamping, orphan removal)"
```

### Job 5: Silver Quality Gate

```bash
aws glue create-job --name quality_checks_silver \
  --role GlueServiceRole \
  --command '{"Name": "glueetl", "ScriptLocation": "s3://your-datalake-bucket/scripts/silver/quality_checks_silver.py", "PythonVersion": "3"}' \
  --glue-version "4.0" --worker-type "G.1X" --number-of-workers 2 --timeout 30 \
  --description "Silver quality gate (0.80 threshold, blocks if score < 0.80 or critical failures > 0)"
```

### Jobs 6-9: Gold Zone Modeling (4 jobs)

```bash
# gold_dim_fund
aws glue create-job --name gold_dim_fund \
  --role GlueServiceRole \
  --command '{"Name": "glueetl", "ScriptLocation": "s3://your-datalake-bucket/scripts/gold/gold_dim_fund.py", "PythonVersion": "3"}' \
  --glue-version "4.0" --worker-type "G.1X" --number-of-workers 2 --timeout 60 \
  --description "Build fund dimension (joined from funds + market)"

# gold_dim_category
aws glue create-job --name gold_dim_category \
  --role GlueServiceRole \
  --command '{"Name": "glueetl", "ScriptLocation": "s3://your-datalake-bucket/scripts/gold/gold_dim_category.py", "PythonVersion": "3"}' \
  --glue-version "4.0" --worker-type "G.1X" --number-of-workers 2 --timeout 60 \
  --description "Build category dimension with surrogate keys"

# gold_dim_date
aws glue create-job --name gold_dim_date \
  --role GlueServiceRole \
  --command '{"Name": "glueetl", "ScriptLocation": "s3://your-datalake-bucket/scripts/gold/gold_dim_date.py", "PythonVersion": "3"}' \
  --glue-version "4.0" --worker-type "G.1X" --number-of-workers 2 --timeout 60 \
  --description "Build date dimension from distinct price dates"

# gold_fact_fund_performance
aws glue create-job --name gold_fact_fund_performance \
  --role GlueServiceRole \
  --command '{"Name": "glueetl", "ScriptLocation": "s3://your-datalake-bucket/scripts/gold/gold_fact_fund_performance.py", "PythonVersion": "3"}' \
  --glue-version "4.0" --worker-type "G.1X" --number-of-workers 2 --timeout 60 \
  --description "Build fact table (star schema, partitioned by year)"
```

### Job 10: Gold Quality Gate

```bash
aws glue create-job --name quality_checks_gold \
  --role GlueServiceRole \
  --command '{"Name": "glueetl", "ScriptLocation": "s3://your-datalake-bucket/scripts/gold/quality_checks_gold.py", "PythonVersion": "3"}' \
  --glue-version "4.0" --worker-type "G.1X" --number-of-workers 2 --timeout 30 \
  --description "Gold quality gate (0.95 threshold, blocks if score < 0.95 or critical failures > 0)"
```

**Expected output:**
- 10 Glue jobs registered
- All jobs configured with Iceberg support (Glue 4.0)

---

## Step 5.4: IAM Permissions Setup (MCP)

**Operation:** Verify and configure Glue service role permissions
**Tool:** `mcp__iam__*` (IAM MCP loaded)
**Status:** LIVE MCP CALLS

### 5.4.1: List Existing Roles

**MCP Call:** `mcp__iam__list_roles`

```python
# Expected to find: GlueServiceRole
```

### 5.4.2: Verify Role Permissions

**MCP Call:** `mcp__iam__simulate_principal_policy`

```python
# Test actions:
actions = [
    "s3:GetObject",
    "s3:PutObject",
    "s3:ListBucket",
    "glue:GetDatabase",
    "glue:GetTable",
    "glue:CreateTable",
    "glue:UpdateTable",
    "lakeformation:GetDataAccess"
]

resources = [
    "arn:aws:s3:::your-datalake-bucket/*",
    "arn:aws:glue:us-east-1:*:database/finsights_silver",
    "arn:aws:glue:us-east-1:*:database/finsights_gold",
    "arn:aws:glue:us-east-1:*:table/finsights_silver/*",
    "arn:aws:glue:us-east-1:*:table/finsights_gold/*"
]
```

**Expected result:** All actions return `allowed`

### 5.4.3: Inspect Inline Policies

**MCP Call:** `mcp__iam__list_role_policies` + `mcp__iam__get_role_policy`

```python
# Retrieve all inline policies attached to GlueServiceRole
# Expected: policies for S3, Glue, Lake Formation access
```

### 5.4.4: Add Missing Permissions (if needed)

**MCP Call:** `mcp__iam__put_role_policy`

```python
# Add inline policy for Iceberg table access if missing
policy_document = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "glue:GetTable",
                "glue:GetTables",
                "glue:CreateTable",
                "glue:UpdateTable",
                "glue:DeleteTable",
                "glue:GetPartitions"
            ],
            "Resource": [
                "arn:aws:glue:*:*:catalog",
                "arn:aws:glue:*:*:database/finsights_silver",
                "arn:aws:glue:*:*:database/finsights_gold",
                "arn:aws:glue:*:*:table/finsights_silver/*",
                "arn:aws:glue:*:*:table/finsights_gold/*"
            ]
        }
    ]
}
```

**Expected MCP calls:** 3-5 calls (list_roles, simulate, list_role_policies, get_role_policy, potentially put_role_policy)

---

## Step 5.5: Lake Formation Grants (MCP via Lambda)

**Operation:** Grant table permissions to Glue service role
**Tool:** `mcp__lambda__AWS_LambdaFn_LF_access_grant_new` (Lambda MCP loaded)
**Status:** LIVE MCP CALLS

### 5.5.1: Grant Silver Table Permissions

**MCP Call:** Invoke Lambda `LF_access_grant_new` 3 times

```python
# Grant 1: finsights_silver.funds_clean
{
    "database": "finsights_silver",
    "table": "funds_clean",
    "principal": "arn:aws:iam::*:role/GlueServiceRole",
    "permissions": ["SELECT", "INSERT", "DELETE", "ALTER"]
}

# Grant 2: finsights_silver.market_data_clean
{
    "database": "finsights_silver",
    "table": "market_data_clean",
    "principal": "arn:aws:iam::*:role/GlueServiceRole",
    "permissions": ["SELECT", "INSERT", "DELETE", "ALTER"]
}

# Grant 3: finsights_silver.nav_clean
{
    "database": "finsights_silver",
    "table": "nav_clean",
    "principal": "arn:aws:iam::*:role/GlueServiceRole",
    "permissions": ["SELECT", "INSERT", "DELETE", "ALTER"]
}
```

### 5.5.2: Grant Gold Table Permissions

**MCP Call:** Invoke Lambda `LF_access_grant_new` 4 times

```python
# Grant 4: finsights_gold.dim_fund
# Grant 5: finsights_gold.dim_category
# Grant 6: finsights_gold.dim_date
# Grant 7: finsights_gold.fact_fund_performance
# (Same structure as above, Gold database)
```

**Expected MCP calls:** 7 Lambda invocations (3 Silver + 4 Gold)

---

## Step 5.6: KMS Encryption Setup

**Operation:** Create/verify KMS keys for zone-specific encryption
**Tool:** `aws kms` CLI (core MCP not loaded)
**Status:** DRY-RUN

```bash
# Create Bronze zone KMS key
aws kms create-key --description "Bronze zone encryption key for your-datalake-bucket" \
  --tags TagKey=Zone,TagValue=Bronze TagKey=Workload,TagValue=us_mutual_funds_etf

# Create alias
aws kms create-alias --alias-name alias/finsights-bronze-key --target-key-id <key-id>

# Create Silver zone KMS key
aws kms create-key --description "Silver zone encryption key for your-datalake-bucket" \
  --tags TagKey=Zone,TagValue=Silver TagKey=Workload,TagValue=us_mutual_funds_etf

# Create alias
aws kms create-alias --alias-name alias/finsights-silver-key --target-key-id <key-id>

# Create Gold zone KMS key
aws kms create-key --description "Gold zone encryption key for your-datalake-bucket" \
  --tags TagKey=Zone,TagValue=Gold TagKey=Workload,TagValue=us_mutual_funds_etf

# Create alias
aws kms create-alias --alias-name alias/finsights-gold-key --target-key-id <key-id>
```

**Expected output:**
- 3 KMS keys created (Bronze, Silver, Gold)
- 3 aliases created

---

## Step 5.7: Deploy Airflow DAG to MWAA

**Operation:** Upload DAG file to MWAA S3 bucket
**Tool:** `aws s3 cp` CLI (core MCP not loaded)
**Status:** DRY-RUN

```bash
# Upload DAG to MWAA DAGs folder
aws s3 cp workloads/us_mutual_funds_etf/dags/us_mutual_funds_etf_dag.py \
  s3://finsights-mwaa-bucket/dags/us_mutual_funds_etf_dag.py

# Verify DAG uploaded
aws s3 ls s3://finsights-mwaa-bucket/dags/ | grep us_mutual_funds_etf
```

**Expected output:**
- DAG file uploaded
- MWAA will auto-detect and parse DAG within 5 minutes

---

## Step 5.8: Query Verification via Redshift Spectrum (MCP)

**Operation:** Verify Silver and Gold tables are queryable
**Tool:** `mcp__redshift__*` (Redshift MCP loaded)
**Status:** LIVE MCP CALLS

### 5.8.1: List Redshift Clusters

**MCP Call:** `mcp__redshift__list_clusters`

```python
# Expected to find: finsights-redshift-cluster
```

### 5.8.2: List External Schemas

**MCP Call:** `mcp__redshift__list_schemas`

```python
# Expected schemas (via Spectrum):
# - spectrum_silver (maps to finsights_silver Glue DB)
# - spectrum_gold (maps to finsights_gold Glue DB)
```

### 5.8.3: Verify Tables Visible

**MCP Call:** `mcp__redshift__list_tables`

```python
# Expected tables in spectrum_silver:
# - funds_clean
# - market_data_clean
# - nav_clean

# Expected tables in spectrum_gold:
# - dim_fund
# - dim_category
# - dim_date
# - fact_fund_performance
```

### 5.8.4: Run Validation Query

**MCP Call:** `mcp__redshift__execute_query`

```sql
-- Test 1: Count Silver tables
SELECT
    'funds_clean' AS table_name, COUNT(*) AS row_count
FROM spectrum_silver.funds_clean
UNION ALL
SELECT
    'market_data_clean', COUNT(*)
FROM spectrum_silver.market_data_clean
UNION ALL
SELECT
    'nav_clean', COUNT(*)
FROM spectrum_silver.nav_clean;

-- Expected results:
-- funds_clean: ~120 rows
-- market_data_clean: ~120 rows
-- nav_clean: ~140 rows
```

### 5.8.5: Star Schema Join Test

**MCP Call:** `mcp__redshift__execute_query`

```sql
-- Test 2: Verify fact-to-dim joins work
SELECT
    d.fund_name,
    d.fund_type,
    d.management_company,
    AVG(f.return_1yr_pct) AS avg_1yr_return,
    AVG(f.sharpe_ratio) AS avg_sharpe_ratio,
    SUM(f.total_assets_millions) / 1000 AS total_aum_billions
FROM spectrum_gold.fact_fund_performance f
JOIN spectrum_gold.dim_fund d
    ON f.fund_ticker = d.fund_ticker
JOIN spectrum_gold.dim_date dt
    ON f.date_key = dt.date_key
WHERE dt.year = 2024
GROUP BY d.fund_name, d.fund_type, d.management_company
ORDER BY avg_sharpe_ratio DESC
LIMIT 10;

-- Expected result: Top 10 funds by risk-adjusted performance
```

**Expected MCP calls:** 4-5 calls (list_clusters, list_schemas, list_tables, 2 execute_query)

---

## Step 5.9: Audit Trail Verification (MCP)

**Operation:** Verify all deployment operations are logged in CloudTrail
**Tool:** `mcp__cloudtrail__*` (CloudTrail MCP loaded)
**Status:** LIVE MCP CALLS

### 5.9.1: Verify S3 Uploads Logged

**MCP Call:** `mcp__cloudtrail__lookup_events`

```python
# Query parameters:
{
    "LookupAttributes": [
        {"AttributeKey": "EventName", "AttributeValue": "PutObject"}
    ],
    "StartTime": "2026-03-16T00:00:00Z",
    "EndTime": "2026-03-16T23:59:59Z",
    "MaxResults": 50
}

# Expected: PutObject events for:
# - s3://your-datalake-bucket/scripts/bronze/bronze_data_generation.py
# - s3://your-datalake-bucket/scripts/silver/*.py (4 files)
# - s3://your-datalake-bucket/scripts/gold/*.py (5 files)
# - s3://finsights-mwaa-bucket/dags/us_mutual_funds_etf_dag.py
```

### 5.9.2: Verify Glue Operations Logged

**MCP Call:** `mcp__cloudtrail__lookup_events`

```python
# Query for Glue job creation:
{
    "LookupAttributes": [
        {"AttributeKey": "EventName", "AttributeValue": "CreateJob"}
    ],
    "StartTime": "2026-03-16T00:00:00Z",
    "EndTime": "2026-03-16T23:59:59Z"
}

# Expected: 10 CreateJob events (8 ETL + 2 quality)
```

### 5.9.3: Verify Lake Formation Grants Logged

**MCP Call:** `mcp__cloudtrail__lookup_events`

```python
# Query for LF grants:
{
    "LookupAttributes": [
        {"AttributeKey": "EventName", "AttributeValue": "GrantPermissions"}
    ],
    "StartTime": "2026-03-16T00:00:00Z",
    "EndTime": "2026-03-16T23:59:59Z"
}

# Expected: 7 GrantPermissions events (3 Silver + 4 Gold)
```

### 5.9.4: Verify IAM Changes Logged

**MCP Call:** `mcp__cloudtrail__lookup_events`

```python
# Query for IAM policy updates:
{
    "LookupAttributes": [
        {"AttributeKey": "EventName", "AttributeValue": "PutRolePolicy"}
    ],
    "StartTime": "2026-03-16T00:00:00Z",
    "EndTime": "2026-03-16T23:59:59Z"
}

# Expected: 0-1 events (only if new policy was added)
```

### 5.9.5: Complex Audit Query (CloudTrail Lake)

**MCP Call:** `mcp__cloudtrail__lake_query`

```sql
-- Query CloudTrail Lake for all deployment activity
SELECT
    eventTime,
    eventName,
    eventSource,
    userIdentity.principalId,
    requestParameters,
    responseElements
FROM cloudtrail_events
WHERE eventTime >= '2026-03-16 00:00:00'
  AND eventTime <= '2026-03-16 23:59:59'
  AND (
    eventName IN ('PutObject', 'CreateJob', 'CreateDatabase', 'CreateTable',
                  'GrantPermissions', 'PutRolePolicy', 'CreateKey')
    OR (eventSource = 'lambda.amazonaws.com'
        AND requestParameters LIKE '%LF_access_grant%')
  )
ORDER BY eventTime DESC;
```

**Expected MCP calls:** 5-6 calls (4 lookup_events + 1 lake_query)

---

## Deployment Summary

### MCP Calls (LIVE in local mode)

| MCP Server | Calls | Operations |
|------------|-------|------------|
| **iam** | 3-5 | list_roles, simulate_principal_policy, list_role_policies, get_role_policy, (put_role_policy) |
| **lambda** | 7 | LF_access_grant_new (3 Silver + 4 Gold tables) |
| **redshift** | 4-5 | list_clusters, list_schemas, list_tables, execute_query (2x) |
| **cloudtrail** | 5-6 | lookup_events (4x), lake_query (1x) |
| **TOTAL MCP** | **19-23** | All executed against live AWS account |

### CLI Fallback (DRY-RUN in local mode)

| CLI Command | Calls | Reason |
|-------------|-------|--------|
| `aws s3 cp` | 12 | core MCP not loaded (upload scripts + DAG) |
| `aws glue create-database` | 2 | aws-dataprocessing MCP not loaded (Silver, Gold DBs) |
| `aws glue create-job` | 10 | aws-dataprocessing MCP not loaded (8 ETL + 2 quality) |
| `aws kms create-key` | 3 | core MCP not loaded (Bronze, Silver, Gold keys) |
| `aws kms create-alias` | 3 | core MCP not loaded (key aliases) |
| **TOTAL CLI** | **30** | Logged as [DRY-RUN] — not executed in local mode |

### Coverage

- **MCP Coverage:** 40% of operations (19-23 MCP / 49-53 total)
- **MCP-First Rule:** Followed — all operations checked MCP availability first
- **Audit Trail:** 100% (all CloudTrail calls via MCP)
- **Permission Verification:** 100% (all IAM calls via MCP)
- **Query Verification:** 100% (all Redshift calls via MCP)

---

## Post-Deployment Verification Checklist

**Manual steps after deployment:**

1. **Verify Glue Jobs Registered**
   ```bash
   aws glue list-jobs | grep -E "bronze_data_generation|silver_|gold_|quality_checks"
   ```
   Expected: 10 jobs listed

2. **Verify MWAA DAG Active**
   - Log into MWAA UI
   - Check "us_mutual_funds_etf_pipeline" DAG appears
   - Verify DAG has no import errors
   - Check schedule: Monthly, 1st of month, 02:00 UTC

3. **Run Test Execution**
   - Trigger DAG manually (don't wait for schedule)
   - Monitor task execution in MWAA UI
   - Verify Bronze → Silver → Gold flow completes
   - Check quality gates pass (Silver 0.80, Gold 0.95)

4. **Query Gold Tables via QuickSight**
   - Connect QuickSight to Athena
   - Query `finsights_gold.fact_fund_performance`
   - Create sample visualization (top 10 funds by Sharpe ratio)
   - Verify data looks realistic

5. **Review CloudTrail Logs**
   - Use CloudTrail console or MCP `lake_query`
   - Verify all deployment actions logged
   - Check for any failed API calls

---

## Rollback Plan

If deployment fails:

1. **Delete Glue Jobs**
   ```bash
   for job in bronze_data_generation silver_funds_clean silver_market_data_clean \
              silver_nav_clean quality_checks_silver gold_dim_fund gold_dim_category \
              gold_dim_date gold_fact_fund_performance quality_checks_gold; do
       aws glue delete-job --job-name $job
   done
   ```

2. **Revoke Lake Formation Grants** (via MCP Lambda)
   ```python
   mcp__lambda__AWS_Lambda_LF_revoke_access_new(
       database="finsights_silver",
       table="*",
       principal="arn:aws:iam::*:role/GlueServiceRole"
   )
   ```

3. **Delete Glue Databases**
   ```bash
   aws glue delete-database --name finsights_silver
   aws glue delete-database --name finsights_gold
   ```

4. **Remove S3 Scripts**
   ```bash
   aws s3 rm s3://your-datalake-bucket/scripts/ --recursive
   ```

5. **Remove MWAA DAG**
   ```bash
   aws s3 rm s3://finsights-mwaa-bucket/dags/us_mutual_funds_etf_dag.py
   ```

---

## Next Steps

After successful deployment:

1. **Add to Production Monitoring**
   - CloudWatch dashboard for Glue job metrics
   - SNS alerts for DAG failures
   - Cost tracking for Glue DPUs consumed

2. **Document for Ops Team**
   - Update runbook with troubleshooting steps
   - Add contact info for data engineering team
   - Document quality gate thresholds

3. **Schedule Recurring Reviews**
   - Monthly: Review quality metrics trends
   - Quarterly: Review AUM data accuracy
   - Annually: Review schema evolution needs

4. **Onboard Analysis Agent**
   - Load semantic.yaml into Analysis Agent context
   - Test NLP queries: "Which funds have highest Sharpe ratio?"
   - Integrate with QuickSight Q&A

---

## MCP Server Reconnection Guide

To increase MCP coverage from 40% to 100%, fix these servers:

**High Priority:**
- `aws-dataprocessing` → Would eliminate 12 Glue/Athena CLI calls
- `core` → Would eliminate 18 S3/KMS CLI calls

**Steps:**
```bash
# Test if packages are installable
uvx awslabs.core-mcp-server@latest --help
uvx awslabs.aws-dataprocessing-mcp-server@latest --help

# If errors, check Python env and AWS credentials
python3 --version  # Must be 3.11+
aws sts get-caller-identity  # Must succeed

# Restart Claude Code to reload MCP servers
```

Once reconnected, MCP coverage would increase to 100%.
