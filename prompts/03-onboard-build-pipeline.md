# 03 — ONBOARD: Build Data Pipeline
> Master prompt for complete pipeline setup. Spawns 4 sub-agents.

## Purpose

The primary prompt for onboarding a new dataset through the full Landing -> Staging -> Publish pipeline. This spawns 4 sub-agents (Metadata, Transformation, Quality, DAG) each with test gates.

## When to Use

- After ROUTE (01) confirms the data is new
- For each dataset you want to bring into the platform
- After GENERATE (02) if using synthetic data

## Prompt Template

```
Onboard new dataset: [DATASET_NAME]

Source:
- Type: [S3/Database/API]
- Location: [S3_PATH] (simulated locally at [LOCAL_PATH])
- Local fixture: [PATH_TO_CSV_FIXTURE for integration tests]
- Format: [CSV/JSON/Parquet]
- Frequency: [Daily/Hourly]
- Credentials: [Airflow Connection ID or Secrets Manager ARN]
- Estimated size: [ROW_COUNT] rows, [SIZE] GB

Schema:
- [col1]: [type], [description], [role: measure/dimension/identifier/temporal]
- [col2]: ...

Semantic Layer (for AI Analysis Agent):

  Fact table grain: [What does one row represent? e.g., one order / one line item / one event]

  Measures (with aggregation semantics):
  - [col]: [SUM/AVG/COUNT DISTINCT/MIN/MAX] - [description] - unit: [USD/count/pct]
    (e.g., revenue: SUM - "Net revenue after discount" - unit: USD)
    (e.g., unit_price: AVG - "Price per unit, SUM is meaningless" - unit: USD)

  Dimensions (with allowed values):
  - [col]: [description] - values: [list or "free text"]
    (e.g., region: "Sales territory" - values: [East, West, Central, South])

  Temporal:
  - [col]: [description] - grain: [day/hour] - primary: [YES/NO]

  Identifiers:
  - [col]: [description] - role: [PK/FK] - references: [TABLE.COL if FK]

  Derived columns:
  - [col] = [FORMULA] - [description]
    (e.g., revenue = quantity * unit_price * (1 - discount_pct))

  Dimension hierarchies:
  - [name]: [level1] -> [level2] -> [level3]
    (e.g., product: category -> subcategory -> product_name)

  Default filters (implicit business logic):
  - "[context]" -> WHERE [condition]
    (e.g., "Revenue queries" -> WHERE status = 'Completed')

  Business terms & synonyms:
  - "[user term]" / "[synonym]": [SQL expression] - [definition]
    (e.g., "sales" / "revenue" / "turnover": SUM(revenue) - "Net order amount")
    (e.g., "AOV": SUM(revenue) / COUNT(DISTINCT order_id) - "Average order value")

  Time intelligence:
  - Fiscal year start: [MONTH]
  - Week starts: [Monday/Sunday]
  - Common comparisons: [MoM, QoQ, YoY, WoW, YTD, MTD]
  - Timezone: [UTC/etc]

  Data freshness:
  - Refresh: [Daily/Hourly/Real-time]
  - Latest available: [T-0/T-1 day/T-1 week]

  Seed questions (top 5-10 business user questions):
  1. "[question]" -> [expected SQL pattern]
  2. "[question]" -> [expected SQL pattern]
  ...

  Data steward:
  - Owner: [team/person]
  - Domain: [Sales/Marketing/Finance/Ops]
  - Sensitivity: [Public/Internal/Confidential/Restricted]

Encryption (at rest):
- Landing zone: [KMS key alias, e.g., alias/landing-data-key] — SSE-KMS on S3
- Staging zone: [KMS key alias, e.g., alias/staging-data-key] — Iceberg tables encrypted via S3 SSE-KMS
- Publish zone: [KMS key alias, e.g., alias/publish-data-key] — Iceberg tables encrypted via S3 SSE-KMS
- Glue Catalog: [KMS key alias, e.g., alias/catalog-metadata-key] — catalog metadata encryption
- Log every encrypt/decrypt operation: "Encrypting with KMS key: [alias]"
- Re-encrypt at each zone boundary (Landing key != Staging key != Publish key)

Compliance & Governance:
- Regulatory requirements: [GDPR/CCPA/HIPAA/SOX/PCI DSS/None]
- PII detection: [Automatic via shared/utils/pii_detection_and_tagging.py]
  - Name-based: Scan column names for PII patterns
  - Content-based: Regex on sample data (100 rows)
  - LF-Tags applied: PII_Classification, PII_Type, Data_Sensitivity
- Tag-based access control: [Roles with sensitivity level access]
- Data retention: [DAYS for each zone]
- Audit logging: [CloudTrail for all Lake Formation operations]

Data Zones:

Landing (raw ingestion):
- Keep raw format: [YES/NO]
- Partitioning: [By ingestion date / other]
- Retention: [DAYS]
- Encryption: SSE-KMS with [LANDING_KMS_KEY_ALIAS]

Staging (cleaned, validated):
- Cleaning: Dedupe on [KEY], handle nulls [DROP/FILL], cast [COL->TYPE]
- PII detection: [Run after profiling — automatic]
- PII masking: [COLUMNS to hash/mask based on detection results]
- LF-Tags: [Applied to all PII columns for column-level security]
- Validate: [enum constraints, date ranges, FK references]
- Format: Apache Iceberg on S3 Tables
- Encryption: SSE-KMS with [STAGING_KMS_KEY_ALIAS]
- Registered in Glue Catalog

Publish (curated, business-ready):
- Use case: [Reporting/Analytics/ML]
- Format: [Star Schema/Flat/Custom]
  - If Star Schema: [Fact table name + measures, Dim tables, Aggregate tables]
- Quality threshold: 95%
- Format: Apache Iceberg on S3 Tables
- Encryption: SSE-KMS with [PUBLISH_KMS_KEY_ALIAS]
- Registered in Glue Catalog
- Access control: [Tag-based permissions via Lake Formation]

Quality Rules:
- Completeness: [Required columns non-null, threshold %]
- Uniqueness: [Key must be unique]
- Validity: [Value constraints, enum lists]
- Accuracy: [Computed field validation, e.g., revenue = qty * price * (1-discount)]
- Referential: [FK must exist in target table, threshold %]
- Critical rules: [Block promotion if fail]
- PII compliance: [All PII columns tagged, access logged]

Schedule:
- Frequency: [cron expression]
- Dependencies: [Other DAGs / ExternalTaskSensor]
- SLA: [minutes]
- MWAA bucket: [S3 bucket for Airflow DAG deployment, e.g., s3://my-mwaa-environment-bucket]

Testing:
- Use [FIXTURE_PATH] as data source for integration tests
- Use [SIMULATED_S3_PATH] for local pipeline runs (e.g., /tmp/data-lake/)
- Import scripts using importlib.util.spec_from_file_location to avoid
  cross-workload module collisions when running pytest across all workloads
- Target: 50+ tests (unit: metadata, transformations, quality, DAG; integration: pipeline)

Build complete pipeline with tests.
```

## Key Parameters

### Source

| Parameter | Description | Example |
|-----------|-------------|---------|
| `DATASET_NAME` | Workload name (becomes folder name) | `order_transactions` |
| `S3_PATH` | Production S3 location | `s3://prod-data-lake/raw/transactions/` |
| `LOCAL_PATH` | Simulated local S3 path | `/tmp/data-lake/landing/orders/` |
| `FIXTURE_PATH` | CSV fixture for integration tests | `shared/fixtures/orders.csv` |
| `CSV/JSON/Parquet` | Source format | JSON |
| `Daily/Hourly` | Ingestion frequency | Hourly |

### Schema

| Parameter | Description | Example |
|-----------|-------------|---------|
| `col` | Column name | `revenue` |
| `type` | Data type | DECIMAL(10,2) |
| `role` | Column role | measure / dimension / identifier / temporal |

### Semantic Layer

| Parameter | Description | Example |
|-----------|-------------|---------|
| `Fact table grain` | What one row represents | "One row per order" |
| `default_aggregation` | How to aggregate each measure | SUM, AVG, COUNT DISTINCT |
| `unit` | Unit of measurement | USD, count, pct |
| `Derived columns` | Computed field formulas | `revenue = qty * price * (1-discount)` |
| `Default filters` | Implicit business logic | `"Revenue" -> WHERE status='Completed'` |
| `Business terms` | User synonyms for columns | `"sales"/"turnover" -> SUM(revenue)` |
| `Seed questions` | Top user questions with SQL patterns | `"Total revenue?" -> SUM(revenue)` |

### Encryption

| Parameter | Description | Example |
|-----------|-------------|---------|
| `KMS key alias` | Zone-specific KMS key | `alias/landing-data-key` |

### Zones

| Parameter | Description | Example |
|-----------|-------------|---------|
| `Keep raw format` | Preserve original format in Landing | YES |
| `Cleaning rules` | Dedupe, null handling, type casting | Dedupe on order_id, DROP null PKs |
| `PII masking` | Columns to hash/mask in Staging | email (SHA256), phone (mask) |
| `Use case` | Publish zone format driver | Reporting -> Star Schema |
| `Quality threshold` | Minimum score for Publish | 95% |

## Expected Output

The ONBOARD prompt creates the full workload directory:

```
workloads/{dataset_name}/
├── config/
│   ├── source.yaml
│   ├── semantic.yaml
│   ├── transformations.yaml
│   ├── quality_rules.yaml
│   └── schedule.yaml
├── scripts/
│   ├── extract/ingest_to_landing.py
│   ├── transform/landing_to_staging.py
│   ├── transform/staging_to_publish.py
│   ├── quality/check_staging.py
│   └── quality/check_publish.py
├── dags/
│   └── {dataset_name}_dag.py
├── sql/
│   ├── landing/
│   ├── staging/
│   └── publish/
├── tests/
│   ├── unit/
│   └── integration/
├── deploy_to_aws.py              # Full deployment script (S3, Glue, IAM, MWAA, QuickSight)
└── README.md
```

Plus 50+ tests (unit + integration) that must all pass.

The `deploy_to_aws.py` script MUST include:
- All Glue job creation + execution (Bronze → Silver → Gold)
- IAM role setup
- Athena workgroup creation
- QuickSight dashboard setup
- **MWAA DAG deployment** (Step 13): uploads DAG file, shared utils, workload config, and workload scripts to MWAA S3 bucket
- `--dry-run` mode for safe testing
- `--mwaa-bucket=BUCKET` parameter for MWAA deployment

## Phase 7: Deploy to AWS

After artifacts pass all tests and get human approval, deploy to AWS.

### Step 0: MCP Health Check (MANDATORY)

Before any deployment, verify MCP servers are connected:

```bash
claude mcp list
```

**Required servers** (must be Connected — BLOCK deployment if not):
- `glue-athena` — Glue catalog, crawlers, jobs, Athena queries
- `lakeformation` — LF-Tags, TBAC grants, column-level security
- `iam` — Role verification, policy management

**Optional servers** (fall back to CLI if not connected):
- `cloudtrail` — Audit trail verification
- `redshift` — Query verification via Spectrum
- `core` — S3 uploads, KMS keys
- `s3-tables` — Iceberg table management
- `pii-detection` — PII detection + LF-Tag application
- `sagemaker-catalog` — Business metadata

**Slow-startup servers** (`core`, `pii-detection`, `sagemaker-catalog`) may show "Failed to connect" on health check but work during conversation. Test with a simple call to confirm.

Present results to human. Do NOT proceed if any REQUIRED server fails.

### Deployment Checklist
1. **Create Glue database** (if new workload)
2. **Grant Lake Formation permissions** (CREATE_TABLE, ALTER, DROP on database; ALL on tables)
3. **Create Glue jobs** (one per ETL script, Glue 4.0, `--datalake-formats: iceberg`)
4. **Upload scripts to CORRECT S3 path** — verify each job's `ScriptLocation`:
   ```bash
   aws glue get-job --job-name MY_JOB --query 'Job.Command.ScriptLocation' --output text
   ```
5. **Run Bronze to Silver jobs first**, then Silver to Gold after Silver succeeds
6. **Verify all Iceberg tables** exist in Glue Data Catalog
7. **PII Detection + LF-Tag Application** (MANDATORY — runs after tables registered):
   ```bash
   python3 -m shared.utils.pii_detection_and_tagging \
     --database {DATABASE_NAME} --region us-east-1
   ```
   - Creates 3 LF-Tags: `PII_Classification`, `PII_Type`, `Data_Sensitivity`
   - Scans all tables, applies column-level tags
   - Even non-PII columns get tagged `PII_Classification=NONE`
   - Verify: `aws lakeformation get-resource-lf-tags --resource '{"Table":{"DatabaseName":"DB","Name":"TABLE"}}'`
8. **Grant TBAC permissions to querying principals** (CRITICAL — without this, Athena returns `COLUMN_NOT_FOUND`):
   Applying LF-Tags activates Tag-Based Access Control. All principals (Athena users, Glue roles,
   QuickSight) need explicit grants on the tag values to see columns.
   ```bash
   # Full access (all sensitivity levels)
   aws lakeformation grant-permissions \
     --principal '{"DataLakePrincipalIdentifier":"arn:aws:iam::ACCOUNT:role/ROLE"}' \
     --permissions SELECT DESCRIBE \
     --resource '{"LFTagPolicy":{"ResourceType":"TABLE","Expression":[{"TagKey":"PII_Classification","TagValues":["NONE","LOW","MEDIUM"]}]}}' \
     --region us-east-1

   # Restricted access (hide MEDIUM columns like manager_name)
   aws lakeformation grant-permissions \
     --principal '{"DataLakePrincipalIdentifier":"arn:aws:iam::ACCOUNT:role/analyst"}' \
     --permissions SELECT DESCRIBE \
     --resource '{"LFTagPolicy":{"ResourceType":"TABLE","Expression":[{"TagKey":"PII_Classification","TagValues":["NONE","LOW"]}]}}' \
     --region us-east-1
   ```
   - Grant to: current IAM user, Glue ETL role, Athena execution role, QuickSight service role
   - Repeat for `Data_Sensitivity` and `PII_Type` tags with matching values
   - Verify: `SELECT * FROM {gold_table} LIMIT 5` in Athena — should return columns

9. **Deploy DAG + shared utils to MWAA** (if MWAA is configured):
   ```bash
   # Upload DAG file
   aws s3 cp workloads/{WORKLOAD}/dags/{WORKLOAD}_dag.py \
     s3://{MWAA_BUCKET}/dags/

   # Upload shared utilities (required by DAG imports)
   aws s3 sync shared/utils/ s3://{MWAA_BUCKET}/dags/shared/utils/ \
     --exclude '__pycache__/*' --exclude '*.pyc'
   aws s3 sync shared/logging/ s3://{MWAA_BUCKET}/dags/shared/logging/ \
     --exclude '__pycache__/*' --exclude '*.pyc'

   # Upload __init__.py files for import chain
   aws s3 cp shared/__init__.py s3://{MWAA_BUCKET}/dags/shared/__init__.py

   # Upload workload config (referenced by DAG)
   aws s3 sync workloads/{WORKLOAD}/config/ \
     s3://{MWAA_BUCKET}/dags/workloads/{WORKLOAD}/config/

   # Upload workload scripts (called by DAG operators)
   aws s3 sync workloads/{WORKLOAD}/scripts/ \
     s3://{MWAA_BUCKET}/dags/workloads/{WORKLOAD}/scripts/ \
     --exclude '__pycache__/*' --exclude '*.pyc'
   ```
   - Verify: DAG appears in Airflow UI within ~30 seconds
   - Check: No import errors in Airflow DAG processing logs
   - The DAG file must be at the **root** of the `dags/` prefix (not nested in workloads/)

10. **Post-Deployment Verification** (MANDATORY — run after all steps complete):

    This is a comprehensive smoke test across all deployed services. Do NOT skip.

    **10a. Glue Catalog — tables exist with correct schema:**
    ```bash
    # List all tables in the database
    aws glue get-tables --database-name {DATABASE} \
      --query 'TableList[].{Name:Name,Type:Parameters.table_type,Cols:StorageDescriptor.Columns|length(@)}' \
      --output table

    # Verify each table has expected columns (spot-check silver + gold)
    aws glue get-table --database-name {DATABASE} --name {SILVER_TABLE} \
      --query 'Table.StorageDescriptor.Columns[].{Name:Name,Type:Type}' --output table
    aws glue get-table --database-name {DATABASE} --name {GOLD_TABLE} \
      --query 'Table.StorageDescriptor.Columns[].{Name:Name,Type:Type}' --output table
    ```
    Expected: All Silver + Gold tables present, column names and types match semantic.yaml.

    **10b. Athena — data is queryable and row counts are sane:**
    ```bash
    # Query each Gold table (must return rows, not errors)
    aws athena start-query-execution \
      --query-string "SELECT COUNT(*) AS row_count FROM {DATABASE}.{GOLD_TABLE}" \
      --work-group {WORKGROUP} \
      --result-configuration "OutputLocation=s3://{BUCKET}/athena-results/"

    # Spot-check a star schema join (if applicable)
    aws athena start-query-execution \
      --query-string "SELECT f.*, d.column_name FROM {DATABASE}.{FACT_TABLE} f JOIN {DATABASE}.{DIM_TABLE} d ON f.fk = d.pk LIMIT 5" \
      --work-group {WORKGROUP} \
      --result-configuration "OutputLocation=s3://{BUCKET}/athena-results/"
    ```
    Expected: Row counts > 0, joins return data, no COLUMN_NOT_FOUND errors.

    **10c. LF-Tags — all PII/non-PII columns tagged:**
    ```bash
    # Check tags on every table
    for TABLE in {SILVER_TABLE_1} {SILVER_TABLE_2} {GOLD_TABLE_1} {GOLD_TABLE_2}; do
      echo "--- $TABLE ---"
      aws lakeformation get-resource-lf-tags \
        --resource "{\"Table\":{\"DatabaseName\":\"${DATABASE}\",\"Name\":\"$TABLE\"}}" \
        --query 'LFTagOnDatabase || LFTagsOnTable || LFTagsOnColumns' --output table
    done
    ```
    Expected: Every column has PII_Classification + Data_Sensitivity tags.

    **10d. TBAC — access grants are correct per role:**
    ```bash
    # Verify each principal's grants
    for ROLE in {GLUE_ROLE} {ATHENA_ROLE} {QUICKSIGHT_ROLE}; do
      echo "--- $ROLE ---"
      aws lakeformation list-permissions \
        --principal "{\"DataLakePrincipalIdentifier\":\"arn:aws:iam::${ACCOUNT}:role/$ROLE\"}" \
        --query 'PrincipalResourcePermissions[].{Resource:Resource,Permissions:Permissions}' \
        --output table
    done

    # Test restricted role sees NULL for high-sensitivity columns
    # (assume analyst role and query — HIGH/CRITICAL columns should be NULL)
    ```
    Expected: Each role has grants matching its sensitivity level. Restricted roles cannot see PII.

    **10e. KMS — encryption active on all zones:**
    ```bash
    # Verify S3 bucket encryption
    aws s3api get-bucket-encryption --bucket {DATA_LAKE_BUCKET}

    # Verify KMS key exists and rotation enabled
    aws kms describe-key --key-id alias/{WORKLOAD}-key
    aws kms get-key-rotation-status --key-id alias/{WORKLOAD}-key
    ```
    Expected: SSE-KMS enabled, key rotation active.

    **10f. MWAA DAG — loaded without errors (if MWAA configured):**
    ```bash
    # Check DAG exists in MWAA S3 bucket
    aws s3 ls s3://{MWAA_BUCKET}/dags/{WORKLOAD}_dag.py

    # Check shared utils uploaded
    aws s3 ls s3://{MWAA_BUCKET}/dags/shared/utils/ --recursive | head -10

    # Verify DAG parsed successfully (via MWAA CLI or Airflow REST API)
    # If using MWAA CLI:
    aws mwaa create-cli-token --name {MWAA_ENV_NAME} | \
      jq -r '.CliToken' | \
      xargs -I{} curl -s "https://{MWAA_WEBSERVER}/aws_mwaa/cli" \
        -H "Authorization: Bearer {}" \
        -H "Content-Type: text/plain" \
        -d "dags list" | base64 -d | grep {WORKLOAD}
    ```
    Expected: DAG listed, no import errors in DAG processing logs.

    **10g. QuickSight — datasets accessible (if QuickSight configured):**
    ```bash
    # List datasets
    aws quicksight list-data-sets --aws-account-id {ACCOUNT} \
      --query "DataSetSummaries[?contains(Name,'{WORKLOAD}')].{Name:Name,Id:DataSetId}" \
      --output table

    # Check data source connection
    aws quicksight describe-data-source --aws-account-id {ACCOUNT} \
      --data-source-id {WORKLOAD}_athena_source \
      --query 'DataSource.Status'
    ```
    Expected: Data source status = CREATION_SUCCESSFUL, datasets listed.

    **10h. CloudTrail — audit trail active:**
    ```bash
    # Verify recent deployment events logged
    aws cloudtrail lookup-events \
      --lookup-attributes AttributeKey=EventSource,AttributeValue=lakeformation.amazonaws.com \
      --max-results 10 \
      --query 'Events[].{Time:EventTime,Name:EventName,User:Username}' \
      --output table
    ```
    Expected: CreateTable, AddLFTagsToResource, GrantPermissions events visible.

    **10i. Summary report — present to human:**
    After running all checks, present a summary table:
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
    If ANY check fails, report the failure details and ask the human how to proceed.
    Do NOT consider the deployment complete until all checks pass.

### Known Glue 4.0 + Iceberg Rules
- Use `.saveAsTable("glue_catalog.db.table")` — NOT `.save(s3_path)`
- Use `spark.table("glue_catalog.db.table")` — NOT `spark.read.parquet()`
- Do NOT use `.partitionBy()` — causes `ClusteredWriter` errors
- Point `bronze_path` to specific CSV files, not directories with mixed formats
- Only require `JOB_NAME` in `getResolvedOptions` for catalog-based jobs
- Use catalog table names in lineage sections, not `args['path']`

See `prompts/07-fix-iceberg-glue.md` for the full troubleshooting guide.
