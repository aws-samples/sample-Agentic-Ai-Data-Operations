# PROMPT 07: Fix Iceberg Glue Integration

**Purpose**: Fix AWS Glue ETL scripts to properly use Apache Iceberg tables with Glue Data Catalog

**When to Use**:
- Glue jobs fail with "Failed to find data source: iceberg"
- Jobs fail with "Table not found" or catalog errors
- Using Iceberg format but scripts write to S3 paths instead of catalog tables
- Lake Formation permission issues

---

## Problem

When writing Iceberg tables in AWS Glue, using `.save(s3_path)` doesn't work with the Glue Data Catalog. The scripts must use `.saveAsTable(catalog.database.table)` instead.

**Common Errors**:
- `Failed to find data source: iceberg`
- `Table 's3://bucket/path'.'' not found`
- `Insufficient Lake Formation permission(s)`

---

## Solution Pattern

### 1. Update Write Operations

**❌ OLD (Doesn't Work)**:
```python
df.write \
    .format("iceberg") \
    .mode("overwrite") \
    .save(args['silver_path'])
```

**✅ NEW (Works with Glue Catalog)**:
```python
# Define table name in catalog
table_name = "glue_catalog.financial_portfolios_db.silver_stocks"

# Write to catalog table
df.write \
    .format("iceberg") \
    .mode("overwrite") \
    .saveAsTable(table_name)

print(f"Table written: {table_name}")
```

**⚠️ Partitioning Warning (Glue 4.0)**:
Do NOT use `.partitionBy()` with `.saveAsTable()` in Glue 4.0. It causes `ClusteredWriter` errors:
```
java.lang.IllegalStateException: Incoming records violate the writer assumption
that records are clustered by spec and by partition within each spec.
```
Write unpartitioned tables instead. Add partitioning later via `ALTER TABLE` in Athena if needed.

### 2. Update Read Operations

**❌ OLD (Reads S3 Path)**:
```python
df = glue_context.create_dynamic_frame.from_options(
    connection_type="s3",
    connection_options={"paths": [args['silver_path']]},
    format="parquet"
).toDF()
```

**✅ NEW (Reads Catalog Table)**:
```python
spark = glue_context.spark_session
table_name = "glue_catalog.financial_portfolios_db.silver_stocks"
df = spark.table(table_name)

print(f"Read from {table_name}: {df.count()} rows")
```

### 2a. CRITICAL: Verify Script Upload Path

**⚠️ #1 cause of "nothing works" debugging loops**: Uploading scripts to the wrong S3 path.

```bash
# Check where the Glue job actually loads the script from:
aws glue get-job --job-name MY_JOB --query 'Job.Command.ScriptLocation' --output text
# Example output: s3://bucket/scripts/workload/my_script.py

# Upload to THAT EXACT PATH — not a subdirectory:
aws s3 cp my_script.py s3://bucket/scripts/workload/my_script.py

# WRONG (different path!):
aws s3 cp my_script.py s3://bucket/scripts/workload/transform/my_script.py
```

If the paths don't match, the job runs the OLD script and all your fixes are silently ignored.

### 3. Configure Glue Job Parameters

**Add Iceberg Configuration**:
```python
--datalake-formats: iceberg
--conf: spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions --conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog --conf spark.sql.catalog.glue_catalog.warehouse=s3://bucket/path/ --conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog
```

**Update via AWS CLI**:
```bash
aws glue update-job --job-name my_job --job-update '{
  "DefaultArguments": {
    "--datalake-formats": "iceberg",
    "--conf": "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions --conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog --conf spark.sql.catalog.glue_catalog.warehouse=s3://bucket/gold/ --conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog"
  }
}'
```

### 4. Grant Lake Formation Permissions

**Required Permissions**:
```python
import boto3

lakeformation = boto3.client('lakeformation')

# Get Glue role ARN
glue = boto3.client('glue')
response = glue.get_job(JobName='my_job')
role_arn = response['Job']['Role']

# Grant CREATE_TABLE on database
lakeformation.grant_permissions(
    Principal={'DataLakePrincipalIdentifier': role_arn},
    Resource={'Database': {'Name': 'my_database'}},
    Permissions=['CREATE_TABLE', 'ALTER', 'DROP']
)

# Grant ALL on tables
lakeformation.grant_permissions(
    Principal={'DataLakePrincipalIdentifier': role_arn},
    Resource={'Table': {'DatabaseName': 'my_database', 'TableWildcard': {}}},
    Permissions=['ALL']
)
```

---

## Complete Example

### Bronze → Silver Script (Iceberg-Compatible)

```python
#!/usr/bin/env python3
"""
Bronze → Silver transformation with Iceberg table writes
"""
import sys
from datetime import datetime
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F

# Get job parameters
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'bronze_path', 'database_name', 'table_name'])

# Initialize Glue context
sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args['JOB_NAME'], args)

# Read from Bronze (CSV)
bronze_df = glue_context.create_dynamic_frame.from_options(
    connection_type="s3",
    connection_options={"paths": [args['bronze_path']]},
    format="csv",
    format_options={"withHeader": True}
).toDF()

# Transformations
transformed_df = bronze_df \
    .dropDuplicates(['primary_key']) \
    .filter(F.col('important_column').isNotNull())

# Write to Silver as Iceberg table in Glue Catalog
table_name = f"glue_catalog.{args['database_name']}.{args['table_name']}"
transformed_df.write \
    .format("iceberg") \
    .mode("overwrite") \
    .saveAsTable(table_name)

print(f"✅ Silver table written: {table_name}")
print(f"   Rows: {transformed_df.count()}")

job.commit()
```

### Silver → Gold Script (Iceberg-Compatible)

```python
#!/usr/bin/env python3
"""
Silver → Gold transformation with Iceberg reads and writes
"""
import sys
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F

# Get job parameters
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'database_name'])

# Initialize
sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args['JOB_NAME'], args)

# Read from Silver (Iceberg)
silver_table = f"glue_catalog.{args['database_name']}.silver_data"
silver_df = spark.table(silver_table)

# Transformations
gold_df = silver_df \
    .groupBy("category") \
    .agg(F.sum("amount").alias("total_amount"))

# Write to Gold (Iceberg)
gold_table = f"glue_catalog.{args['database_name']}.gold_summary"
gold_df.write \
    .format("iceberg") \
    .mode("overwrite") \
    .saveAsTable(gold_table)

print(f"✅ Gold table written: {gold_table}")
print(f"   Rows: {gold_df.count()}")

job.commit()
```

---

## Deployment Checklist

Use this checklist when deploying Iceberg tables to AWS Glue:

### 1. Update All ETL Scripts
- [ ] Replace `.save(s3_path)` with `.saveAsTable(catalog.db.table)`
- [ ] Replace S3 reads with `spark.table(catalog.db.table)`
- [ ] Remove ALL `.partitionBy()` calls (causes ClusteredWriter errors in Glue 4.0)
- [ ] Replace `args['path']` in lineage sections with catalog table name strings
- [ ] Remove obsolete S3 path params from `getResolvedOptions` (keep only `JOB_NAME` + bronze_path for bronze jobs)
- [ ] Add print statements showing table names
- [ ] Test locally with `--local` mode first

### 2. Upload Scripts to S3 (⚠️ VERIFY PATH FIRST)
```bash
# CRITICAL: Check where each job loads its script from
for job in $(aws glue list-jobs --query 'JobNames[?contains(@,`my_workload`)]' --output text); do
  echo "$job: $(aws glue get-job --job-name $job --query 'Job.Command.ScriptLocation' --output text)"
done

# Upload to the EXACT paths shown above — not a subdirectory
aws s3 cp workloads/my_workload/scripts/transform/my_script.py \
  s3://my-bucket/scripts/my_workload/my_script.py
```

### 3. Configure Glue Jobs
```bash
# For each job, add Iceberg parameters
aws glue update-job --job-name my_job --job-update '{
  "DefaultArguments": {
    "--datalake-formats": "iceberg",
    "--conf": "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions ..."
  }
}'
```

### 4. Grant Lake Formation Permissions
```bash
# Run Python script from Step 4 above
python3 scripts/grant_lf_permissions.py
```

### 5. Test Jobs
```bash
# Start jobs one at a time
aws glue start-job-run --job-name my_bronze_to_silver_job

# Wait 2 minutes, check status
aws glue get-job-runs --job-name my_bronze_to_silver_job --max-results 1

# If successful, start dependent jobs
aws glue start-job-run --job-name my_silver_to_gold_job
```

### 6. Verify Tables in Athena
```sql
-- Check tables exist
SHOW TABLES IN my_database;

-- Query data
SELECT * FROM my_database.silver_data LIMIT 10;

-- Check Iceberg metadata
SELECT * FROM my_database.silver_data$snapshots;
```

---

## Troubleshooting

### Error: "Failed to find data source: iceberg"

**Cause**: Missing `--datalake-formats` parameter

**Fix**:
```bash
aws glue update-job --job-name my_job --job-update '{
  "DefaultArguments": {
    "--datalake-formats": "iceberg"
  }
}'
```

### Error: "Table 's3://bucket/path'.'' not found"

**Cause**: Using `.save(s3_path)` instead of `.saveAsTable()`

**Fix**: Update script to use `.saveAsTable("glue_catalog.db.table")`

### Error: "Insufficient Lake Formation permission(s)"

**Cause**: Glue role lacks Lake Formation permissions

**Fix**: Grant CREATE_TABLE and ALL permissions (see Step 4 above)

### Error: "Incoming records violate the writer assumption that records are clustered"

**Cause**: Using `.partitionBy()` with `.saveAsTable()` in Glue 4.0. The Iceberg `ClusteredWriter` expects data pre-sorted by partition key, but Spark doesn't guarantee this.

**Fix**: Remove `.partitionBy()` entirely. Write unpartitioned Iceberg tables. Add partitioning later via Athena `ALTER TABLE` if needed for query performance.

### Error: Fixes not taking effect (same error after code changes)

**Cause**: Script uploaded to wrong S3 path. Glue job's `ScriptLocation` doesn't match where you uploaded.

**Fix**:
```bash
# Check the actual path:
aws glue get-job --job-name MY_JOB --query 'Job.Command.ScriptLocation' --output text
# Upload to THAT path, not a subdirectory
```

### Error: "RESOURCE_NUMBER_LIMIT_EXCEEDED" or concurrent runs

**Cause**: Jobs configured with `MaxConcurrentRuns=1`

**Fix**: Wait for previous run to complete, or increase limit:
```bash
aws glue update-job --job-name my_job --job-update '{
  "MaxConcurrentRuns": 3
}'
```

---

## Key Differences: S3 Path vs Catalog Table

| Aspect | S3 Path (`.save()`) | Catalog Table (`.saveAsTable()`) |
|--------|---------------------|----------------------------------|
| Write | `.save("s3://bucket/path/")` | `.saveAsTable("glue_catalog.db.table")` |
| Read | `spark.read.parquet("s3://...")` | `spark.table("glue_catalog.db.table")` |
| Catalog Registration | Manual (external table) | Automatic |
| Time Travel | ❌ Not available | ✅ Built-in (`$snapshots`) |
| ACID Transactions | ❌ No | ✅ Yes |
| Schema Evolution | ❌ Manual | ✅ Automatic |
| Athena Queries | ✅ Works | ✅ Works (with metadata) |
| Lake Formation | Manual grants | ✅ Integrated |

---

## Naming Convention

**Catalog Hierarchy**:
```
glue_catalog                  # Spark catalog name (fixed)
└── financial_portfolios_db   # Database name
    ├── silver_stocks         # Table: Bronze→Silver output
    ├── silver_portfolios
    ├── silver_positions
    ├── gold_dim_stocks       # Table: Silver→Gold output
    ├── gold_dim_portfolios
    ├── gold_fact_positions
    └── gold_portfolio_summary
```

**Table Name Format**:
- Bronze→Silver: `silver_{table_name}`
- Silver→Gold dimensions: `gold_dim_{table_name}`
- Silver→Gold facts: `gold_fact_{table_name}`
- Aggregates: `gold_{aggregate_name}`

---

## Testing Locally

Before deploying, test scripts locally with pandas fallback:

```bash
python3 workloads/my_workload/scripts/transform/bronze_to_silver.py \
  --local \
  --bronze_path ./sample_data/input.csv \
  --silver_path ./output/silver/data.parquet \
  --database_name financial_portfolios_db \
  --table_name silver_data
```

Local mode bypasses Iceberg and uses Parquet for testing transformations.

---

## Expected Outcome

After applying this pattern:

✅ **Before**:
- ❌ Jobs fail with Iceberg errors
- ❌ Tables not registered in catalog
- ❌ No time travel or ACID
- ❌ Lake Formation permission issues

✅ **After**:
- ✅ Jobs succeed and write to Glue catalog
- ✅ Tables queryable in Athena
- ✅ Time travel enabled (`$snapshots`, `$history`)
- ✅ ACID transactions working
- ✅ Lake Formation permissions granted
- ✅ Automated daily pipeline ready

---

## Related Prompts

- **PROMPT 02**: Generate synthetic test data
- **PROMPT 03**: Onboard new dataset with Bronze→Silver→Gold
- **PROMPT 05**: Create QuickSight dashboard on Gold tables

---

**Generated**: 2026-03-20
**Workload**: financial_portfolios
**Status**: ✅ Tested and validated with AWS Glue 4.0 + Iceberg
