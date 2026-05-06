# 03 — ONBOARD: Build Data Pipeline
> Master prompt for complete pipeline setup. Spawns 4 sub-agents.

## Purpose

The primary prompt for onboarding a new dataset through the full Landing -> Staging -> Publish pipeline. This spawns 4 sub-agents (Metadata, Transformation, Quality, DAG) each with test gates.

## When to Use

- After ROUTE (01) confirms the data is new
- For each dataset you want to bring into the platform
- After GENERATE (02) if using synthetic data

## Quick Start (Simple CSV Ingestion)

For simple workloads, you can skip most details and use defaults:

```
Onboard new dataset: [DATASET_NAME]

Source: CSV at [S3_PATH or LOCAL_PATH]
Schema: (paste first 5-10 columns, rest will be auto-detected)
- [col1]: [type]
- [col2]: [type]
- [col3]: [type]
...

Regulation: [None/HIPAA/GDPR/CCPA/SOX/PCI DSS]

Use all defaults for encryption, retention, quality, and scheduling.
```

**That's it!** The system will:
- Auto-detect remaining columns via profiling (Phase 3)
- Apply default transformations (dedup on PK, null handling, type casting)
- Generate standard quality rules (completeness 90%, uniqueness 100%)
- Schedule daily at 2 AM UTC with 2-hour SLA
- Create basic Bronze→Silver→Gold DAG
- Apply regulation-specific controls automatically (if regulation selected)

**When to use the full template below?**
- Custom transformations (complex dedup logic, derived columns, hierarchies)
- Regulatory compliance with custom controls beyond defaults
- Advanced semantic layer (time intelligence, seed questions, business terms)
- Non-standard scheduling (hourly, real-time, custom dependencies)
- Specific encryption keys or retention periods

---

## Default Values (Optional — Skip if Using Defaults)

The following values have sensible defaults. Only specify if you need custom values:

| Field | Default | When to Override |
|-------|---------|------------------|
| **KMS key (Landing)** | `alias/landing-data-key` | HIPAA/PCI DSS: use `alias/hipaa-phi-key` or `alias/pci-cardholder-key` |
| **KMS key (Staging)** | `alias/staging-data-key` | HIPAA/PCI DSS: use same key as Landing (all zones contain PHI/PCI data) |
| **KMS key (Publish)** | `alias/publish-data-key` | HIPAA/PCI DSS: use same key as Landing |
| **Schedule** | Daily at 2 AM UTC (`0 2 * * *`) | Hourly, real-time, or custom schedule |
| **SLA** | 2 hours | Mission-critical pipelines need tighter SLAs |
| **Retries** | 3 with exponential backoff | Flaky sources need more retries |
| **Landing Retention** | 90 days | Regulatory requirements (HIPAA: 90 days, GDPR: depends on consent) |
| **Staging Retention** | 365 days | Regulatory requirements (HIPAA: 2555 days / 7 years) |
| **Publish Retention** | 365 days | Regulatory requirements (HIPAA: 2555 days / 7 years) |
| **Quality Threshold (Silver)** | 80% | Lower for exploratory pipelines, higher for critical data |
| **Quality Threshold (Gold)** | 95% | Always high for business-ready data |
| **Deduplication** | Auto-detect PK from schema | Specify if composite key or custom logic |
| **Null handling** | DROP rows with null PKs, FILL non-critical columns | Specify if different strategy needed |

**Quick Start users**: If you don't specify these, the defaults above are automatically applied.

**Full Template users**: Specify values inline (overrides defaults).

---

## Prompt Template (Comprehensive Onboarding)

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

Deployment Scope (account_topology — see shared/templates/account_topology.yaml):

- Scope: [single / multi]

**If single (default):** nothing else to specify. Glue catalog, Glue jobs,
MWAA, S3, IAM all live in the account returned by `aws sts get-caller-identity`.

**If multi (catalog in Account A, jobs/MWAA in Account B):**
- catalog_account_id: [12-digit AWS account ID — Account A, owns Glue Data
  Catalog + Lake Formation]
- jobs_account_id: [12-digit AWS account ID — Account B, runs Glue jobs,
  MWAA, owns S3 buckets + KMS keys; MUST equal current caller identity]
- catalog_assume_role_arn: [arn:aws:iam::<A>:role/<catalog-reader> — IAM
  role in Account A that Account B's Glue service role assumes; MUST
  already exist per docs/multi-account-deployment.md §1]
- catalog_external_id: [optional sts:ExternalId string, or "null" if the
  trust policy doesn't require one]
- Region: [us-east-1 / ... — both accounts must be same region]

Pre-requisites for multi-account (STOP and refuse onboarding if any is missing):
  1. Account A: catalog-reader IAM role exists with trust policy allowing
     Account B's Glue service role (see docs/multi-account-deployment.md §1).
  2. Account A: Lake Formation grants the reader role DESCRIBE + SELECT on
     target databases/tables (see §2 of the same doc).
  3. Account B: Glue service role has `sts:AssumeRole` on the Account A
     reader role ARN (see §3).
  4. Airflow Variables `glue_catalog_account_id`,
     `glue_catalog_assume_role_arn`, and `glue_catalog_external_id` are
     already set by `prompts/environment-setup-agent/01-setup-aws-infrastructure.md`
     Step 1b.

Schema:
- [col1]: [type], [description], [role: measure/dimension/identifier/temporal]
- [col2]: ...

Semantic Layer (for AWS Semantic Layer handoff via Phase 7 Step 8.5):

**REQUIRED (minimum for AI to answer questions):**

  Fact table grain: [What does one row represent? e.g., one order / one line item / one event]

  Measures (with aggregation semantics):
  - [col]: [SUM/AVG/COUNT DISTINCT/MIN/MAX] - [description] - unit: [USD/count/pct]
    (e.g., revenue: SUM - "Net revenue after discount" - unit: USD)
    (e.g., unit_price: AVG - "Price per unit, SUM is meaningless" - unit: USD)
  *Provide top 3-5 measures — most important business metrics*

  Dimensions (with allowed values):
  - [col]: [description] - values: [list or "free text"]
    (e.g., region: "Sales territory" - values: [East, West, Central, South])
  *Provide top 5-10 dimensions — how users slice/filter the data*

  Temporal:
  - [col]: [description] - grain: [day/hour] - primary: [YES/NO]
  *At least one temporal column for time-based analysis*

  Identifiers:
  - [col]: [description] - role: [PK/FK] - references: [TABLE.COL if FK]
  *Primary key and any foreign keys for joins*

**OPTIONAL (advanced semantic features — skip for simple workloads):**

<details>
<summary>Click to expand advanced semantic layer options</summary>

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
  Provide 3-5 examples with full SQL to help the AI understand your data:

  1. "What was our total revenue last month?"
     ```sql
     SELECT SUM(revenue) AS total_revenue
     FROM gold_orders
     WHERE order_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')
       AND order_date < DATE_TRUNC('month', CURRENT_DATE)
       AND status = 'Completed'
     ```

  2. "Which region had the highest average order value in Q4?"
     ```sql
     SELECT region, AVG(revenue) AS avg_order_value
     FROM gold_orders
     WHERE QUARTER(order_date) = 4
       AND YEAR(order_date) = YEAR(CURRENT_DATE - INTERVAL '1 year')
       AND status = 'Completed'
     GROUP BY region
     ORDER BY avg_order_value DESC
     LIMIT 1
     ```

  3. "Show me the top 10 customers by lifetime value"
     ```sql
     SELECT customer_id, customer_name, SUM(revenue) AS lifetime_value
     FROM gold_orders
     WHERE status = 'Completed'
     GROUP BY customer_id, customer_name
     ORDER BY lifetime_value DESC
     LIMIT 10
     ```

  (Add more questions specific to your use case)

  Data steward:
  - Owner: [team/person]
  - Domain: [Sales/Marketing/Finance/Ops]
  - Sensitivity: [Public/Internal/Confidential/Restricted]

</details>

Encryption (at rest):

**KMS Key Strategy Decision Tree:**

```
┌─ HIPAA or PCI DSS selected?
│  └─ YES → Use SAME dedicated key for all zones
│     - HIPAA: alias/hipaa-phi-key (all zones contain PHI)
│     - PCI DSS: alias/pci-cardholder-key (all zones contain cardholder data)
│     - Rationale: Sensitive data exists in all zones (Bronze=raw, Silver=masked, Gold=aggregated)
│     - Re-encrypt at zone boundaries WITH THE SAME KEY (log the operation)
│
└─ NO (GDPR/CCPA/SOX/None) → Use DIFFERENT keys per zone
   - Landing: alias/landing-data-key OR alias/{workload}-landing-key
   - Staging: alias/staging-data-key OR alias/{workload}-staging-key
   - Publish: alias/publish-data-key OR alias/{workload}-publish-key
   - Glue Catalog: alias/catalog-metadata-key (shared across workloads)
   - Rationale: Data sensitivity decreases from Bronze→Silver→Gold (masking applied in Silver)
   - Re-encrypt at each zone boundary (Landing key → Staging key → Publish key)
```

**Specify keys for each zone:**
- Landing zone: [KMS key alias, e.g., alias/landing-data-key OR alias/hipaa-phi-key] — SSE-KMS on S3
- Staging zone: [KMS key alias, e.g., alias/staging-data-key OR alias/hipaa-phi-key] — Iceberg tables encrypted via S3 SSE-KMS
- Publish zone: [KMS key alias, e.g., alias/publish-data-key OR alias/hipaa-phi-key] — Iceberg tables encrypted via S3 SSE-KMS
- Glue Catalog: [KMS key alias, e.g., alias/catalog-metadata-key] — catalog metadata encryption
- Log every encrypt/decrypt operation: "Encrypting with KMS key: [alias]"

Compliance & Governance:
- Regulatory requirements: [GDPR/CCPA/HIPAA/SOX/PCI DSS/None]

**How regulation loading works**:
If you select a regulation (e.g., HIPAA), the system automatically loads controls from `prompts/data-onboarding-agent/regulation/hipaa.md`. These controls include default encryption keys, retention periods, LF-Tag requirements, access roles, and masking methods. You don't need to specify these manually — they're auto-applied during Phase 1 discovery. See `prompts/data-onboarding-agent/regulation/README.md` for what each regulation provides.

**What you MUST still specify** (even with regulation selected):
- Data steward owner and domain
- Failure notification email
- Business context (semantic layer, seed questions if needed)

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
- PII masking: [Automatic based on sensitivity — specify overrides if needed]

**Default PII masking methods** (auto-applied after detection):
| Sensitivity | Method | Example | Reversible |
|-------------|--------|---------|------------|
| CRITICAL (SSN, MRN, Credit Card) | SHA-256 hash | `123-45-6789` → `a1b2c3d4...` | No |
| HIGH (Name, Email, DOB) | SHA-256 hash OR mask_email | `john@email.com` → `j***@email.com` | No |
| MEDIUM (Phone, Address) | mask_partial | `555-123-4567` → `555-***-4567` | No |
| LOW | No masking (keep original) | `92101` (zip) → `92101` | N/A |

**Override masking** (optional — only if defaults don't fit):
- [COLUMN]: [method] - [reason]
  Example: `ssn: keep - "Needed for fraud detection in Staging, will be dropped in Gold"`

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

Testing (choose tier based on use case):

**Minimum (Test Gate Pass)** — for exploratory pipelines or prototypes:
- 5 unit tests: schema validation, transformation logic, quality check basics, deduplication, null handling
- 1 integration test: Bronze→Silver pipeline run with fixture data
- Allows deployment but flagged as "prototype" in workload README
- Use [FIXTURE_PATH] as data source for integration tests

**Standard (Recommended)** — for production pipelines:
- 20+ unit tests: metadata, transformations (per-column), quality (all 5 dimensions), DAG structure, lineage
- 5+ integration tests: Bronze→Silver→Gold flow, quality gates, error handling, idempotency, PII detection
- Use [SIMULATED_S3_PATH] for local pipeline runs (e.g., /tmp/data-lake/)
- Import scripts using importlib.util.spec_from_file_location to avoid cross-workload module collisions when running pytest across all workloads

**Comprehensive (Production-Ready)** — for critical/regulated data:
- 50+ unit tests: all Standard tests + edge cases + column-level transformation tests
- 10+ integration tests: all Standard tests + failure scenarios + rollback tests + compliance verification
- Property-based tests (fast-check): transformation idempotency, lineage completeness, quality monotonicity, schema preservation, Bronze immutability
- Required for HIPAA/SOX/PCI DSS workloads

**Skip tests for prototype** (NOT RECOMMENDED):
- Add `--skip-tests` flag in Phase 4
- Pipeline will be flagged as "UNTESTED - DO NOT USE IN PRODUCTION" in README
- Must add tests before promoting to production use

Build complete pipeline with tests.
```

## Key Parameters

### Source

| Parameter | Description | Example |
|-----------|-------------|---------|
| `DATASET_NAME` | Workload name (becomes folder name) | `order_transactions` |
| `S3_PATH` | Production S3 location | `s3://prod-data-lake/raw/transactions/` |
| `LOCAL_PATH` | Simulated local S3 path | `/tmp/data-lake/landing/orders/` |
| `FIXTURE_PATH` | CSV fixture for integration tests | `demo/sample_data/orders.csv` |
| `CSV/JSON/Parquet` | Source format | JSON |
| `Daily/Hourly` | Ingestion frequency | Hourly |

### Deployment Scope

| Parameter | Description | Example |
|-----------|-------------|---------|
| `Scope` | `single` (default) or `multi` | `single` |
| `catalog_account_id` | Account A (Glue catalog owner) if multi | `111111111111` |
| `jobs_account_id` | Account B (Glue jobs + MWAA + S3) — matches caller | `222222222222` |
| `catalog_assume_role_arn` | IAM role Account B assumes into Account A | `arn:aws:iam::111111111111:role/adop-catalog-reader` |
| `catalog_external_id` | Optional sts:ExternalId | `adop-b-to-a` |

**Persistence**: Once the user answers the Deployment Scope block in the
prompt template, write the full structure to
`workloads/{DATASET_NAME}/config/deployment.yaml` using the schema at
`shared/templates/account_topology.yaml`. In single mode, set
`catalog_account_id == jobs_account_id` and leave assume-role fields null.

**Sub-agent threading**: Include the `account_topology` block in every
sub-agent spawn prompt (Metadata, Transformation, Quality, DAG, Ontology
Staging, IaC Generator). Each sub-agent reads it and:

- **Metadata Agent** instantiates `GlueFetcher` / `LakeFormationFetcher`
  with `catalog_id=catalog_account_id` so Phase 3 profiling hits the
  correct catalog.
- **Transformation Agent** — when `mode=multi`, the generated PySpark
  MUST include `spark.conf.set("spark.sql.catalog.glue_catalog.glue.id", args["catalog_account_id"])`
  and accept `--catalog_account_id` as a job arg.
- **DAG Agent** — when `mode=multi`, the generated DAG MUST read
  `Variable.get("glue_catalog_account_id")` and pass it as
  `--catalog_account_id` to every GlueJobOperator default_args.
- **IaC Generator** reads the block in its Phase 0 (see
  `prompts/devops-agent/iac-generator.md`) and emits provider aliases
  + CatalogId references accordingly.
- See `docs/multi-account-deployment.md` for the full generation
  contract.

### RESUME.md maintenance (push side of hybrid)

After **every** sub-agent test gate passes (Metadata, Transformation,
Quality, DAG, Ontology Staging), the orchestrator MUST regenerate
`workloads/{workload_name}/RESUME.md`. Call the shared util:

```python
from shared.utils.resume_writer import write_resume_from_disk
write_resume_from_disk(workload_name="{workload_name}")
```

…or via CLI: `python3 -m shared.utils.resume_writer --workload {workload_name}`.

RESUME.md is the **durable handoff contract** when the session is
interrupted. A human (or a future Claude Code session) reads RESUME.md
to know which phases completed, what's blocking, and the exact prompt
to paste to resume. Do NOT hand-write RESUME.md — always regenerate
from disk so the file matches reality.

Update RESUME.md also at:
- Phase 0 topology choice persisted to `config/deployment.yaml`.
- Phase 5 deploy dry-run started (writes a `trace_events.jsonl`).
- Phase 5 deploy completed (writes `deployment_summary.json`).

If the agent cannot call Python (e.g., Claude Code tool budget
exhausted), instruct the user to run the CLI command shown above.

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
├── logs/                          # Pipeline execution traces and logs
│   ├── trace_events.jsonl        # Cumulative trace history (committed to git)
│   ├── run_YYYYMMDD_HHMMSS/     # Per-run logs (ignored by git)
│   │   ├── trace.jsonl          # This run's trace events
│   │   ├── orchestrator.log     # Phase transitions, test gates
│   │   ├── extract.log          # Bronze extraction logs
│   │   ├── transform.log        # Silver/Gold transformation logs
│   │   ├── quality.log          # Quality check results
│   │   └── load.log             # Gold load logs
│   ├── latest -> run_YYYYMMDD_HHMMSS/  # Symlink to latest run
│   └── .gitignore               # Ignore run_*/ folders, keep trace_events.jsonl
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

## Prompt Validation (Pre-Flight Check)

Before starting the onboarding process, validate the prompt template inputs to catch errors early:

**Mandatory validation checks** (fail-fast on first error):

1. **Dataset name valid**:
   - Format: lowercase, alphanumeric + underscores only, no spaces
   - Length: 3-64 characters
   - Not already in use: check `workloads/` folder
   - Example valid: `healthcare_patients`, `order_transactions`
   - Example invalid: `Healthcare-Patients!`, `my workload`

2. **Source accessible**:
   - If S3: verify path format `s3://bucket/path/` and bucket exists (if not simulated)
   - If local: verify path exists and is readable
   - If fixture: verify CSV file exists at specified path
   - Format specified: CSV, JSON, or Parquet

3. **Schema has ≥1 column**:
   - At least one column defined with name and type
   - Column names valid (no special chars except underscore)
   - At least one column has a role (measure/dimension/identifier/temporal)

4. **Regulation fields complete** (if regulation selected):
   - Regulation is one of: HIPAA, GDPR, CCPA, SOX, PCI DSS, None
   - If regulation selected, data steward owner is specified
   - If regulation selected, failure notification email is specified

5. **Required fields not empty**:
   - Dataset name provided
   - Source location provided
   - Source format provided
   - Frequency provided (Daily/Hourly)
   - At least one measure OR dimension defined (semantic layer minimum)

**Remediation** (if any check fails):
- Report which check failed with specific reason
- Provide corrected example
- Ask user to fix and re-submit prompt

**Pass criteria**: All 5 checks pass → proceed to Phase 0 (Health Check & Auto-Detect from SKILLS.md).

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

8.5. **Stage OWL + R2RML ontology for AWS Semantic Layer handoff** (OPTIONAL — skip if
     `workloads/{WORKLOAD}/config/semantic.yaml` is missing OR the user
     opted out of ontology staging during Phase 1 discovery):

   Spawn the **Ontology Staging Agent** sub-agent with this context:
   - `dataset_name`: `{WORKLOAD}`
   - `glue_database`: `{DATABASE_NAME}` (the Gold-zone database)
   - `glue_table`: primary Gold-zone fact/dimension table
   - `namespace`: short ontology namespace (default: derived from `{WORKLOAD}`,
     e.g., `financial_portfolios` → `finance`)
   - `version`: `v1` (increment on regeneration)

   The sub-agent:
   1. Calls `glue-athena` MCP `get_table` to fetch the Gold-zone schema.
   2. Calls `shared.semantic_layer.induce_and_stage(mode="local", ...)`.
   3. Writes three artifacts to `workloads/{WORKLOAD}/config/`:
      - `ontology.ttl` — OWL2 classes, properties, hierarchy, PII annotations
      - `mappings.ttl` — R2RML TriplesMaps wiring OWL classes to Glue tables
      - `ontology_manifest.json` — `state: "STAGED_LOCAL"`, checksums, steward checklist
   4. Validates both TTL files with rdflib (auto-fix + retry up to 2×).
   5. Returns `AgentOutput` with 3 artifacts + counts + decisions.

   **Test gate**: `pytest workloads/{WORKLOAD}/tests/unit/test_owl_inducer.py
   workloads/{WORKLOAD}/tests/unit/test_r2rml_mapper.py
   workloads/{WORKLOAD}/tests/unit/test_turtle_validator.py` MUST pass
   before proceeding to Step 9. If it fails, block deployment and surface
   the failure.

   **What this step does NOT do** (these are AWS Semantic Layer / Data Steward jobs
   for when the AWS Semantic Layer platform deploys in AWS):
   - No Neptune SPARQL writes.
   - No S3 upload to a knowledge-layer bucket.
   - No DynamoDB version record.
   - No SNS steward notification.
   - No T-Box reasoning, no SHACL authoring, no VKG publish.

   When the AWS Semantic Layer platform deploys, a follow-up `ontology-publish-agent` will read
   these committed local TTL files and push them to AWS. No regeneration
   is needed — the inducer is deterministic.

   Full spawn prompt: `prompts/data-onboarding-agent/ontology-staging-agent.md`.
   Skill definition: SKILLS.md → "Skill: Ontology Staging Agent".

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
