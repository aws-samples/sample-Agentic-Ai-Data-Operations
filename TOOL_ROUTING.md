# TOOL_ROUTING.md — Tool Selection for Agentic Data Onboarding

> **Read this file FIRST before any pipeline operation.**
> It tells you WHICH tool to pick and WHY, with code examples for implementation.
> For per-phase runtime guardrails and exact MCP tool names, see → [MCP_GUARDRAILS.md](./MCP_GUARDRAILS.md)
> Canonical server list: [tool-registry/servers.yaml](./tool-registry/servers.yaml)

---

## Step 1 — Am I in a Sub-Agent or Main Conversation?

This is the most important question. Answer it before anything else.

| Context | What I can do |
|---|---|
| **Main conversation** (Data Onboarding Agent) | Use MCP tools directly + run CLI/Bash fallback |
| **Sub-agent** (spawned via `Agent` tool) | **Generate scripts and config files ONLY** — no MCP, no AWS execution |
| **Bash fallback** | Only when MCP tool is unavailable or errored — log why: `Warning: MCP fallback — {server} not loaded for {operation}` |

**If you are a sub-agent: stop reading this file after Step 1. You write files. The main conversation deploys.**

---

## Step 2 — MCP Server Status

These are the **13 configured** MCP servers (matching `.mcp.json`). Do not assume others work.

| Category | MCP Server | Tools Available | Use For |
|---|---|---|---|
| **REQUIRED** | `glue-athena` | `create_database`, `get_table`, `get_tables`, `create_crawler`, `start_crawler`, `start_job_run`, `get_job_run`, `athena_query` | Glue catalog + Athena queries (custom FastMCP) |
| **REQUIRED** | `lakeformation` | `create_lf_tag`, `add_lf_tags_to_resource`, `grant_permissions`, `revoke_permissions`, `batch_grant_permissions`, `get_resource_lf_tags` | LF-Tags, TBAC grants, column-level security (custom FastMCP) |
| **REQUIRED** | `iam` | `list_roles`, `simulate_principal_policy`, `list_role_policies`, `get_role_policy`, `put_role_policy`, `create_role` | Role lookup, permission simulation, policy management |
| WARN | `cloudtrail` | `lookup_events`, `lake_query`, `list_event_data_stores`, `get_query_results`, `get_query_status` | Audit verification, security checks, compliance |
| WARN | `redshift` | `list_clusters`, `list_databases`, `list_schemas`, `list_tables`, `list_columns`, `execute_query` | Schema verification, Gold zone validation, catalog checks via Spectrum |
| WARN | `core` | S3, KMS, Secrets Manager | S3 operations, KMS key management, secrets *(slow startup)* |
| WARN | `s3-tables` | S3 Tables (Iceberg) operations | S3 Tables management, Iceberg table operations |
| WARN | `pii-detection` | `detect_pii_in_table`, `scan_database_for_pii`, `create_lf_tags`, `get_pii_columns`, `apply_column_security`, `get_pii_report` | PII detection + LF-Tag application (custom FastMCP, *slow startup*) |
| OPTIONAL | `sagemaker-catalog` | `put_custom_metadata`, `get_custom_metadata`, `list_tables_with_metadata`, `search_metadata`, `delete_custom_metadata` | Business metadata on Glue tables (custom FastMCP, *slow startup*) |
| OPTIONAL | `lambda` | `AWS_LambdaFn_LF_access_grant_new`, `AWS_Lambda_LF_revoke_access_new`, `spark_on_aws_lambda`, `tagging_finder`, `LF_access_grant` | Lake Formation grants/revokes, Spark execution, resource tagging |
| OPTIONAL | `cloudwatch` | Logs, metrics, alarms, dashboards | Monitoring, log queries, metric alarms |
| OPTIONAL | `cost-explorer` | Cost and usage data | Cost tracking, budget analysis |
| OPTIONAL | `dynamodb` | Table CRUD, query, scan | Operational state, DynamoDB operations |
| ❌ N/A | `sns-sqs`, `eventbridge`, `stepfunctions` | — | → Fall back to respective `aws` CLI commands |

---

## Step 3 — Pick Your Tool by User Intent

Match the user's intent phrase to the row below. Use the `NOT when` column to disqualify.

---

### Discovery & Validation

```yaml
tool: local-file-scan
intent: ["check if data already onboarded", "does this source exist", "duplicate detection", "workload already exists"]
use: Glob + Read on workloads/*/config/source.yaml
not_when: Checking AWS infrastructure — that needs IAM/Redshift MCP
mcp_server: none (native file tools)
```

```yaml
tool: iam-simulate
intent: ["can the role access this", "verify permissions", "will Glue be able to read", "permission check"]
use: mcp__iam__simulate_principal_policy with actions [s3:GetObject, s3:ListBucket, glue:GetTable]
not_when: You already know permissions are correct and just want to proceed
mcp_server: iam (REQUIRED)
```

```yaml
tool: cloudtrail-lookup
intent: ["who accessed this data", "audit recent activity", "security check on source", "was this operation logged"]
use: mcp__cloudtrail__lookup_events with EventName filter
not_when: Real-time monitoring (use CloudWatch instead)
mcp_server: cloudtrail (WARN)
```

---

### Schema Discovery

```yaml
tool: glue-crawler
intent: ["discover schema", "detect columns", "crawl source", "new dataset schema", "what columns does this have"]
use: mcp__glue_athena__create_crawler + mcp__glue_athena__start_crawler
not_when: >
  Source is a REST API → define schema manually from API docs |
  Source is a stream (Kafka/Kinesis) → use schema registry |
  Need results in under 1 minute → use Athena DDL instead
fallback: Athena DDL (faster, no partition auto-detection)
mcp_server: glue-athena (REQUIRED)
```

```yaml
tool: redshift-spectrum-schema
intent: ["check if table already registered", "verify schema in catalog", "list columns in existing table"]
use: mcp__redshift__list_tables + mcp__redshift__list_columns (if Spectrum external schema exists)
not_when: No Spectrum external schema exists → use glue-athena MCP
mcp_server: redshift (WARN)
```

---

### Data Profiling

```yaml
tool: athena-tablesample
intent: ["profile the data", "sample the source", "check data quality before onboarding", "detect PII", "distribution of values", "null rates"]
use: mcp__glue_athena__athena_query with TABLESAMPLE BERNOULLI(5) query (synchronous)
not_when: >
  Source is not in S3 yet → use Glue JDBC job instead |
  Redshift Spectrum external schema exists → prefer mcp__redshift__execute_query
mcp_server: glue-athena (REQUIRED); OR redshift (WARN) if Spectrum schema exists
```

---

### Bronze Zone (Raw Ingestion)

```yaml
tool: s3-copy-sync
intent: ["ingest raw data", "copy to Bronze", "land raw files", "S3 to S3 copy"]
use: core MCP (S3 operations) or aws s3 sync / aws s3 cp CLI
not_when: Transformation is needed — use Glue ETL instead; source is NOT already in S3
mcp_server: core (WARN, slow startup) — prefer MCP; fall back to CLI if timeout
```

```yaml
tool: glue-jdbc-etl
intent: ["ingest from database", "extract from RDS", "pull from Postgres", "copy from Redshift to Bronze"]
use: aws glue create-job CLI with JDBC source → writes raw extract (no transforms) to S3 Bronze
not_when: Source is already in S3 — use s3 sync instead
mcp_server: glue-athena (REQUIRED)
```

```yaml
tool: lambda-api-extract
intent: ["ingest from API", "pull from REST endpoint", "HTTP source", "webhook ingestion"]
use: mcp__lambda__spark_on_aws_lambda OR aws lambda invoke CLI
not_when: Data volume is large/batch — use Glue ETL instead
mcp_server: lambda (OPTIONAL)
```

---

### Silver Zone (Clean & Validate)

```yaml
tool: glue-etl-iceberg-silver
intent: ["transform Bronze to Silver", "clean the data", "apply schema", "deduplicate", "Bronze to Silver", "run Silver transform"]
use: aws glue create-job CLI (PySpark + Iceberg) — MUST include --enable-data-lineage true
not_when: Simple file copy with no transforms — use s3 sync instead (cheaper)
mandatory_flag: "--enable-data-lineage: true — NON-NEGOTIABLE on every Glue ETL job"
mcp_server: glue-athena (REQUIRED)
```

```yaml
tool: glue-data-quality
intent: ["run quality rules", "check completeness", "validate Silver data", "quality gate", "DQDL rules"]
use: aws glue start-data-quality-ruleset-evaluation-run CLI (DQDL syntax)
not_when: Quick one-off check — Athena SQL is faster; Silver score threshold is 80%, Gold is 95%
mcp_server: glue-athena (REQUIRED)
```

---

### Gold Zone (Curate & Serve)

```yaml
tool: glue-etl-iceberg-gold
intent: ["transform Silver to Gold", "build star schema", "create fact table", "create dimension table", "aggregate for dashboards", "SCD Type 2"]
use: aws glue create-job CLI (PySpark + Iceberg) — MUST include --enable-data-lineage true
not_when: Format decision not yet made — run Phase 1 discovery first (see Gold format decision tree below)
mandatory_flag: "--enable-data-lineage: true — NON-NEGOTIABLE"
mcp_server: glue-athena (REQUIRED)
```

```yaml
tool: redshift-query-verify
intent: ["verify Gold data is queryable", "test star schema join", "validate Gold output", "check row counts in Gold"]
use: mcp__redshift__execute_query (synchronous, preferred over async Athena CLI)
not_when: No Redshift cluster / Spectrum schema in this environment
mcp_server: redshift (WARN)
```

---

### Security & Governance

```yaml
tool: lake-formation-grant
intent: ["grant column access", "restrict PII columns", "apply LF-Tags", "column-level security", "give role access to table"]
use: mcp__lakeformation__grant_permissions or mcp__lakeformation__add_lf_tags_to_resource
not_when: Row-level security needed — use Athena row filters instead
mcp_server: lakeformation (REQUIRED)
```

```yaml
tool: kms-encryption
intent: ["encrypt zone data", "create KMS key", "zone-specific key", "at-rest encryption"]
use: aws kms create-key + create-alias CLI — one CMK per zone: {workload}_bronze_key, _silver_key, _gold_key
not_when: Sharing a key across zones — always use separate zone-scoped keys
mcp_server: core (WARN, slow startup)
```

```yaml
tool: secrets-manager
intent: ["store database credentials", "store API key", "connection secrets", "don't hardcode password"]
use: aws secretsmanager create-secret CLI — never store credentials in code or config files
mcp_server: core (WARN, slow startup)
```

---

### Metadata & Catalog

```yaml
tool: glue-data-catalog
intent: ["register table schema", "update catalog", "add table to catalog", "schema registration"]
use: aws glue create-table / update-table CLI (automatic for Iceberg via S3 Tables integration)
not_when: Table is Iceberg on S3 Tables — registration is automatic, no manual step needed
mcp_server: glue-athena (REQUIRED)
```

```yaml
tool: sagemaker-catalog-metadata
intent: ["store business context", "add column descriptions", "flag PII column", "set column role", "business glossary"]
use: mcp__sagemaker_catalog__put_custom_metadata or mcp__sagemaker_catalog__get_custom_metadata
not_when: High-read-volume operational data — use DynamoDB instead
mcp_server: sagemaker-catalog (OPTIONAL)
```

---

### Lineage (Mandatory — Never Disable)

```yaml
tool: glue-data-lineage
intent: ["track data lineage", "column-level lineage", "where did this data come from", "impact analysis"]
use: Set --enable-data-lineage true on EVERY Glue ETL job — table + column lineage is automatic
not_when: NEVER disable. Overhead is <5% of job duration. No exceptions.
mcp_server: glue-athena (REQUIRED) — lineage is a job parameter, not a separate tool
```

---

### Orchestration

```yaml
tool: airflow-mwaa
intent: ["schedule the pipeline", "run daily", "orchestrate all steps", "deploy DAG", "cron schedule"]
use: aws s3 sync workloads/{name}/dags/ to MWAA S3 bucket — DAG appears in Airflow UI automatically
not_when: One-off or purely event-driven workflow — use Step Functions instead
mcp_server: stepfunctions ❌ → CLI fallback for Step Functions; MWAA via s3 sync
```

---

## Step 4 — Source Type to Ingestion Path

```
S3 source
  → Glue Crawler (glue-athena MCP) for schema
  → Athena TABLESAMPLE (glue-athena MCP) for profiling
  → Glue ETL + --enable-data-lineage for Bronze→Silver→Gold
  → Iceberg tables on S3 Tables

JDBC Database (RDS / Aurora / Redshift)
  → Glue JDBC Crawler (CLI) for schema
  → Glue JDBC ETL job (CLI) for profiling
  → Glue ETL + --enable-data-lineage for ingestion + transform
  → Iceberg tables on S3 Tables

REST API
  → Lambda extraction (lambda MCP) for ingestion
  → Manual schema definition from API docs
  → Glue ETL (CLI) for Bronze→Silver→Gold
  → Iceberg tables on S3 Tables

Stream (Kafka / Kinesis / MSK)
  → Schema Registry (MSK) or Kinesis Data Streams schema
  → Glue Streaming ETL (CLI) → Iceberg tables
```

---

## Step 5 — Gold Zone Format Decision (Run Before Building Gold)

```
Query latency requirement?
├── Sub-second  → Iceberg + materialized views  (or Redshift for extreme scale)
├── Seconds     → Iceberg with partition pruning
└── Minutes     → Iceberg or Parquet (Athena)

Data size?
├── < 1 GB      → Flat Iceberg table
├── 1–100 GB    → Partitioned Iceberg; consider star schema
└── 100 GB+     → Star schema in Iceberg; Redshift Spectrum for joins

Read pattern?
├── Dashboards  → Pre-aggregated materialized views
├── Ad-hoc SQL  → Iceberg (Athena)
├── ML features → Iceberg columnar access
└── API serving → DynamoDB cache on top of Iceberg
```

---

## Ontology Staging Routes (AWS Semantic Layer handoff — Phase 7 Step 8.5)

| Intent | Tool | Notes |
|---|---|---|
| Read `semantic.yaml` | Local filesystem (`shared/metadata/semantic_reader.py`) | Source of truth for column roles, relationships, hierarchies, PII flags |
| Fetch Gold-zone Glue schema | `mcp__glue_athena__get_table` | Fall back to `aws glue get-table` CLI if MCP is down |
| Induce OWL + R2RML mappings | `shared.semantic_layer.induce_and_stage(mode="local")` | Pure Python + rdflib; no AWS calls |
| Validate Turtle syntax | rdflib (`shared/semantic_layer/turtle_validator.py`) | Auto-fix + retry up to 2x |
| Write `ontology.ttl` + `mappings.ttl` + `ontology_manifest.json` | Local filesystem to `workloads/{name}/config/` | `state: "STAGED_LOCAL"` |
| Publish to Neptune SPARQL | **Future — requires AWS Semantic Layer deployment** | |
| Upload TTL to S3 knowledge-layer bucket | **Future** | |

**Routing rule**: If the user says "generate ontology", "stage ontology for AWS Semantic Layer", "emit OWL", or "onboard to semantic layer", route to the Ontology Staging Agent sub-agent (`prompts/data-onboarding-agent/ontology-staging-agent.md`).

---

## Mandatory Rules (Enforced Always)

> Canonical list: [tool-registry/invariants.yaml](./tool-registry/invariants.yaml)

1. **Never skip lineage** — `--enable-data-lineage: true` on every Glue ETL job, no exceptions
2. **Never put credentials in code** — always Secrets Manager or Airflow Connections
3. **Never mutate Bronze** — S3 Object Lock in Governance mode; Bronze is immutable
4. **Never skip quality gates** — Silver >= 80%, Gold >= 95%; critical rule failures block promotion regardless of score
5. **Never execute AWS ops from a sub-agent** — sub-agents generate artifacts only; main conversation deploys
6. **Always simulate IAM before source access** — `mcp__iam__simulate_principal_policy` must return `allowed` before proceeding
7. **Always verify deployment** — use `mcp__redshift__execute_query` or Athena CLI to confirm tables are queryable after deploy
8. **Always audit** — run `mcp__cloudtrail__lookup_events` after deploy to confirm all operations are logged
9. **Log every CLI fallback** — print `Warning: MCP fallback — {server} not loaded for {operation}. Using CLI.`
10. **Zone-scoped KMS keys** — separate CMK for Bronze, Silver, Gold per workload; never share keys across zones
11. **MCP first** — use MCP server tools FIRST for all AWS operations; CLI only when unavailable or errored

---

## AWS Service Reference (Code Examples)

> For detailed implementation patterns. These are the most common code snippets used across workloads.

### Source Connectivity Check

| Source Type | Tool | How to Test |
|---|---|---|
| **S3 bucket** | AWS CLI / Boto3 | `aws s3 ls s3://{bucket}/{prefix}/ --max-items 1` |
| **RDS / Aurora** | AWS Glue JDBC Connection | Create Connection, run "Test connection" |
| **Redshift** | AWS Glue JDBC Connection | Same as RDS — test via Glue Connection |
| **DynamoDB** | Boto3 | `describe_table()` |
| **API endpoint** | Python `requests` | HTTP GET to health/ping endpoint |

### Glue Crawler Configuration

```python
import boto3
glue = boto3.client('glue')

glue.create_crawler(
    Name=f"{workload_name}_source_crawler",
    Role='arn:aws:iam::{account}:role/GlueCrawlerRole',
    DatabaseName=f"{workload_name}_db",
    Targets={
        'S3Targets': [{
            'Path': f's3://{source_bucket}/{source_prefix}/',
            'Exclusions': ['_tmp/**', '_spark_metadata/**']
        }]
    },
    SchemaChangePolicy={
        'UpdateBehavior': 'UPDATE_IN_DATABASE',
        'DeleteBehavior': 'LOG'
    },
    RecrawlPolicy={'RecrawlBehavior': 'CRAWL_NEW_FOLDERS_ONLY'},
    Tags={'workload': workload_name, 'managed-by': 'data-onboarding-agent'}
)
glue.start_crawler(Name=f"{workload_name}_source_crawler")
```

### Athena Profiling Query

```sql
WITH sample AS (
    SELECT * FROM "{database}"."{table}" TABLESAMPLE BERNOULLI(5)
)
SELECT
    COUNT(*) AS sample_rows,
    COUNT(revenue) AS revenue_non_null,
    ROUND(100.0 * (COUNT(*) - COUNT(revenue)) / COUNT(*), 2) AS revenue_null_pct,
    COUNT(DISTINCT revenue) AS revenue_distinct,
    MIN(revenue) AS revenue_min,
    MAX(revenue) AS revenue_max,
    COUNT(DISTINCT region) AS region_distinct,
    MIN(order_date) AS order_date_min,
    MAX(order_date) AS order_date_max
FROM sample;
```

### Iceberg Table Creation (Silver)

```sql
CREATE TABLE s3tablesbucket.silver_db.{table_name} (
    -- columns from schema discovery
)
USING iceberg
PARTITIONED BY (region, days(order_date))
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
```

### Iceberg MERGE INTO (Upserts)

```sql
MERGE INTO silver_db.{table} AS target
USING bronze_staging AS source
ON target.{pk} = source.{pk}
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

### Glue Data Quality (DQDL)

```
Rules = [
    Completeness "email" > 0.95,
    Uniqueness "order_id" = 1.0,
    ColumnValues "revenue" between 0 and 100000,
    CustomSql "SELECT COUNT(*) FROM silver_table WHERE order_date > ship_date" = 0
]
```

### Glue Data Lineage (Mandatory on Every Job)

```bash
aws glue create-job \
  --name "{workload}_bronze_to_silver" \
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

### Airflow Operators

```python
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.operators.glue_crawler import GlueCrawlerOperator
from airflow.providers.amazon.aws.operators.athena import AthenaOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.amazon.aws.operators.sns import SnsPublishOperator
```

---

*For per-phase runtime guardrails → [MCP_GUARDRAILS.md](./MCP_GUARDRAILS.md)*
*For agent skill definitions and spawn prompts → [SKILLS.md](./SKILLS.md)*
