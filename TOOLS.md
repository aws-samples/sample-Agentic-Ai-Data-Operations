# TOOLS.md — AWS Tooling Reference for Agentic Data Onboarding

> Maps each agent and phase to the specific AWS services and tools to use.
> SKILLS.md defines **what** each agent does. This file defines **which tool** to use for each step.

---

## MCP-First Rule (Global)

**For every AWS operation, use the corresponding MCP server tool FIRST.** Only fall back to AWS CLI (`aws` commands in Bash) or Boto3 if:
1. The MCP server tool is **not available** (e.g., running in a sub-agent context where MCP is inaccessible)
2. The MCP server tool **returns an error** that cannot be resolved

**Why**: MCP server tools provide structured, auditable, permission-controlled access to AWS services. Raw CLI/Boto3 bypasses these controls.

**Sub-agent limitation**: Sub-agents spawned via the `Agent` tool do NOT have MCP access. They must generate scripts and config files only. The **main conversation** (Data Onboarding Agent) executes all AWS deployment operations via MCP after sub-agents return.

| Context | MCP Available? | Action |
|---|---|---|
| Main conversation | Yes | Use MCP tools directly |
| Sub-agent (Agent tool) | **No** | Generate scripts/configs only — do NOT execute AWS operations |
| Bash fallback | N/A | Only when MCP unavailable or errored — log why fallback was needed |

### MCP Server → AWS Service Mapping

| MCP Server | AWS Services | When to Use |
|---|---|---|
| `aws-dataprocessing` | Glue Crawlers, Glue ETL, Glue Data Catalog, Athena | Schema discovery, profiling, transforms, quality checks, catalog ops |
| `s3-tables` | S3 Tables (Iceberg) | Silver/Gold zone storage, Iceberg table management |
| `sagemaker-catalog` | SageMaker Catalog (custom metadata) | Business context, column roles, PII flags, relationships |
| `core` | S3, KMS, Secrets Manager | Bronze storage, encryption, secrets |
| `lambda` | Lambda | Serverless compute, API extraction |
| `stepfunctions` | Step Functions | Workflow orchestration (alternative to Airflow) |
| `cloudwatch` | CloudWatch | Monitoring, metrics, alarms |
| `sns-sqs` | SNS, SQS | Alerting, notifications |
| `eventbridge` | EventBridge | Workflow triggers, event-driven scheduling |
| `redshift` | Redshift | Query engine (Gold zone alternative) |
| `iam` | IAM | Role/policy management |
| `cloudtrail` | CloudTrail | Audit logging, security investigation |
| `cost-explorer` | Cost Explorer | Cost tracking, budget analysis |
| `verified-permissions` | Amazon Verified Permissions | Cedar policy evaluation, agent authorization, guardrail enforcement |
| `lakeformation` | Lake Formation | Column-level access control, permissions |
| `dynamodb` | DynamoDB | Operational state tables, API serving cache |

---

## Quick Reference

| Task | Primary Tool | Fallback | MCP Server |
|---|---|---|---|
| Schema discovery (S3) | AWS Glue Crawler | Manual Athena DDL | `aws-dataprocessing` |
| Schema discovery (DB) | AWS Glue JDBC Crawler | Direct JDBC metadata query | `aws-dataprocessing` |
| Data profiling (S3) | AWS Athena (query in place) | Glue ETL job on sample | `aws-dataprocessing` |
| Data profiling (DB) | Source database SQL | AWS Glue JDBC connection | `aws-dataprocessing` |
| Data catalog | AWS Glue Data Catalog | SageMaker Lakehouse Catalog API | `aws-dataprocessing` |
| Business context store | SageMaker Catalog (custom metadata columns) | — | `sagemaker-catalog` (custom) |
| Bronze storage | Amazon S3 (raw source format, partitioned) | — | `core` (S3 APIs) |
| Silver storage | Amazon S3 Tables (Apache Iceberg) | — | `s3-tables` |
| Gold storage | Amazon S3 Tables (Iceberg default; format per discovery) | — | `s3-tables` |
| Transformations | AWS Glue ETL (PySpark) | Athena CTAS (no lineage) | `aws-dataprocessing` |
| **Data Lineage** | **AWS Glue Data Lineage** | **None — always Glue** | `aws-dataprocessing` |
| Quality checks | AWS Glue Data Quality | Custom Athena SQL checks | `aws-dataprocessing` |
| Orchestration | Apache Airflow (MWAA) | AWS Step Functions | `stepfunctions` |
| Workflow triggers | Airflow Scheduler / S3 Event | EventBridge | `eventbridge` (custom) |
| Encryption | AWS KMS | — | `core` (KMS APIs) |
| Secrets | AWS Secrets Manager | Airflow Connections | `core` (Secrets Manager) |
| Monitoring | Amazon CloudWatch | Airflow UI metrics | `cloudwatch` |
| Alerting | Amazon SNS → Slack/Email | Airflow on_failure_callback | `sns-sqs` |
| OWL + R2RML generation (ontology staging) | rdflib (local Python) | — | None (local) |
| Ontology publish (RDF/SPARQL, VKG) | **ORION** (external, not yet deployed) | — | **Future** — requires ORION deployment |
| Serverless compute | AWS Lambda | — | `lambda` |
| Query engine (Gold) | Amazon Athena | Redshift Spectrum | `aws-dataprocessing` or `redshift` |

---

## Phase 2: Source Validation Tools

### Duplicate Detection

No specific AWS tool — this is a local file scan of `workloads/*/config/source.yaml`. Use file reads and string matching.

### Source Connectivity Check

| Source Type | Tool | How to Test |
|---|---|---|
| **S3 bucket** | AWS CLI / Boto3 | `aws s3 ls s3://{bucket}/{prefix}/ --max-items 1` — confirms bucket exists and IAM has access |
| **RDS / Aurora** | AWS Glue JDBC Connection | Create a Glue Connection, run "Test connection" — validates VPC, security groups, credentials |
| **Redshift** | AWS Glue JDBC Connection | Same as RDS — test via Glue Connection |
| **DynamoDB** | Boto3 | `describe_table()` — confirms table exists and IAM has access |
| **API endpoint** | Python `requests` | HTTP GET to health/ping endpoint — confirms reachability |
| **On-prem database** | AWS Glue JDBC via VPN/DirectConnect | Test Glue Connection through VPC with appropriate route |
| **Kafka / MSK** | Boto3 MSK client | `list_clusters()` and `describe_cluster()` — confirms access |

```python
# Example: S3 connectivity check
import boto3
s3 = boto3.client('s3')
try:
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
    print(f"✓ Source reachable. Objects found: {response.get('KeyCount', 0)}")
except s3.exceptions.NoSuchBucket:
    print("✗ Bucket does not exist")
except Exception as e:
    print(f"✗ Access denied or error: {e}")
```

---

## Phase 3: Profiling & Metadata Discovery Tools

### Step 3.1: Schema Discovery — AWS Glue Crawler

Use AWS Glue Crawler as the primary schema discovery tool. It auto-detects schema, format, partitioning, and registers results in the Glue Data Catalog.

**When to use Glue Crawler**:
- Source is in S3 (CSV, JSON, Parquet, Avro, ORC)
- Source is a JDBC database (RDS, Aurora, Redshift, on-prem via VPN)
- You need automatic partition detection
- You want schema registered in the Glue Data Catalog automatically

**When NOT to use Glue Crawler** (use alternatives):
- Source is a REST API → use custom Python extraction + manual schema definition
- Source is a streaming system (Kafka/Kinesis) → use schema registry instead
- You need immediate results → Crawler can take minutes; use Athena DDL for speed

**Glue Crawler configuration**:

```python
# Example: Create and run a Glue Crawler for a new source
import boto3
glue = boto3.client('glue')

crawler_name = f"{workload_name}_source_crawler"

glue.create_crawler(
    Name=crawler_name,
    Role='arn:aws:iam::{account}:role/GlueCrawlerRole',  # From Airflow Variable
    DatabaseName=f"{workload_name}_db",
    Targets={
        'S3Targets': [{
            'Path': f's3://{source_bucket}/{source_prefix}/',
            'Exclusions': ['_tmp/**', '_spark_metadata/**']
        }]
        # OR for JDBC:
        # 'JdbcTargets': [{
        #     'ConnectionName': f'{workload_name}_jdbc_conn',
        #     'Path': 'database/schema/table'
        # }]
    },
    SchemaChangePolicy={
        'UpdateBehavior': 'UPDATE_IN_DATABASE',
        'DeleteBehavior': 'LOG'
    },
    RecrawlPolicy={
        'RecrawlBehavior': 'CRAWL_NEW_FOLDERS_ONLY'
    },
    Configuration=json.dumps({
        "Version": 1.0,
        "Grouping": {"TableGroupingPolicy": "CombineCompatibleSchemas"}
    }),
    Tags={
        'workload': workload_name,
        'managed-by': 'data-onboarding-agent'
    }
)

glue.start_crawler(Name=crawler_name)
```

**After crawler completes**, read the schema from the Glue Data Catalog:

```python
response = glue.get_table(
    DatabaseName=f"{workload_name}_db",
    Name=table_name
)
columns = response['Table']['StorageDescriptor']['Columns']
partitions = response['Table']['PartitionKeys']
location = response['Table']['StorageDescriptor']['Location']
format = response['Table']['Parameters'].get('classification', 'unknown')
```

### Step 3.2: 5% Sample Profiling — Amazon Athena

Use Athena to query the source data in place (S3) without moving it. Run profiling on a ~5% sample using `TABLESAMPLE` or `LIMIT` with row-count math.

**Profiling query template**:

```sql
-- Step 1: Get total row count
SELECT COUNT(*) AS total_rows FROM "{database}"."{table}";

-- Step 2: Profile on 5% sample
WITH sample AS (
    SELECT *
    FROM "{database}"."{table}"
    TABLESAMPLE BERNOULLI(5)
    -- If TABLESAMPLE not supported, use:
    -- WHERE MOD(ABS(checksum(CAST(rand() AS VARCHAR))), 100) < 5
),
profiled AS (
    SELECT
        COUNT(*) AS sample_rows,

        -- Per-column profiling (repeat for each column)
        -- Numeric column example:
        COUNT(revenue) AS revenue_non_null,
        COUNT(*) - COUNT(revenue) AS revenue_nulls,
        ROUND(100.0 * (COUNT(*) - COUNT(revenue)) / COUNT(*), 2) AS revenue_null_pct,
        COUNT(DISTINCT revenue) AS revenue_distinct,
        MIN(revenue) AS revenue_min,
        MAX(revenue) AS revenue_max,
        ROUND(AVG(revenue), 2) AS revenue_avg,

        -- String column example:
        COUNT(DISTINCT region) AS region_distinct,
        ROUND(100.0 * (COUNT(*) - COUNT(region)) / COUNT(*), 2) AS region_null_pct,

        -- Date column example:
        MIN(order_date) AS order_date_min,
        MAX(order_date) AS order_date_max,
        COUNT(DISTINCT order_date) AS order_date_distinct
    FROM sample
)
SELECT * FROM profiled;
```

**Top-N values query** (for low-cardinality columns):

```sql
-- Get top values for dimension columns
SELECT region, COUNT(*) AS cnt,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) AS pct
FROM "{database}"."{table}"
TABLESAMPLE BERNOULLI(5)
GROUP BY region
ORDER BY cnt DESC
LIMIT 10;
```

**PII pattern detection query**:

```sql
-- Detect email patterns
SELECT
    'email_column' AS column_name,
    COUNT(*) AS total,
    SUM(CASE WHEN REGEXP_LIKE(email_column, '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z]{2,}') THEN 1 ELSE 0 END) AS email_matches,
    ROUND(100.0 * SUM(CASE WHEN REGEXP_LIKE(email_column, '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z]{2,}') THEN 1 ELSE 0 END) / COUNT(*), 2) AS match_pct
FROM "{database}"."{table}"
TABLESAMPLE BERNOULLI(5);

-- Detect SSN patterns (XXX-XX-XXXX)
-- Detect phone patterns
-- Detect credit card patterns (Luhn check on 13-19 digit numbers)
```

**Athena configuration**:

```python
import boto3
athena = boto3.client('athena')

response = athena.start_query_execution(
    QueryString=profiling_sql,
    QueryExecutionContext={
        'Database': f'{workload_name}_db',
        'Catalog': 'AwsDataCatalog'
    },
    ResultConfiguration={
        'OutputLocation': f's3://{athena_results_bucket}/profiling/{workload_name}/',
        'EncryptionConfiguration': {
            'EncryptionOption': 'SSE_KMS',
            'KmsKey': kms_key_alias  # From Airflow Variable
        }
    },
    WorkGroup=workgroup  # From Airflow Variable
)
```

### For Database Sources (non-S3)

If the source is a database (not S3), use the same profiling SQL patterns but execute via:
1. **AWS Glue JDBC connection** → run profiling as a Glue ETL job
2. **Direct database connection** → execute profiling SQL natively on the source DB
3. Write results to S3 as Parquet for the metadata report

---

## Bronze Zone Tools

| Step | Tool | Details |
|---|---|---|
| Raw data ingestion (S3→S3) | AWS S3 Copy / Sync | `aws s3 sync` or Boto3 `copy_object` — preserves original format |
| Raw data ingestion (DB→S3) | AWS Glue ETL Job | PySpark job reads from JDBC, writes to S3 (Parquet or JSON — raw extract, not transformed) |
| Raw data ingestion (API→S3) | AWS Lambda + S3 Put | Lambda calls API, writes response to S3 |
| Checksum calculation | Python hashlib / S3 ETag | Calculate MD5/SHA256 on ingested files for integrity |
| Partitioning | Glue ETL / Athena CTAS | Partition by ingestion date: `year={}/month={}/day={}` |
| Catalog registration | AWS Glue Crawler | Re-crawl Bronze location after ingestion |
| Immutability enforcement | S3 Object Lock | Enable Object Lock in Governance mode on Bronze bucket |

```python
# Bronze ingestion: S3 Object Lock for immutability
s3.put_object_lock_configuration(
    Bucket=bronze_bucket,
    ObjectLockConfiguration={
        'ObjectLockEnabled': 'Enabled',
        'Rule': {
            'DefaultRetention': {
                'Mode': 'GOVERNANCE',
                'Days': retention_days  # From config
            }
        }
    }
)
```

---

## Silver Zone Tools — Apache Iceberg on Amazon S3 Tables

Silver zone is **always Apache Iceberg tables** on Amazon S3 Tables, registered in Glue Data Catalog.

| Step | Tool | Details |
|---|---|---|
| Bronze→Silver transform | AWS Glue ETL (PySpark + Iceberg) | Read Bronze raw data, apply cleaning rules, write as Iceberg table. **`--enable-data-lineage: true` required.** |
| Iceberg table creation | Spark SQL / Athena DDL | `CREATE TABLE ... USING iceberg` with S3 Tables catalog |
| Schema validation | Glue ETL schema check | Compare DataFrame schema against Glue Catalog Iceberg schema |
| Deduplication | Spark SQL / Iceberg MERGE INTO | `MERGE INTO silver USING bronze ON key WHEN MATCHED ...` |
| Data cleaning | Glue ETL transforms | DynamicFrame `apply_mapping`, `resolveChoice`, `drop_nulls` |
| Partitioning | Iceberg partition spec | Partition by business dimensions (Iceberg hidden partitioning) |
| Compaction | Iceberg maintenance | `CALL system.rewrite_data_files(table => ...)` for file optimization |
| Quality check | AWS Glue Data Quality | Run DQDL rules against Silver Iceberg table |
| Catalog registration | Glue Data Catalog | Automatic — Iceberg tables register via S3 Tables catalog integration |
| Time-travel | Iceberg snapshots | `SELECT * FROM silver.table FOR SYSTEM_TIME AS OF timestamp` |

**Iceberg table creation example** (Spark SQL via Glue ETL):

```sql
CREATE TABLE s3tablesbucket.silver_db.sales_transactions (
    order_id STRING,
    customer_id STRING,
    order_date DATE,
    region STRING,
    product_category STRING,
    quantity INT,
    unit_price DOUBLE,
    discount_pct DOUBLE,
    revenue DOUBLE,
    payment_method STRING,
    status STRING
)
USING iceberg
PARTITIONED BY (region, days(order_date))
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
```

**Iceberg MERGE INTO for upserts** (Silver updates):

```sql
MERGE INTO silver_db.sales_transactions AS target
USING bronze_staging AS source
ON target.order_id = source.order_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

**Glue Data Quality rule example** (DQDL syntax):

```
Rules = [
    Completeness "email" > 0.95,
    Uniqueness "order_id" = 1.0,
    ColumnValues "revenue" between 0 and 100000,
    CustomSql "SELECT COUNT(*) FROM silver_table WHERE order_date > ship_date" = 0
]
```

---

## Gold Zone Tools — Format Based on Discovery

Gold zone format is determined during Phase 1 discovery (see SKILLS.md). Default is Iceberg.

| Step | Tool | Details |
|---|---|---|
| Silver→Gold transform | AWS Glue ETL (PySpark + Iceberg) | Read Silver Iceberg, aggregate/curate, write to Gold Iceberg. **`--enable-data-lineage: true` required.** |
| Flat table | Spark SQL / Iceberg | Single wide denormalized Iceberg table |
| Star schema — fact table | Spark SQL / Iceberg | Fact table with FK references to dimension tables |
| Star schema — dimension tables | Spark SQL / Iceberg | Separate Iceberg tables for each dimension (customer, product, region) |
| SCD Type 2 | Iceberg MERGE INTO | Compare incoming vs existing, insert new + expire old records |
| Materialized views | Athena CTAS / Iceberg | Pre-aggregated views for dashboard latency requirements |
| Compaction | Iceberg maintenance | `rewrite_data_files` for query performance optimization |
| Quality check | AWS Glue Data Quality | Stricter rules (score >= 0.95) |
| Catalog registration | Glue Data Catalog | Automatic via S3 Tables catalog integration |

**Gold zone format decision tree** (from Phase 1 discovery):

```
Query latency?
├── Sub-second → Iceberg + materialized views (or Redshift for extreme cases)
├── Seconds → Iceberg tables with partition pruning
└── Minutes → Iceberg or Parquet

Data size?
├── < 1 GB → flat Iceberg table
├── 1-100 GB → partitioned Iceberg, consider star schema
└── 100 GB+ → star schema in Iceberg, partition pruning, Redshift Spectrum

Read pattern?
├── Dashboards → pre-aggregated materialized views
├── Ad-hoc SQL → Iceberg (Athena)
├── ML features → Iceberg with columnar access
└── API serving → DynamoDB/cache on top of Iceberg
```

---

## Orchestration Tools

| Step | Tool | Details |
|---|---|---|
| DAG execution | Amazon MWAA (Managed Airflow) | Managed Airflow — DAGs deployed from `workloads/{name}/dags/` |
| Glue job trigger | `GlueJobOperator` | Airflow operator to start Glue ETL jobs |
| Crawler trigger | `GlueCrawlerOperator` | Airflow operator to start Glue Crawlers |
| Athena queries | `AthenaOperator` | Airflow operator to run Athena SQL |
| Quality checks | `GlueDataQualityRuleSetEvaluationRunOperator` | Airflow operator for Glue Data Quality rulesets |
| S3 sensors | `S3KeySensor` | Wait for upstream data to land in S3 |
| Cross-DAG deps | `ExternalTaskSensor` | Wait for upstream DAG/task completion |
| Alerting | `SnsPublishOperator` or callback | Send SNS → Slack/Email on failure |
| Secrets | `SecretsManagerBackend` | Airflow Secrets Backend for Secrets Manager integration |

**Airflow provider packages required**:
```
apache-airflow-providers-amazon
```

**Key Airflow operators from `apache-airflow-providers-amazon`**:

```python
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.operators.glue_crawler import GlueCrawlerOperator
from airflow.providers.amazon.aws.operators.athena import AthenaOperator
from airflow.providers.amazon.aws.operators.glue_data_quality import (
    GlueDataQualityRuleSetEvaluationRunOperator,
)
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.amazon.aws.operators.sns import SnsPublishOperator
```

---

## Metadata & Catalog Tools

| Step | Tool | Details |
|---|---|---|
| Schema registry | AWS Glue Data Catalog | Central schema store for all zones |
| **Lineage tracking** | **AWS Glue Data Lineage (native)** | **ALWAYS enable `--enable-data-lineage` on every Glue ETL job. Automatic table-level + column-level lineage via OpenLineage. Viewable in Glue Console.** |
| Classification (PII) | AWS Glue PII detection + SageMaker Catalog | Built-in PII detection in Glue; results stored as custom metadata columns |
| Business glossary | SageMaker Catalog custom metadata columns | Column roles, descriptions, business terms as custom properties on table/column |
| Business context | SageMaker Catalog custom metadata columns | Column roles (measure/dimension/temporal/identifier), PII flags, relationships — replaces DynamoDB |
| Relationship discovery | Custom profiling (Athena SQL) | Join-key candidate detection via value distribution matching |

**Glue PII detection**:

```python
# Enable Glue sensitive data detection during ETL
from awsglue.transforms import DetectPII

detected = DetectPII.apply(
    frame=dynamic_frame,
    entity_types_to_detect=["EMAIL", "PHONE_NUMBER", "SSN", "CREDIT_CARD", "IP_ADDRESS"],
    output_column_name="pii_detection_result"
)
```

---

## Glue Data Lineage (Mandatory)

**Every Glue ETL job MUST have data lineage enabled.** This is a non-negotiable requirement — no exceptions.

### How to Enable

Set the job parameter `--enable-data-lineage` to `true` on every Glue ETL job:

**Via Glue Console**: Job details → Advanced properties → Job parameters → Add `--enable-data-lineage` = `true`

**Via AWS CLI**:
```bash
aws glue create-job \
  --name "product_inventory_bronze_to_silver" \
  --role "AWS-Glue-job-role" \
  --command '{"Name":"glueetl","ScriptLocation":"s3://...","PythonVersion":"3"}' \
  --default-arguments '{
    "--enable-data-lineage": "true",
    "--enable-glue-datacatalog": "true",
    "--conf": "spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog"
  }' \
  --glue-version "4.0" \
  --number-of-workers 2 \
  --worker-type "G.1X"
```

**Via Airflow GlueJobOperator**:
```python
GlueJobOperator(
    task_id="transform_bronze_to_silver",
    job_name="product_inventory_bronze_to_silver",
    script_args={
        "--enable-data-lineage": "true",
        "--source_database": "demo_ai_agents",
        "--source_table": "bronze_product_inventory",
        "--target_s3_path": "s3://bucket/silver/product_inventory/",
    },
)
```

### What Glue Data Lineage Captures Automatically

| Level | What It Tracks | Example |
|---|---|---|
| **Table-level** | Source table → Target table relationships | `bronze_product_inventory` → `silver_product_inventory` |
| **Column-level** | Source column → Target column mappings | `bronze.unit_price` → `silver.unit_price` (passthrough) |
| **Derived columns** | Multi-source column derivations | `bronze.unit_price, bronze.cost_price` → `gold.margin` |
| **Job metadata** | Job name, run ID, start/end time, status | `job_run_id: jr_abc123`, `duration: 45s` |
| **DynamicFrame transforms** | ApplyMapping, ResolveChoice, DropNullFields | Tracks which transforms were applied |
| **Catalog registration** | Table creation/update in Glue Data Catalog | New columns added, schema changes |

### Where to View Lineage

1. **Glue Console** → Data Catalog → Tables → Select table → **Lineage** tab
2. **Glue Console** → ETL Jobs → Select job → **Data lineage** tab
3. **API**: `aws glue get-data-quality-result` and OpenLineage events in CloudWatch

### Lineage + Iceberg

When writing Iceberg tables, Glue Data Lineage also tracks:
- Iceberg snapshot IDs (links lineage to specific table versions)
- Partition evolution changes
- Schema evolution (added/removed columns)

### Rules for Lineage in This Project

1. **ALWAYS enable `--enable-data-lineage: true`** on every Glue ETL job — Bronze→Silver, Silver→Gold, any reprocessing job
2. **ALWAYS use GlueContext and DynamicFrames** (or Spark DataFrames with Glue catalog) — lineage only works with Glue-aware reads/writes
3. **ALWAYS read from Glue Catalog** (`create_dynamic_frame.from_catalog()`) — not raw S3 paths — so lineage can trace back to catalog tables
4. **ALWAYS write via Glue Catalog** (`write_dynamic_frame.from_catalog()` or Iceberg `writeTo("glue_catalog.db.table")`) — not raw S3 `save()`
5. **NEVER disable lineage** to save cost or time — lineage overhead is minimal (<5% job duration)
6. **Verify lineage after every deploy**: Check Glue Console → table → Lineage tab to confirm source→target links appear

---

## Security Tools

| Concern | Tool | Configuration |
|---|---|---|
| Encryption at rest | AWS KMS | Separate CMK per zone: `{workload}_bronze_key`, `{workload}_silver_key`, `{workload}_gold_key` |
| Encryption in transit | TLS 1.3 | Enforced on all S3, Glue, Athena, SageMaker Catalog connections |
| Secrets management | AWS Secrets Manager | Store DB credentials, API keys — never in code |
| Access control | IAM Roles + Lake Formation | Per-agent IAM roles; Lake Formation for column-level access |
| Audit logging | AWS CloudTrail + S3 access logs | Trail for API calls; S3 server access logs for data access |
| Network isolation | VPC + Security Groups | Glue jobs run in VPC; Security Groups restrict JDBC access |

---

## Monitoring & Alerting Tools

| What to Monitor | Tool | Details |
|---|---|---|
| DAG/task status | Airflow UI + CloudWatch | MWAA publishes Airflow metrics to CloudWatch |
| Glue job metrics | CloudWatch Metrics | Job duration, DPU usage, bytes read/written |
| Athena query metrics | CloudWatch Metrics | Query execution time, data scanned, cost |
| Data quality scores | Custom CloudWatch Metric | Publish quality scores as custom metrics for dashboards |
| Pipeline SLA breaches | Airflow SLA + SNS | Airflow detects SLA miss → SNS → Slack/PagerDuty |
| Cost tracking | AWS Cost Explorer tags | Tag all resources with `workload={name}` for cost allocation |

---

## Tool Selection Decision Tree

```
Is the source in S3?
├── YES → Use Glue Crawler for schema discovery
│         Use Athena for profiling (query in place)
│         Use Glue ETL for transformations
│         Write Silver/Gold as Iceberg tables on S3 Tables
│
└── NO → Is it a database (RDS/Aurora/Redshift)?
         ├── YES → Use Glue JDBC Crawler for schema discovery
         │         Use Glue JDBC Connection for profiling
         │         Use Glue ETL with JDBC source for ingestion
         │         Write Silver/Gold as Iceberg tables on S3 Tables
         │
         └── NO → Is it an API?
                  ├── YES → Use Lambda for extraction
                  │         Define schema manually from API docs
                  │         Write to S3 Bronze, then Iceberg for Silver/Gold
                  │
                  └── Is it a stream (Kafka/Kinesis)?
                       ├── YES → Use MSK/Kinesis schema registry
                       │         Use Glue Streaming ETL → Iceberg tables
                       │
                       └── Custom source → Lambda + custom connector → Iceberg tables
```
