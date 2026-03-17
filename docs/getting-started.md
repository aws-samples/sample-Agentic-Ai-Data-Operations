# Getting Started: Reusable Data Onboarding Prompts

Welcome! This guide helps you onboard any dataset using **modular, copy-paste prompts**.

---

## 📚 Documentation Overview

Your data onboarding system now has reusable prompt patterns you can use for any dataset:

| File | Purpose | When to Use |
|------|---------|-------------|
| **PROMPTS_QUICK_REFERENCE.md** | 📋 Copy-paste templates | Quick lookup for prompt structure |
| **PROMPTS_EXAMPLES.md** | 📝 Filled-out examples | See real-world usage with details |
| **SKILLS.md** (bottom section) | 📖 Full documentation | Deep dive into each pattern |
| **CLAUDE.md** | 🏗️ Architecture reference | Understand system design |

---

## 🚀 Quick Start: Onboard Your First Dataset

### Step 1: Check if it already exists
```
Check if data from [YOUR_DATA_DESCRIPTION] has already been onboarded.

Source details:
- Location: [S3_PATH or DATABASE.TABLE]
- Format: [CSV/JSON/Parquet]
- Description: [Brief description]

Report: existing workload status or confirm new data.
```

**What happens**: Claude searches all existing workloads and tells you if this data is already onboarded.

---

### Step 2: Onboard the dataset
If Step 1 says "not found", use this prompt:

```
Onboard new dataset: [DATASET_NAME]

Source:
- Type: [S3/Database/API]
- Location: [FULL_PATH]
- Format: [CSV/JSON/Parquet]
- Frequency: [Daily/Hourly/One-time]
- Credentials: [AWS Secrets Manager ARN]

Schema:
- column1: type, description, role (measure/dimension/identifier)
- column2: type, description, role

Bronze:
- Keep raw format: YES
- Retention: [DAYS]

Silver:
- Cleaning: [Dedupe on KEY, handle nulls, type casting]
- PII masking: [COLUMNS]
- Format: Apache Iceberg

Gold:
- Use case: [Reporting/Analytics/ML]
- Format: [Star Schema/Flat]
- Quality threshold: 95%

Quality Rules:
- Completeness: [Required columns non-null]
- Uniqueness: [Key must be unique]

Schedule:
- Frequency: [cron expression]
- SLA: [minutes]

Build complete pipeline with tests.
```

**What happens**: Claude creates:
- Complete folder structure (`workloads/[name]/`)
- Config files (source, semantic, transformations, quality, schedule)
- Transformation scripts (Bronze→Silver→Gold)
- Airflow DAG
- Comprehensive tests (50+ tests)
- README documentation

---

### Step 3: Validate it works

```bash
# Run tests
cd workloads/[YOUR_DATASET_NAME]
pytest tests/ -v

# Should see: 50+ tests passing ✓

# Check DAG
python3 dags/[your_dataset]_dag.py
# Should print: "DAG loaded successfully"
```

---

## 📖 Common Scenarios

### Scenario 1: Demo with Synthetic Data

**Need**: Create a demo without access to real data

```
1. Generate synthetic data for customer_demo:

Rows: 100
Columns:
- customer_id: STRING, unique, CUST-001 format
- name: STRING, realistic names
- email: STRING, 10% nulls
- segment: ENUM, Enterprise 20%, SMB 50%, Individual 30%
- country: STRING, US 60%, UK 20%, CA 10%, DE 10%

Output: shared/fixtures/customer_demo.csv with generator script
```

Then onboard it with ONBOARD prompt above.

---

### Scenario 2: Link Two Datasets

**Need**: Connect orders to customers via foreign key

```
Add relationship between workloads:

Source: order_transactions
Target: customer_master

Relationship:
- FK: orders.customer_id → customers.customer_id
- Cardinality: many-to-one
- Description: "Each order belongs to one customer"

Integrity:
- Expected validity: 98%
- Orphan handling: QUARANTINE

Update semantic.yaml, scripts, DAG, tests.
```

**What happens**: Claude adds FK validation, updates configs, adds tests for referential integrity.

---

### Scenario 3: Create a Dashboard

**Need**: Business users want to visualize the data

```
Create QuickSight dashboard: [NAME]

Data sources:
- Dataset 1: [TABLE_NAME], mode [SPICE/DIRECT_QUERY]

Visuals:
1. [VISUAL_NAME]: Type [KPI/Bar/Line/Pie], measures [AGGREGATIONS]
2. ...

Permissions: [IAM users/groups]

Create dashboard and return URL.
```

**What happens**: Claude creates QuickSight data source, datasets, dashboard with all visuals, and grants permissions.

---

### Scenario 4: Document for Audit

**Need**: Compliance team needs lineage documentation

```
Analyze data lineage for [WORKLOAD_NAME]:

Provide:
1. Source → Bronze → Silver → Gold flow
2. FK relationships
3. Column-level transformations
4. Quality scores

Generate data_product_catalog.yaml and lineage diagram.
```

**What happens**: Claude creates lineage diagrams, relationship graphs, and structured metadata for governance.

---

## 🎯 The Six Core Patterns

Use these in order for a complete data onboarding:

1. **ROUTE: Check Existing** ✅ Always first
2. **ONBOARD: Build Pipeline** 📥 Create pipeline
3. **ENRICH: Link Datasets** 🔗 Link datasets (optional)
4. **CONSUME: Create Dashboard** 📊 Visualize (optional)
5. **GOVERN: Trace Lineage** 📋 Document (optional)

Plus:
- **GENERATE: Create Data** 🎲 For demos/testing

---

## 📝 Customization Tips

### 1. Start Simple
Don't specify every detail on first try. Start with basic info:

**Minimal prompt** (works fine):
```
Onboard customer data from s3://bucket/customers.csv

Format: CSV
Frequency: Daily
Cleaning: Dedupe on customer_id, mask email/phone
Gold: Star schema for reporting
```

Claude will ask clarifying questions for anything missing.

### 2. Be Specific Where It Matters

**Critical details** (always specify):
- Source location (exact path)
- Format (CSV/JSON/Parquet)
- Key column (for deduplication)
- PII columns (for masking)
- Quality threshold (80% Silver, 95% Gold)
- Schedule (cron expression)

**Less critical** (Claude can infer or use defaults):
- Exact partitioning strategy
- Retry counts
- Alert recipients
- SLA minutes

### 3. Copy from Examples

Don't write prompts from scratch:
1. Open `PROMPTS_EXAMPLES.md`
2. Find similar scenario (e.g., "CSV from S3, daily batch")
3. Copy the whole prompt
4. Replace placeholders with your values

### 4. Iterate

First onboarding doesn't need to be perfect:
1. Get basic pipeline working
2. Run tests, see what fails
3. Refine transformations/quality rules
4. Re-run until all tests pass

---

## 🛠️ Troubleshooting

### "Tests are failing"
```bash
# Read the test output carefully
pytest tests/unit/test_transformations.py -v

# Tests tell you exactly what's wrong:
# - "FK integrity: expected 98%, got 85%" → Need better data or lower threshold
# - "Schema mismatch: missing column revenue" → Add revenue calculation to transform script
# - "Quality score 89%, threshold 95%" → Need stricter data validation
```

Fix one test at a time, re-run, repeat.

### "DAG won't parse"
```bash
# Run the DAG file directly to see Python errors
python3 workloads/my_dataset/dags/my_dataset_dag.py

# Common issues:
# - Missing imports: pip install apache-airflow-providers-amazon
# - Typo in operator name: GlueJobOperator (not AwsGlueJobOperator)
# - Invalid cron: Use "0 6 * * *" not "6am daily"
```

### "Claude asks too many questions"
Be more specific in your prompt. Compare:

**Vague** → Many questions:
```
Onboard customer data
```

**Specific** → Few questions:
```
Onboard customer_master from s3://bucket/crm/customers.csv
- CSV, daily at 6am
- Columns: customer_id, name, email (PII), phone (PII), segment, status
- Dedupe on customer_id
- Mask email/phone in Silver
- Star schema in Gold (fact: customer_activity, dims: customer, geography)
- Quality: 95% threshold
```

### "I want to modify an existing workload"
```
Read workloads/[NAME]/config/semantic.yaml and workloads/[NAME]/scripts/transform/bronze_to_silver.py

Then: Update the [WHAT YOU WANT TO CHANGE] to [NEW BEHAVIOR]
```

Claude will edit existing files instead of creating new ones.

---

## 💡 Best Practices

### ✅ DO
- Always run ROUTE (Check Existing) first
- Specify PII columns for masking
- Set quality thresholds (80% Silver, 95% Gold)
- Use Secrets Manager for credentials
- Test with small data first (100 rows)
- Document relationships in semantic.yaml

### ❌ DON'T
- Skip ROUTE and create duplicate workloads
- Hardcode secrets in code or config
- Skip quality rules (bad data will reach Gold)
- Use Bronze for queries (use Silver/Gold)
- Modify Bronze zone data (it's immutable)

---

## 📚 Next Steps

**For your first onboarding:**
1. Open `PROMPTS_EXAMPLES.md`
2. Find an example similar to your data
3. Copy the ROUTE prompt, fill in your details, send to Claude
4. If not found, copy the ONBOARD prompt, fill in, send
5. Wait for pipeline generation (~5-10 minutes)
6. Run tests: `pytest workloads/[NAME]/tests/ -v`
7. If tests pass, you're done! Deploy to AWS.

**For ongoing work:**
- Keep `PROMPTS_QUICK_REFERENCE.md` open for copy-paste
- Use GENERATE to create demo data for testing
- Use ENRICH to document relationships between datasets
- Use CONSUME to create dashboards for stakeholders
- Use GOVERN to generate lineage docs for governance

**Need help?**
- See detailed examples: `PROMPTS_EXAMPLES.md`
- See full documentation: `SKILLS.md` → Modular Prompt Patterns
- See architecture: `CLAUDE.md`

---

## 🎉 You're Ready!

You now have:
- ✅ 6 reusable prompt patterns
- ✅ Copy-paste templates
- ✅ Real-world examples
- ✅ Troubleshooting guide

Start with ROUTE (Check Existing) and onboard your first dataset!
