# Troubleshooting Guide — US Mutual Funds & ETF Workload

**Date:** March 16, 2026
**Workload:** `us_mutual_funds_etf`
**Pipeline:** Bronze → Silver → Gold (Iceberg + AWS Glue)

This document captures all issues encountered during pipeline deployment and their resolutions for future reference.

---

## Summary of Issues Encountered

| # | Issue | Phase | Severity | Time Lost | Status |
|---|-------|-------|----------|-----------|--------|
| 1 | PySpark DoubleType cannot accept Python int literals | Bronze | HIGH | ~10 min | ✅ FIXED |
| 2 | Static Spark configs modified at runtime | Silver/Gold | HIGH | ~25 min | ✅ FIXED |
| 3 | Insufficient Lake Formation permissions for GlueServiceRole | Silver | HIGH | ~5 min | ✅ FIXED |
| 4 | Race condition in parallel Silver jobs | Silver | MEDIUM | ~5 min | ✅ FIXED |
| 5 | Incorrect DataFrame reference in aggregation | Gold | MEDIUM | ~3 min | ✅ FIXED |

**Total Time Lost to Issues:** ~48 minutes
**Total Pipeline Completion Time:** ~120 minutes (including debugging)

---

## Issue #1: PySpark DoubleType Cannot Accept Python Int Literals

### Symptoms

```
TypeError: field return_1yr_pct: DoubleType() can not accept object 9999 in type <class 'int'>
```

**Job:** `bronze_data_generation`
**File:** `scripts/bronze/bronze_data_generation.py:231`

### Root Cause

PySpark's `DoubleType()` schema requires float literals (e.g., `9999.0`), not Python int objects (e.g., `9999`). When generating intentional outlier data for testing, the script used integer literals:

```python
# WRONG (line 231 before fix):
return_1yr = 9999 if nav_row_count % 2 == 0 else -500
```

Even though the schema defined `return_1yr_pct` as `DoubleType()`, PySpark cannot implicitly cast Python int to float when creating DataFrames.

### Solution

Changed integer literals to float literals:

```python
# CORRECT (line 231 after fix):
return_1yr = 9999.0 if nav_row_count % 2 == 0 else -500.0
```

### How to Avoid

1. **Always use float literals for DoubleType columns:**
   ```python
   # DO THIS:
   .withColumn("price", F.lit(100.0))

   # NOT THIS:
   .withColumn("price", F.lit(100))
   ```

2. **Use explicit casting if working with integer variables:**
   ```python
   int_value = 9999
   .withColumn("return_pct", F.lit(float(int_value)))
   ```

3. **Test with sample data early:**
   - Run `df.show()` immediately after creating DataFrame
   - Catches type errors before writing to S3

### Files Changed

- `scripts/bronze/bronze_data_generation.py` (line 231)

### Verification

```bash
# Check job status
aws glue get-job-run --job-name bronze_data_generation --run-id jr_7c30f... --query 'JobRun.JobRunState'

# Expected: SUCCEEDED (after fix)
```

**Job Run ID (Fixed):** `jr_7c30f5736d1ed4436901a22b21c3856f50f11823e112f665b8d8f9776b1c51f4`
**Duration:** 81 seconds

---

## Issue #2: Static Spark Configs Modified at Runtime

### Symptoms

```
AnalysisException: Cannot modify the value of a static config: spark.sql.extensions
```

**Jobs Affected:**
- `silver_funds_clean`
- `silver_market_data_clean`
- `silver_nav_clean`

**Failed Run IDs:**
- `jr_ba6c4cdae4f7f69fc78d03f58784cf5b01bee53ef5c4266057653f605ac96a97` (funds)
- `jr_9ba6a35d0f46986912c49390b5ebb5f79ee1daa2abe39ca94aefd8c884617643` (market)
- `jr_cb4216d15f730de91fa840d4c567c0ff58f4b4e00ef80689908e385d23f242a2` (nav)

### Root Cause

All 3 Silver scripts attempted to configure Apache Iceberg via `spark.conf.set()` **after** SparkSession was already initialized by AWS Glue:

```python
# WRONG (lines 28-32 in all Silver scripts):
spark.conf.set("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
spark.conf.set("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog")
spark.conf.set("spark.sql.catalog.glue_catalog.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog")
spark.conf.set("spark.sql.catalog.glue_catalog.warehouse", "s3://your-datalake-bucket/")
spark.conf.set("spark.sql.catalog.glue_catalog.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
```

**Why it fails:**
- `spark.sql.extensions` is a **static configuration** that must be set at SparkSession creation time
- AWS Glue creates the SparkSession before running user code
- Attempting to modify static configs at runtime throws `AnalysisException`

### Solution

**Removed runtime `spark.conf.set()` calls from all 3 scripts** and moved configuration to Glue job `DefaultArguments`:

```python
# CORRECT: Scripts no longer set Iceberg configs
# (Removed lines 28-32 from all Silver scripts)

job.init(args["JOB_NAME"], args)
logger = glueContext.get_logger()

# Directly proceed to data processing
logger.info("[silver_funds_clean] STEP 1: Reading Bronze raw_funds data")
```

**Updated Glue job configuration via AWS CLI:**

```bash
aws glue update-job --job-name silver_funds_clean --job-update '{
  "DefaultArguments": {
    "--TempDir": "s3://your-datalake-bucket/tmp/",
    "--enable-glue-datacatalog": "true",
    "--datalake-formats": "iceberg",
    "--conf": "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions --conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog --conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog --conf spark.sql.catalog.glue_catalog.warehouse=s3://your-datalake-bucket/ --conf spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO"
  }
}'
```

**Key parameters:**
- `--datalake-formats`: `iceberg` (enables Iceberg support in Glue 4.0)
- `--conf`: All Spark configs in a single space-separated string

### How to Avoid

1. **Never use `spark.conf.set()` for static configs in Glue jobs:**
   - Static configs: `spark.sql.extensions`, `spark.sql.catalog.*`, `spark.driver.*`, `spark.executor.*`
   - These must be set at job startup via `DefaultArguments`

2. **Use Glue job `DefaultArguments` with `--conf` flag:**
   ```json
   {
     "--datalake-formats": "iceberg",
     "--conf": "spark.config1=value1 --conf spark.config2=value2"
   }
   ```

3. **Runtime-modifiable configs are OK:**
   ```python
   # These can be set in scripts:
   spark.conf.set("spark.sql.shuffle.partitions", "200")  # ✅ OK
   spark.conf.set("spark.default.parallelism", "100")     # ✅ OK
   ```

4. **Test Iceberg configuration:**
   ```python
   # Verify Iceberg is loaded
   spark.sql("SHOW CATALOGS").show()
   # Should show "glue_catalog"
   ```

### Files Changed

- `scripts/silver/silver_funds_clean.py` (removed lines 28-32)
- `scripts/silver/silver_market_data_clean.py` (removed lines 28-32)
- `scripts/silver/silver_nav_clean.py` (removed lines 28-32)
- Glue job configs updated via AWS CLI

### Verification

```bash
# Check job DefaultArguments include Iceberg config
aws glue get-job --job-name silver_funds_clean --query 'Job.DefaultArguments'

# Expected output:
{
  "--TempDir": "s3://your-datalake-bucket/tmp/",
  "--enable-glue-datacatalog": "true",
  "--datalake-formats": "iceberg",
  "--conf": "spark.sql.extensions=... (full config string)"
}
```

**Fixed Job Run IDs:**
- `jr_ac899b3c1f7a14e11d59ff260abad54cbc57062a1172f59520056382dc410d16` (funds) — SUCCEEDED (86s)
- `jr_78ec1ba713abcc92395092ade1646b9f7e4b6439feb7002864e4a810d7dbb44a` (market) — SUCCEEDED (101s)

---

## Issue #3: Insufficient Lake Formation Permissions for GlueServiceRole

### Symptoms

```
An error occurred while calling o159.createOrReplace. Insufficient Lake Formation permission(s) on funds_clean
(Service: Glue, Status Code: 400, Request ID: 50355e9d-9977-4f59-bf07-84456bb9f8a9)
```

**Jobs Affected:**
- `silver_funds_clean` (trying to create `funds_clean` table)
- `silver_market_data_clean` (trying to create `market_data_clean` table)
- `silver_nav_clean` (trying to read `funds_clean` table)

**Failed Run IDs:**
- `jr_568d510da0992a492ba232a8184219f8ec9e2c2210074c974a05710f546d7df1` (funds)
- `jr_cb9322470e526e5e8476acc6ae4565b61c2f89fbed8468ab3fdd1559a9ea9a8d` (market)
- `jr_02316a0a4b675384d8773e31bc2bf7706e60fa1264bb83b78b426d0fafb8ffbc` (nav)

### Root Cause

**AWS Lake Formation is enabled by default** and requires explicit permissions for all database and table operations, **even if IAM policies allow them**.

The `GlueServiceRole` had IAM permissions (`AWSGlueServiceRole` + `AmazonS3FullAccess`) but **no Lake Formation grants**:
- No permission to create tables in `finsights_silver` database
- No permission to create tables in `finsights_gold` database
- No permission to read/write data from existing tables

When Iceberg `.createOrReplace()` tried to create tables, Lake Formation blocked the operation.

### Solution

**Granted Lake Formation permissions to GlueServiceRole** for both databases:

#### Step 1: Database-Level Permissions

```bash
# Grant permissions on finsights_silver database
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::123456789012:role/GlueServiceRole \
  --resource '{"Database":{"Name":"finsights_silver"}}' \
  --permissions CREATE_TABLE ALTER DROP DESCRIBE

# Grant permissions on finsights_gold database
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::123456789012:role/GlueServiceRole \
  --resource '{"Database":{"Name":"finsights_gold"}}' \
  --permissions CREATE_TABLE ALTER DROP DESCRIBE
```

#### Step 2: Table Wildcard Permissions

```bash
# Grant permissions on ALL tables in finsights_silver
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::123456789012:role/GlueServiceRole \
  --resource '{"Table":{"DatabaseName":"finsights_silver","TableWildcard":{}}}' \
  --permissions SELECT INSERT ALTER DELETE DROP DESCRIBE \
  --permissions-with-grant-option SELECT INSERT ALTER DELETE DROP DESCRIBE

# Grant permissions on ALL tables in finsights_gold
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::123456789012:role/GlueServiceRole \
  --resource '{"Table":{"DatabaseName":"finsights_gold","TableWildcard":{}}}' \
  --permissions SELECT INSERT ALTER DELETE DROP DESCRIBE \
  --permissions-with-grant-option SELECT INSERT ALTER DELETE DROP DESCRIBE
```

**Why `--permissions-with-grant-option`?**
- Allows Glue jobs to manage Iceberg metadata tables
- Iceberg creates internal tables (snapshots, manifests) that need CREATE_TABLE permission

### How to Avoid

1. **Always grant Lake Formation permissions upfront** when creating Glue databases:

```bash
# When creating a new database, immediately grant LF permissions
aws glue create-database --database-input '{"Name":"my_database"}'

aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT:role/GlueServiceRole \
  --resource '{"Database":{"Name":"my_database"}}' \
  --permissions CREATE_TABLE ALTER DROP DESCRIBE

aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT:role/GlueServiceRole \
  --resource '{"Table":{"DatabaseName":"my_database","TableWildcard":{}}}' \
  --permissions ALL
```

2. **Check Lake Formation settings before running jobs:**

```bash
# List all permissions for a principal
aws lakeformation list-permissions \
  --resource '{"Database":{"Name":"finsights_silver"}}' \
  --query 'PrincipalResourcePermissions[*].[Principal,Permissions]' \
  --output table
```

3. **Use Lake Formation MCP Lambda for automated grants:**

```python
# Use the MCP Lambda function
mcp__lambda__AWS_LambdaFn_LF_access_grant_new({
  "principal_arn": "arn:aws:iam::ACCOUNT:role/GlueServiceRole",
  "database_name": "finsights_silver",
  "permissions": ["CREATE_TABLE", "ALTER", "DROP"]
})
```

4. **Test with a simple CREATE TABLE before running full pipeline:**

```python
# Test script
spark.sql("""
  CREATE TABLE glue_catalog.finsights_silver.test_table (id INT)
  USING iceberg
""")
# If this fails with "Insufficient Lake Formation permission", fix grants first
```

### Verification

```bash
# Verify database permissions
aws lakeformation list-permissions \
  --resource '{"Database":{"Name":"finsights_silver"}}' \
  --query 'PrincipalResourcePermissions[?Principal.DataLakePrincipalIdentifier==`arn:aws:iam::123456789012:role/GlueServiceRole`]' \
  --output table

# Verify table wildcard permissions
aws lakeformation list-permissions \
  --resource '{"Table":{"DatabaseName":"finsights_silver","TableWildcard":{}}}' \
  --query 'PrincipalResourcePermissions[?Principal.DataLakePrincipalIdentifier==`arn:aws:iam::123456789012:role/GlueServiceRole`]' \
  --output table
```

**Fixed Job Run IDs:**
- `jr_ac899b3c1f7a14e11d59ff260abad54cbc57062a1172f59520056382dc410d16` (funds) — SUCCEEDED (86s)
- `jr_78ec1ba713abcc92395092ade1646b9f7e4b6439feb7002864e4a810d7dbb44a` (market) — SUCCEEDED (101s)

---

## Issue #4: Race Condition in Parallel Silver Jobs

### Symptoms

```
AnalysisException: Table or view not found: glue_catalog.finsights_silver.funds_clean
```

**Job:** `silver_nav_clean`
**Failed Run ID:** `jr_1d4c266eb1924e0646fa92b77185cb575e954e4602f90a9e49ebe596c7202dba`

**Timing:**
- `silver_funds_clean` SUCCEEDED at 86 seconds
- `silver_market_data_clean` SUCCEEDED at 101 seconds
- `silver_nav_clean` FAILED at 85 seconds (tried to read `funds_clean` 1 second before it was created)

### Root Cause

The `silver_nav_clean` script performs referential integrity validation by joining with `funds_clean` to drop orphan NAV records:

```python
# Line 99 in silver_nav_clean.py
df_valid_funds = spark.table("glue_catalog.finsights_silver.funds_clean").select("fund_ticker")
```

**Race condition:**
1. All 3 Silver jobs started in parallel at 14:37:35
2. `silver_nav_clean` reached line 99 at ~85 seconds (14:39:00)
3. `silver_funds_clean` completed table creation at ~86 seconds (14:39:01)
4. Glue Data Catalog may have a slight propagation delay (seconds)
5. `silver_nav_clean` tried to read `funds_clean` before it was fully registered → table not found

### Solution (Immediate)

**Restarted `silver_nav_clean` after `funds_clean` table existed:**

```bash
aws glue start-job-run --job-name silver_nav_clean
# Run ID: jr_1c7e61a21a1f689e1549433bc0ce932f2c6e735bf92bd9b4d800354b697d0c62
# Result: SUCCEEDED (120 seconds)
```

### Solution (Long-Term)

**Option 1: Sequential Execution (Recommended)**

Update DAG to run `silver_nav_clean` **after** `silver_funds_clean` completes:

```python
# In Airflow DAG
silver_funds_task >> silver_nav_task  # Dependency
silver_market_task  # Still parallel with silver_funds_task
```

**Option 2: Add Retry Logic with Exponential Backoff**

Update `silver_nav_clean.py` to retry table lookup:

```python
import time

max_retries = 3
retry_delay = 5  # seconds

for attempt in range(max_retries):
    try:
        df_valid_funds = spark.table("glue_catalog.finsights_silver.funds_clean").select("fund_ticker")
        break  # Success
    except AnalysisException as e:
        if "Table or view not found" in str(e) and attempt < max_retries - 1:
            logger.warning(f"[silver_nav_clean] funds_clean not found, retry {attempt + 1}/{max_retries} in {retry_delay}s")
            time.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff
        else:
            raise  # Max retries exceeded or different error
```

**Option 3: Remove Orphan Check (Not Recommended)**

Simplify `silver_nav_clean` to skip referential integrity validation. This is **not recommended** because:
- Orphan records in Silver zone cause FK violations in Gold zone
- Data quality issues propagate downstream
- Debugging becomes harder

### How to Avoid

1. **Design DAGs with proper dependencies:**
   ```python
   # Correct: Sequential when there's a dependency
   bronze_task >> silver_funds_task >> silver_nav_task

   # Also correct: Parallel when independent
   bronze_task >> [silver_funds_task, silver_market_task]
   silver_funds_task >> silver_nav_task
   ```

2. **Use Glue Workflows with triggers:**
   ```bash
   # Create workflow with conditional trigger
   aws glue create-trigger \
     --name silver_nav_trigger \
     --type CONDITIONAL \
     --predicate 'Conditions=[{LogicalOperator=EQUALS,JobName=silver_funds_clean,State=SUCCEEDED}]' \
     --actions Actions=[{JobName=silver_nav_clean}]
   ```

3. **Add table existence checks before reading:**
   ```python
   # Check if table exists before reading
   tables = spark.sql("SHOW TABLES IN glue_catalog.finsights_silver").collect()
   table_names = [row.tableName for row in tables]

   if "funds_clean" not in table_names:
       raise Exception("funds_clean table not found - run silver_funds_clean first")
   ```

4. **Use Iceberg snapshot isolation for reads:**
   ```python
   # Read from a specific snapshot (if available)
   df = spark.read \
     .format("iceberg") \
     .option("snapshot-id", "123456789") \
     .table("glue_catalog.finsights_silver.funds_clean")
   ```

### Files Changed

- None (resolved by restarting job, long-term fix pending in DAG)

### Verification

```bash
# Verify all 3 Silver tables exist
aws glue get-tables --database-name finsights_silver --query 'TableList[*].Name'

# Expected: ["funds_clean", "market_data_clean", "nav_clean"]
```

**Fixed Job Run ID:**
- `jr_1c7e61a21a1f689e1549433bc0ce932f2c6e735bf92bd9b4d800354b697d0c62` (nav_clean) — SUCCEEDED (120s)

---

## Issue #5: Incorrect DataFrame Reference in Aggregation

### Symptoms

```
AnalysisException: Column 'fund_category' does not exist. Did you mean one of the following? [glue_catalog.finsights_silver.market_data_clean.beta, glue_catalog.finsights_silver.market_data_clean.asset_class, ...]
```

**Job:** `gold_dim_category`
**Failed Run ID:** `jr_99e7d19a94f2930dd32d7ac8813d3bd6acec1e214c128d4d11abc3714237ed19`

### Root Cause

The `gold_dim_category` script attempted to group by `fund_category` from the `df_market` DataFrame, but that column only exists in `df_funds`:

```python
# WRONG (line 70 before fix):
df_expense_agg = df_market.groupBy("fund_category").agg(
    F.min("expense_ratio_pct").alias("typical_expense_min"),
    F.max("expense_ratio_pct").alias("typical_expense_max")
)
```

**Column Distribution:**
- `funds_clean` has: `fund_category`, `geographic_focus`
- `market_data_clean` has: `expense_ratio_pct`, `asset_class`, `benchmark_index`
- Neither column exists in both tables

The script had already created `df_joined` (line 45) which joined both tables, but then tried to use `df_market` alone for the aggregation.

### Solution

Changed the DataFrame reference from `df_market` to `df_joined`:

```python
# CORRECT (line 70 after fix):
df_expense_agg = df_joined.groupBy("fund_category").agg(
    F.min("expense_ratio_pct").alias("typical_expense_min"),
    F.max("expense_ratio_pct").alias("typical_expense_max")
)
```

Since `df_joined` contains columns from both `funds_clean` and `market_data_clean`, it has both:
- `fund_category` (from funds_clean)
- `expense_ratio_pct` (from market_data_clean)

### How to Avoid

1. **Verify column availability before aggregation:**
   ```python
   # Check which columns are available
   print("df_market columns:", df_market.columns)
   print("df_joined columns:", df_joined.columns)

   # Use the correct DataFrame
   if "fund_category" in df_joined.columns:
       df_agg = df_joined.groupBy("fund_category").agg(...)
   ```

2. **Use explicit joins before aggregating across tables:**
   ```python
   # Always join first if you need columns from multiple tables
   df_joined = df_funds.join(df_market, "fund_ticker", "inner")

   # Then aggregate from the joined DataFrame
   df_agg = df_joined.groupBy("col_from_funds").agg(F.sum("col_from_market"))
   ```

3. **Test queries with `.show()` early:**
   ```python
   # Test that the column exists before running expensive aggregations
   df_market.select("fund_category").show(1)  # Will fail if column doesn't exist
   ```

4. **Use schema validation:**
   ```python
   required_columns = ["fund_category", "expense_ratio_pct"]
   available_columns = df_joined.columns
   missing = [col for col in required_columns if col not in available_columns]

   if missing:
       raise ValueError(f"Missing required columns: {missing}")
   ```

### Files Changed

- `scripts/gold/gold_dim_category.py` (line 70: `df_market` → `df_joined`)

### Verification

```bash
# Verify table schemas
aws glue get-table --database-name finsights_silver --name funds_clean \
  --query 'Table.StorageDescriptor.Columns[*].Name'

aws glue get-table --database-name finsights_silver --name market_data_clean \
  --query 'Table.StorageDescriptor.Columns[*].Name'
```

**Fixed Job Run ID:**
- `jr_0784f30a298223570843fbfba08555700970d2646a77dbdb1ce5b84e43c338d8` (dim_category) — SUCCEEDED (76s)

---

## Best Practices Learned

### 1. Data Type Handling

✅ **DO:**
- Use float literals (`100.0`) for DoubleType columns
- Use explicit casting when working with variables: `F.lit(float(value))`
- Test DataFrame creation early with `.show()`

❌ **DON'T:**
- Use integer literals (`100`) for DoubleType columns
- Rely on implicit type conversion in PySpark

### 2. Spark Configuration

✅ **DO:**
- Set static configs in Glue job `DefaultArguments` with `--conf` flag
- Use `--datalake-formats: iceberg` for Iceberg support
- Test Spark config with `spark.sql("SHOW CATALOGS").show()`

❌ **DON'T:**
- Use `spark.conf.set()` for static configs like `spark.sql.extensions`
- Modify catalog configs at runtime
- Assume configs will apply after SparkSession creation

### 3. Lake Formation Permissions

✅ **DO:**
- Grant Lake Formation permissions immediately after creating databases
- Use table wildcards for broad permissions: `{"Table":{"DatabaseName":"db","TableWildcard":{}}}`
- Grant `--permissions-with-grant-option` for roles managing Iceberg metadata
- Verify permissions before running jobs: `aws lakeformation list-permissions`

❌ **DON'T:**
- Assume IAM permissions are sufficient (Lake Formation overrides IAM)
- Grant permissions after jobs fail (grant upfront)
- Forget to grant permissions on both databases AND tables

### 4. Job Orchestration

✅ **DO:**
- Define explicit dependencies between jobs that read each other's output
- Use Airflow task dependencies or Glue Workflow triggers
- Add retry logic for transient failures (catalog propagation delays)
- Test jobs individually before running full pipeline

❌ **DON'T:**
- Run jobs in parallel when there are dependencies
- Rely on timing/luck for race conditions
- Skip dependency checks in scripts

### 5. Debugging Workflow

✅ **DO:**
- Read CloudWatch Logs immediately after failures
- Check Glue job run history: `aws glue get-job-run --job-name X --run-id Y`
- Verify infrastructure (S3 buckets, Glue databases, IAM roles, LF permissions) before running jobs
- Document issues and resolutions in TROUBLESHOOTING.md

❌ **DON'T:**
- Retry failed jobs without understanding the error
- Assume the same fix works for all similar errors
- Skip verification steps after making changes

---

## Quick Reference: Debugging Commands

### Check Glue Job Status

```bash
# Get job run status
aws glue get-job-run \
  --job-name JOBNAME \
  --run-id RUNID \
  --query 'JobRun.[JobRunState,ExecutionTime,ErrorMessage]' \
  --output json

# List recent job runs
aws glue get-job-runs --job-name JOBNAME --max-results 10
```

### Check Lake Formation Permissions

```bash
# List permissions for a principal
aws lakeformation list-permissions \
  --resource '{"Database":{"Name":"DATABASE"}}' \
  --query 'PrincipalResourcePermissions[?Principal.DataLakePrincipalIdentifier==`PRINCIPAL_ARN`]'

# List all permissions on a database
aws lakeformation list-permissions \
  --resource '{"Database":{"Name":"DATABASE"}}'
```

### Check Glue Data Catalog

```bash
# List databases
aws glue get-databases --query 'DatabaseList[*].Name'

# List tables in a database
aws glue get-tables --database-name DATABASE --query 'TableList[*].[Name,StorageDescriptor.Location]'

# Get table details
aws glue get-table --database-name DATABASE --name TABLE
```

### Check S3 Data

```bash
# List files in Bronze/Silver/Gold zones
aws s3 ls s3://BUCKET/bronze/ --recursive --human-readable
aws s3 ls s3://BUCKET/silver/ --recursive --human-readable
aws s3 ls s3://BUCKET/gold/ --recursive --human-readable

# Check Iceberg metadata structure
aws s3 ls s3://BUCKET/silver/TABLE/metadata/ --recursive
```

### Check CloudWatch Logs

```bash
# List log groups
aws logs describe-log-groups --query 'logGroups[?contains(logGroupName, `glue`)].logGroupName'

# Tail logs for a job
aws logs tail "/aws-glue/jobs/error" --follow --filter-pattern "JOBNAME"
```

---

## Contact & Support

**Workload Path:**
```
/path/to/claude-data-operations/workloads/us_mutual_funds_etf/
```

**Related Documentation:**
- `README.md` — Workload overview
- `DEPLOYMENT_SUMMARY_2026-03-16.md` — Full deployment log
- `COMPLETE_DEPLOYMENT_INSTRUCTIONS.md` — Step-by-step deployment guide
- `CHECKPOINT_2026-03-16_13-19.md` — Pipeline checkpoint (pause/resume)

**AWS Console Links:**
- S3: https://s3.console.aws.amazon.com/s3/buckets/your-datalake-bucket
- Glue Jobs: https://console.aws.amazon.com/glue/home?region=us-east-1#etl:tab=jobs
- Glue Data Catalog: https://console.aws.amazon.com/glue/home?region=us-east-1#catalog:tab=databases
- Lake Formation: https://console.aws.amazon.com/lakeformation/home?region=us-east-1
- CloudWatch Logs: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups

**Questions?**
- Data Engineering: data-eng@company.com
- Slack: #data-pipeline-alerts
- AWS Support: Open ticket in AWS Console

---

**Document Version:** 1.0
**Last Updated:** March 16, 2026 at 14:45 EST
**Pipeline Status:** ✅ Silver zone complete, ready for Gold zone
