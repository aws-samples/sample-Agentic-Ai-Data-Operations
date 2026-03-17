# Prompt Workflow Guide

This document shows how the 6 modular prompts work together in real-world data onboarding scenarios.

## Overview: The 6 Prompts

| Prompt | Purpose | When to Use | MCP Servers Used |
|--------|---------|-------------|------------------|
| **ROUTE** | Check if data already exists | Always run FIRST | `local-filesystem` |
| **GENERATE** | Create synthetic test data | Demo/testing only | `core` (S3) |
| **ONBOARD** | Build complete pipeline | New data source | All servers |
| **ENRICH** | Link datasets via relationships | After ONBOARD | `sagemaker-catalog`, `dynamodb` |
| **CONSUME** | Create dashboards/reports | After ONBOARD or ENRICH | `redshift`, `aws-dataprocessing` |
| **GOVERN** | Document lineage for compliance | Anytime for audit | `cloudtrail`, `local-filesystem` |

---

## Workflow Patterns

### Pattern 1: New Production Data Source

**Scenario**: Onboard a new production dataset (e.g., customer orders from RDS)

```
Step 1: ROUTE
   ↓ (not found)
Step 2: ONBOARD
   ↓ (pipeline created)
Step 3: ENRICH (optional)
   ↓ (if linking to other datasets)
Step 4: CONSUME
   ↓ (create dashboard)
Step 5: GOVERN
   ↓ (document for audit)
```

**Execution**:

```bash
# Step 1: Check if already onboarded
ROUTE: "Check if we already have customer orders data"

# Step 2: Onboard the data
ONBOARD: "Onboard customer orders from RDS database rds-prod-orders,
table public.orders, to Bronze→Silver→Gold pipeline.
Silver: cleaned orders with valid customer_id.
Gold: reporting tables for revenue analysis."

# Step 3: Link to customer dimension
ENRICH: "Link orders_gold.customer_id to customers_gold.customer_id"

# Step 4: Create dashboard
CONSUME: "Create QuickSight dashboard showing revenue by customer segment"

# Step 5: Document lineage
GOVERN: "Trace lineage for orders revenue from source to dashboard"
```

**MCP Flow**:
```
ROUTE:
  └─> local-filesystem.list_workloads()

ONBOARD:
  ├─> aws-dataprocessing.create_crawler()
  ├─> aws-dataprocessing.start_query_execution() [profiling]
  ├─> sagemaker-catalog.put_custom_metadata()
  ├─> aws-dataprocessing.create_job() [Bronze→Silver]
  ├─> s3-tables.create_table() [Silver Iceberg]
  ├─> aws-dataprocessing.create_data_quality_ruleset()
  ├─> aws-dataprocessing.create_job() [Silver→Gold]
  ├─> s3-tables.create_table() [Gold Iceberg]
  └─> stepfunctions.create_state_machine()

ENRICH:
  ├─> sagemaker-catalog.put_custom_metadata() [relationship]
  └─> dynamodb.put_item() [join semantics in SynoDB]

CONSUME:
  ├─> aws-dataprocessing.start_query_execution() [test Gold data]
  └─> [QuickSight API calls - not yet in MCP]

GOVERN:
  ├─> cloudtrail.lookup_events() [audit trail]
  └─> local-filesystem.read_file() [config files]
```

---

### Pattern 2: Demo/Test Environment

**Scenario**: Create test environment with synthetic data

```
Step 1: GENERATE (customers)
   ↓
Step 2: GENERATE (orders)
   ↓
Step 3: ONBOARD (customers)
   ↓
Step 4: ONBOARD (orders)
   ↓
Step 5: ENRICH (link them)
   ↓
Step 6: CONSUME (test dashboard)
```

**Execution**:

```bash
# Generate synthetic datasets
GENERATE: "Create 1000 synthetic customer records with id, name, email,
region, segment. Include 5% invalid emails and 2% nulls."

GENERATE: "Create 5000 synthetic order records referencing the customer
dataset. Include revenue, order_date, product_category.
10% of orders reference non-existent customer_id."

# Onboard both datasets
ONBOARD: "Onboard customers CSV from s3://test-data/customers.csv"

ONBOARD: "Onboard orders CSV from s3://test-data/orders.csv"

# Link them
ENRICH: "Link orders.customer_id to customers.id as foreign key"

# Create test dashboard
CONSUME: "Create dashboard showing revenue by customer segment"
```

**MCP Flow**:
```
GENERATE (customers):
  ├─> [Python faker library - no MCP]
  └─> core.s3.put_object() [upload to S3]

GENERATE (orders):
  ├─> [Python faker library - no MCP]
  └─> core.s3.put_object() [upload to S3]

ONBOARD (customers):
  └─> [Full pipeline as in Pattern 1]

ONBOARD (orders):
  └─> [Full pipeline as in Pattern 1]

ENRICH:
  └─> [Relationship metadata as in Pattern 1]

CONSUME:
  └─> [Dashboard as in Pattern 1]
```

---

### Pattern 3: Incremental Enhancement

**Scenario**: Existing pipeline needs a new relationship or dashboard

```
Existing: orders_gold and customers_gold already exist
   ↓
Step 1: ROUTE (confirm exists)
   ↓
Step 2: ENRICH (add relationship)
   ↓
Step 3: CONSUME (new dashboard)
```

**Execution**:

```bash
# Verify datasets exist
ROUTE: "Check if orders and customers workloads exist"

# Add relationship
ENRICH: "Link orders_gold.customer_id to customers_gold.customer_id
with LEFT JOIN semantics"

# Create new dashboard
CONSUME: "Create executive dashboard showing monthly revenue trend
by customer segment with YoY comparison"
```

**MCP Flow**:
```
ROUTE:
  └─> local-filesystem.search_workloads_by_source()

ENRICH:
  ├─> sagemaker-catalog.get_custom_metadata() [validate both tables exist]
  ├─> sagemaker-catalog.put_custom_metadata() [add relationship]
  └─> dynamodb.put_item() [store join semantics for Analysis Agent]

CONSUME:
  ├─> aws-dataprocessing.start_query_execution() [validate joined query works]
  └─> [Create QuickSight dashboard]
```

---

### Pattern 4: Compliance Audit

**Scenario**: Auditor requests lineage documentation for PII data

```
Step 1: GOVERN (trace lineage)
   ↓
Step 2: GOVERN (document access logs)
   ↓
Step 3: GOVERN (generate report)
```

**Execution**:

```bash
# Trace data lineage
GOVERN: "Trace lineage for customer_email field from source (RDS)
through Bronze→Silver→Gold to all downstream dashboards"

# Document access
GOVERN: "Show all access to customer_gold table in the last 90 days
with user, timestamp, and query"

# Generate compliance report
GOVERN: "Generate PII compliance report for customer data showing
encryption, access controls, and audit trail"
```

**MCP Flow**:
```
GOVERN (lineage):
  ├─> local-filesystem.get_workload_config() [read transformations.yaml]
  ├─> sagemaker-catalog.get_custom_metadata() [column lineage]
  └─> local-filesystem.write_file() [lineage diagram]

GOVERN (access logs):
  ├─> cloudtrail.lookup_events() [API access logs]
  └─> aws-dataprocessing.start_query_execution() [query Athena audit table]

GOVERN (compliance report):
  ├─> sagemaker-catalog.get_custom_metadata() [PII flags]
  ├─> iam.get_role_policy() [access controls]
  ├─> core.kms.describe_key() [encryption keys]
  └─> local-filesystem.write_file() [compliance report PDF]
```

---

## Detailed Workflow: ONBOARD Prompt

The ONBOARD prompt is the master orchestrator. Here's what happens inside:

```
ONBOARD Prompt Execution
│
├─ Phase 1: DISCOVERY (inline in main conversation)
│  │
│  ├─ Section 1: Source Details
│  │  └─> User provides: location, format, credentials, frequency
│  │
│  ├─ Section 2: Column Identification
│  │  └─> User provides: PK, PII columns, exclusions
│  │
│  ├─ Section 3: Cleaning Rules
│  │  └─> User provides: dedup, nulls, type casting
│  │
│  ├─ Section 4: Metrics & Dimensions
│  │  └─> User provides: column roles, aggregations, hierarchies
│  │
│  ├─ Section 5: Quality Rules
│  │  └─> User provides: thresholds, compliance requirements
│  │
│  └─ Section 6: Scheduling
│     └─> User provides: cron, dependencies, failure handling
│
├─ Phase 2: DEDUPLICATION & VALIDATION (inline)
│  │
│  ├─> MCP: local-filesystem.search_workloads_by_source()
│  │   └─> Check for duplicate sources
│  │
│  └─> MCP: core.s3.list_objects_v2() or aws-dataprocessing.get_table()
│      └─> Validate source connectivity
│
├─ Phase 3: PROFILING (spawn Metadata Agent via Agent tool)
│  │
│  ├─> MCP: aws-dataprocessing.create_crawler()
│  │   └─> Discover schema
│  │
│  ├─> MCP: aws-dataprocessing.start_query_execution()
│  │   └─> Profile 5% sample (stats, nulls, PII patterns)
│  │
│  ├─> Present profiling results to human
│  │   └─> Human confirms or adjusts
│  │
│  └─> MCP: sagemaker-catalog.put_custom_metadata()
│      └─> Store technical metadata + business context
│
├─ Phase 4: BUILD PIPELINE (spawn 4 sub-agents via Agent tool)
│  │
│  ├─> Sub-Agent 1: TRANSFORMATION AGENT
│  │  │  Generates:
│  │  │  • transformations.yaml
│  │  │  • scripts/transform/bronze_to_silver.py
│  │  │  • scripts/transform/silver_to_gold.py
│  │  │  • tests/test_transformations.py
│  │  │
│  │  │  ─── TEST GATE (main conversation runs tests) ───
│  │  │
│  │  │  MCP Execution (main conversation):
│  │  ├─> aws-dataprocessing.create_job() [Bronze→Silver]
│  │  ├─> s3-tables.create_table() [Silver Iceberg]
│  │  ├─> aws-dataprocessing.create_job() [Silver→Gold]
│  │  └─> s3-tables.create_table() [Gold Iceberg]
│  │
│  ├─> Sub-Agent 2: QUALITY AGENT
│  │  │  Generates:
│  │  │  • quality_rules.yaml
│  │  │  • scripts/quality/validate_silver.py
│  │  │  • scripts/quality/validate_gold.py
│  │  │  • tests/test_quality.py
│  │  │
│  │  │  ─── TEST GATE (main conversation runs tests) ───
│  │  │
│  │  │  MCP Execution (main conversation):
│  │  ├─> aws-dataprocessing.create_data_quality_ruleset() [Silver]
│  │  ├─> aws-dataprocessing.create_data_quality_ruleset() [Gold]
│  │  └─> cloudwatch.put_metric_alarm() [quality alerts]
│  │
│  ├─> Sub-Agent 3: METADATA AGENT
│  │  │  Generates:
│  │  │  • config/semantic.yaml (enriched from profiling)
│  │  │  • tests/test_metadata.py
│  │  │
│  │  │  ─── TEST GATE (main conversation runs tests) ───
│  │  │
│  │  │  MCP Execution (main conversation):
│  │  └─> sagemaker-catalog.put_custom_metadata() [final version]
│  │
│  └─> Sub-Agent 4: ORCHESTRATION DAG AGENT
│     │  Generates:
│     │  • dags/pipeline_dag.py (Step Functions state machine)
│     │  • tests/test_dag.py
│     │
│     │  ─── TEST GATE (main conversation runs tests) ───
│     │
│     │  MCP Execution (main conversation):
│     ├─> stepfunctions.create_state_machine()
│     ├─> eventbridge.put_rule() [scheduling]
│     ├─> eventbridge.put_targets() [trigger Step Functions]
│     ├─> sns-sqs.create_topic() [alerts]
│     └─> lambda.create_function() [custom triggers if needed]
│
└─ Phase 5: SUMMARY & APPROVAL
   │
   ├─> Present all artifacts to human
   │   • Configs: source.yaml, semantic.yaml, transformations.yaml, quality_rules.yaml
   │   • Scripts: All Python scripts in scripts/
   │   • Tests: All test files (X/X passing)
   │   • MCP Operations: Summary of what will be deployed
   │
   ├─> Human reviews and approves
   │
   └─> Execute all MCP operations
       └─> Pipeline deployed to AWS
```

---

## Decision Tree: Which Prompt to Use

```
START: Do you have data to work with?
│
├─ NO → Need test data?
│  │
│  ├─ YES → Use GENERATE
│  │  └─> Then proceed to ONBOARD
│  │
│  └─ NO → Wait for real data source
│
└─ YES → Is it already onboarded?
   │
   ├─ UNKNOWN → Use ROUTE to check
   │  │
   │  ├─ FOUND → Skip ONBOARD
   │  │  └─> Continue to ENRICH/CONSUME/GOVERN
   │  │
   │  └─ NOT FOUND → Use ONBOARD
   │
   └─ YES → What do you want to do?
      │
      ├─ Link to another dataset → Use ENRICH
      │
      ├─ Create dashboard/report → Use CONSUME
      │
      ├─ Document for audit → Use GOVERN
      │
      └─ Fix/update pipeline → Re-run ONBOARD (updates existing)
```

---

## Common Workflows

### Workflow A: First-Time Setup (Greenfield)

**Goal**: Set up complete data platform from scratch

```bash
# Day 1: Generate test data
GENERATE: "Create customers dataset (1000 records)"
GENERATE: "Create orders dataset (5000 records)"
GENERATE: "Create products dataset (50 records)"

# Day 1: Onboard test data
ONBOARD: "Onboard customers"
ONBOARD: "Onboard orders"
ONBOARD: "Onboard products"

# Day 2: Link datasets
ENRICH: "Link orders to customers"
ENRICH: "Link orders to products"

# Day 2: Create initial dashboards
CONSUME: "Create revenue dashboard"
CONSUME: "Create customer analytics dashboard"

# Day 3: Document for compliance
GOVERN: "Document lineage for all datasets"

# Day 4: Replace with production data
ONBOARD: "Onboard production customers from RDS"
ONBOARD: "Onboard production orders from RDS"
ONBOARD: "Onboard production products from RDS"

# Day 5: Update dashboards
CONSUME: "Update dashboards to use production data"
```

**MCP Servers Used** (in order):
1. `core` (S3 upload)
2. `local-filesystem` (check workloads)
3. `aws-dataprocessing` (Glue, Athena)
4. `s3-tables` (Iceberg tables)
5. `sagemaker-catalog` (metadata)
6. `dynamodb` (SynoDB)
7. `stepfunctions` (orchestration)
8. `redshift` (dashboards)
9. `cloudtrail` (audit)

---

### Workflow B: Incremental Growth (Brownfield)

**Goal**: Add new data source to existing platform

```bash
# Check if new data source exists
ROUTE: "Check if we have product reviews data"
# Result: Not found

# Onboard new source
ONBOARD: "Onboard product reviews from S3 bucket s3://reviews/raw/"

# Link to existing products
ENRICH: "Link reviews.product_id to products_gold.product_id"

# Create new dashboard
CONSUME: "Create product sentiment dashboard using reviews and products"

# Document new lineage
GOVERN: "Update lineage documentation to include reviews dataset"
```

---

### Workflow C: Data Quality Issue Investigation

**Goal**: Investigate and fix data quality problems

```bash
# Check current state
ROUTE: "Show status of orders workload"

# Run quality checks manually
ONBOARD: "Re-run quality checks on orders_silver"
# (ONBOARD in update mode only runs quality phase)

# Review quality results
GOVERN: "Show quality score history for orders_silver"

# Fix transformation rules
ONBOARD: "Update orders transformation to filter out invalid dates"
# (ONBOARD in update mode regenerates transformations)

# Verify fix
CONSUME: "Query orders_gold to verify date ranges are valid"
```

---

### Workflow D: Compliance Audit Response

**Goal**: Respond to auditor requests

```bash
# Trace specific data element
GOVERN: "Trace lineage for customer_ssn field end-to-end"

# Show access history
GOVERN: "List all users who accessed customer_gold in last 90 days"

# Show encryption status
GOVERN: "Document encryption methods for all customer PII fields"

# Generate compliance report
GOVERN: "Generate GDPR compliance report for customer data"

# Update access controls (if needed)
# (Use IAM MCP server directly - not a prompt pattern yet)
```

---

## Prompt Chaining Syntax

When running multiple prompts in sequence, use this format:

```bash
# Sequential execution (wait for each to complete)
PROMPT1 && PROMPT2 && PROMPT3

# Parallel execution (all at once - only if independent)
PROMPT1 & PROMPT2 & PROMPT3 & wait

# Conditional execution
PROMPT1 || PROMPT2  # Run PROMPT2 only if PROMPT1 fails
```

**Example**:

```bash
# Generate and immediately onboard
GENERATE: "Create test customers" && \
ONBOARD: "Onboard customers from s3://test/customers.csv"

# Onboard multiple datasets in parallel
ONBOARD: "Onboard customers" & \
ONBOARD: "Onboard orders" & \
ONBOARD: "Onboard products" & \
wait

# Conditional: Only link if both datasets exist
ROUTE: "Check customers and orders exist" && \
ENRICH: "Link orders to customers"
```

---

## MCP Server Usage by Prompt

| Prompt | MCP Servers | Operations |
|--------|-------------|------------|
| **ROUTE** | `local-filesystem` | `list_workloads`, `search_workloads_by_source` |
| **GENERATE** | `core` | `s3.put_object`, `s3.create_bucket` |
| **ONBOARD** | `local-filesystem`<br>`aws-dataprocessing`<br>`s3-tables`<br>`sagemaker-catalog`<br>`dynamodb`<br>`stepfunctions`<br>`eventbridge`<br>`sns-sqs`<br>`cloudwatch` | Full pipeline deployment |
| **ENRICH** | `sagemaker-catalog`<br>`dynamodb` | `put_custom_metadata` (relationships)<br>`put_item` (join semantics) |
| **CONSUME** | `aws-dataprocessing`<br>`redshift` | `start_query_execution`<br>`execute_statement` |
| **GOVERN** | `cloudtrail`<br>`local-filesystem`<br>`sagemaker-catalog` | `lookup_events`<br>`read_file`<br>`get_custom_metadata` |

---

## Error Handling in Workflows

### When a Prompt Fails

```
ONBOARD fails at Transformation Agent
   ↓
Main conversation receives error
   ↓
Retry logic (max 2 retries)
   ↓
Still fails?
   ↓
Escalate to human with:
   • Full error context
   • What was attempted
   • Suggested fixes
   ↓
Human makes decision:
   ├─ Fix input and re-run
   ├─ Skip this phase
   └─ Abort workflow
```

### When an MCP Call Fails

```
MCP server returns error
   ↓
Orchestrator logs error
   ↓
Check if retryable
   ├─ YES → Exponential backoff (3 attempts)
   └─ NO → Fallback to AWS CLI (if available)
       └─ Still fails → Escalate to human
```

---

## Visual Workflow Example: E-Commerce Platform

```
Day 1: Foundation
──────────────────
GENERATE (customers) → s3://test/customers.csv
GENERATE (products)  → s3://test/products.csv
GENERATE (orders)    → s3://test/orders.csv

ONBOARD (customers)  → workloads/customers/ [Bronze/Silver/Gold]
ONBOARD (products)   → workloads/products/  [Bronze/Silver/Gold]
ONBOARD (orders)     → workloads/orders/    [Bronze/Silver/Gold]

Day 2: Relationships
────────────────────
ENRICH (orders→customers) → FK relationship + join semantics
ENRICH (orders→products)  → FK relationship + join semantics

Day 3: Analytics
────────────────
CONSUME (revenue dashboard)         → QuickSight
CONSUME (customer analytics)        → QuickSight
CONSUME (product performance)       → QuickSight

Day 4: Compliance
─────────────────
GOVERN (customer PII lineage)      → lineage diagram
GOVERN (order audit trail)         → CloudTrail logs
GOVERN (encryption documentation)  → compliance PDF

Day 5: Production
─────────────────
ONBOARD (prod customers from RDS)  → Replace test data
ONBOARD (prod products from RDS)   → Replace test data
ONBOARD (prod orders from RDS)     → Replace test data

CONSUME (update dashboards)        → Point to prod Gold tables
```

---

## Monitoring Workflow Execution

Every prompt execution generates logs:

```
logs/mcp/{workload_name}/{timestamp}.log     # Human-readable
logs/mcp/{workload_name}/{timestamp}.json    # Machine-readable
```

**Monitor in real-time**:

```bash
# Tail console log
tail -f logs/mcp/customers/20260316_*.log

# Parse JSON for metrics
jq '.steps[] | {step: .step_name, status: .status, duration: .duration_seconds}' \
   logs/mcp/customers/20260316_*.json
```

---

## Best Practices

### ✅ DO

1. **Always ROUTE first** - Prevent duplicate work
2. **Test with GENERATE** - Validate pipeline before production data
3. **Use ENRICH after ONBOARD** - Add relationships incrementally
4. **Document with GOVERN** - Create audit trail as you go
5. **Review MCP logs** - Check what was actually executed

### ❌ DON'T

1. **Don't skip ROUTE** - Wastes time onboarding duplicates
2. **Don't ONBOARD without discovery** - Answer all questions first
3. **Don't skip test gates** - Sub-agents must pass tests
4. **Don't ignore MCP errors** - Fix issues immediately
5. **Don't forget GOVERN** - Document lineage for compliance

---

## Summary

The 6 prompts form a complete data lifecycle:

1. **ROUTE** - Prevent duplicates
2. **GENERATE** - Create test data
3. **ONBOARD** - Build pipeline (Bronze→Silver→Gold)
4. **ENRICH** - Add relationships
5. **CONSUME** - Create dashboards
6. **GOVERN** - Document for audit

All prompts use MCP servers for AWS operations, providing:
- ✅ Auditability (every operation logged)
- ✅ Repeatability (replay from logs)
- ✅ Standardization (consistent interface)
- ✅ Visibility (clear step-by-step execution)

Follow the workflow patterns above for your specific use case!
