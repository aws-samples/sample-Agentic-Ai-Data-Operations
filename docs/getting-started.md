# Getting Started: Reusable Data Onboarding Prompts

Welcome! This guide helps you onboard any dataset using **modular, copy-paste prompts**.

---

## 📚 Documentation Overview

Your data onboarding system now has reusable prompt patterns you can use for any dataset:

| File | Purpose | When to Use |
|------|---------|-------------|
| **prompts/00-setup-environment.md** | 🏗️ First-time AWS setup | Run ONCE after cloning repo into new AWS account |
| **prompts/** (01-route through 06-govern) | 📋 Copy-paste templates | Quick lookup for prompt structure |
| **prompts/examples.md** | 📝 Filled-out examples | See real-world usage with details |
| **prompts/regulation/** | 🔒 Regulation-specific controls | When GDPR, CCPA, HIPAA, SOX, or PCI DSS compliance is required |
| **SKILLS.md** (bottom section) | 📖 Full documentation | Deep dive into each pattern |
| **CLAUDE.md** | 🏗️ Architecture reference | Understand system design |
| **deploy_to_aws.py** | 🚀 Deployment script | Deploy workload to AWS (Glue, MWAA, QuickSight) |

---

## 🏗️ First Time? Setup Your AWS Environment

If this is a fresh clone into a new AWS account, run the setup prompt first:

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

Existing resources: none
```

This creates all AWS prerequisites (IAM roles, S3 bucket, KMS keys, Glue databases, LF-Tags) interactively. See `prompts/00-setup-environment.md` for full details.

**Multi-account deployment**: The setup defaults to single-account. If you need the Glue catalog + Lake Formation in one account ("Account A") and Glue jobs + MWAA + S3 in a consumer account ("Account B"), see [`multi-account-deployment.md`](multi-account-deployment.md) — the setup prompt will ask a single-vs-multi question and wire `catalog_account_id` + `sts:AssumeRole` across generated artifacts.

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

Output: demo/sample_data/customer_demo.csv with generator script
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

### Scenario 5a: Demo with Gateway (Cloud-Hosted Tools, Local Agent)

**Need**: Team wants cloud-hosted MCP tools without local Python/uv setup, but agent stays on laptop

```
1. Deploy all 13 MCP servers to Agentcore Gateway:
   → Run prompts/09-deploy-agentcore-gateway.md

2. Switch to Gateway tools:
   → Replace .mcp.json with .mcp.gateway.json

3. Onboard data as usual:
   → Run prompts/03-onboard-build-pipeline.md
```

**What happens**:
- Gateway: All 13 MCP servers (4 custom FastMCP + 9 PyPI) hosted in cloud, each with least-privilege IAM
- Agent: Runs in Claude Code on your laptop (human-in-the-loop)
- Sub-agents: Spawned locally via Claude Code `Agent` tool
- Same onboarding workflow as before -- only the tool transport changes (stdio to SSE)

To revert to fully local: `git checkout .mcp.json`

### Scenario 5b: Production with Runtime (Cloud-Hosted Tools + Cloud Agent)

**Need**: Agent accessible via API for production pipelines, integrations, or multi-user access

```
1. Deploy all 13 MCP servers to Agentcore Gateway:
   → Run prompts/09-deploy-agentcore-gateway.md (if not already deployed)

2. Deploy agent to Agentcore Runtime:
   → Run prompts/10-deploy-agentcore-runtime.md

3. Invoke agent via API:
   → aws bedrock-agent-runtime invoke-agent --agent-id {ID} --input-text "Onboard..."
```

**What happens**:
- Gateway: Same Gateway as Scenario 5a (deployed once, shared by both modes)
- Runtime: Data Onboarding Agent accessible via API, connected to all 13 Gateway tools, with persistent memory
- Human-in-the-loop: Optional -- agent can run autonomously or pause for approval via API

See `prompts/environment-setup-agent/agentcore/README.md` for architecture details.

---

### Scenario 6: Deploy to MWAA

**Need**: Deploy the DAG and dependencies to Amazon Managed Workflows for Apache Airflow

**Option 1: Using the deployment script**
```bash
# Deploy workload to MWAA S3 bucket
python3 deploy_to_aws.py --mwaa-bucket=my-mwaa-bucket-name --workload=customer_master

# The script will:
# 1. Upload DAG file to s3://my-mwaa-bucket-name/dags/
# 2. Sync shared utilities to s3://my-mwaa-bucket-name/plugins/
# 3. Upload Glue scripts to configured S3 location
# 4. Verify all files are in place
```

**Option 2: Manual deployment**
```bash
# Upload DAG
aws s3 cp workloads/customer_master/dags/customer_master_dag.py \
  s3://my-mwaa-bucket-name/dags/

# Sync shared utilities
aws s3 sync shared/ s3://my-mwaa-bucket-name/plugins/shared/ \
  --exclude "*.pyc" --exclude "__pycache__/*"
```

**Set Airflow Variables** (in MWAA UI or via CLI):
```json
{
  "glue_script_s3_path": "s3://my-glue-scripts-bucket/scripts/",
  "glue_iam_role": "arn:aws:iam::123456789012:role/GlueJobRole",
  "aws_account_id": "123456789012",
  "kms_key_alias": "alias/data-pipeline-key"
}
```

**Verify**:
1. Open MWAA Airflow UI
2. Check that `customer_master_dag` appears in the DAG list
3. Unpause the DAG
4. Trigger a manual run to test

**What happens**: Your DAG is deployed to MWAA and ready to run on the configured schedule.

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

### 5. Load Regulation-Specific Prompts When Needed

**Important**: Regulation-specific prompts are NOT loaded by default. Only use them when compliance is explicitly required.

During discovery (Phase 1), if the user mentions compliance requirements:
```
Does this data require regulatory compliance? (GDPR, CCPA, HIPAA, SOX, PCI DSS)
```

If YES, load the appropriate prompt from `prompts/regulation/`:
- `prompts/regulation/gdpr.md` — GDPR (EU data protection)
- `prompts/regulation/ccpa.md` — CCPA (California privacy)
- `prompts/regulation/hipaa.md` — HIPAA (healthcare data)
- `prompts/regulation/sox.md` — SOX (financial reporting)
- `prompts/regulation/pci_dss.md` — PCI DSS (payment card data)

These prompts add:
- Mandatory data residency controls
- Enhanced encryption and access controls
- Audit trail requirements
- Data retention and deletion policies
- Consent tracking (GDPR/CCPA)
- Field-level encryption (HIPAA/PCI DSS)

**Example**:
```
User: "We need to onboard patient records"
Claude: "Does this data require HIPAA compliance?"
User: "Yes"
Claude: [loads prompts/regulation/hipaa.md] → adds PHI encryption, audit logging, access controls
```

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
1. Open `prompts/examples.md`
2. Find an example similar to your data
3. Copy the ROUTE prompt, fill in your details, send to Claude
4. If not found, copy the ONBOARD prompt, fill in, send
5. Wait for pipeline generation (~5-10 minutes)
6. Run tests: `pytest workloads/[NAME]/tests/ -v`
7. If tests pass, you're done! Deploy to AWS with `deploy_to_aws.py`

**For ongoing work:**
- Keep `prompts/` folder open for copy-paste templates
- Use GENERATE to create demo data for testing
- Use ENRICH to document relationships between datasets
- Use CONSUME to create dashboards for stakeholders
- Use GOVERN to generate lineage docs for governance
- Load `prompts/regulation/` only when compliance is required

**Need help?**
- See detailed examples: `prompts/examples.md`
- See full documentation: `SKILLS.md` → Modular Prompt Patterns
- See architecture: `CLAUDE.md`
- See deployment guide: `docs/aws-account-setup.md`

---

## 🎉 You're Ready!

You now have:
- ✅ 6 reusable prompt patterns
- ✅ Copy-paste templates
- ✅ Real-world examples
- ✅ Troubleshooting guide

Start with ROUTE (Check Existing) and onboard your first dataset!
