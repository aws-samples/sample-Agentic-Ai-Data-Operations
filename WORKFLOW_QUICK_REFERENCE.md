# Workflow Quick Reference Card

## 🎯 Which Prompt When?

```
┌─────────────────────────────────────────────────────────────┐
│                    START HERE                               │
│                                                             │
│  Do you know if this data is already onboarded?            │
│                                                             │
│  NO → Use ROUTE first                                      │
│  YES → Skip to next question                               │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Is this data already in the system?                       │
│                                                             │
│  YES → Go to Enhancement Scenarios                         │
│  NO → Continue below                                        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Do you have real data or need test data?                  │
│                                                             │
│  Real Data → Use ONBOARD                                    │
│  Need Test → Use GENERATE, then ONBOARD                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Common Scenarios (Copy-Paste Ready)

### Scenario 1: Brand New Dataset (Production)

```bash
# Step 1: Check if exists
ROUTE: "Check if we have [dataset_name] data"

# Step 2: Onboard
ONBOARD: "Onboard [dataset_name] from [source_type] [source_location].
Schema: [describe columns].
Gold format: [reporting/analytics/ML/API].
Quality threshold: 0.85 for Silver, 0.95 for Gold."
```

**Replace**:
- `[dataset_name]` → e.g., "customer orders"
- `[source_type]` → e.g., "RDS database", "S3 bucket", "API endpoint"
- `[source_location]` → e.g., "rds-prod.us-east-1", "s3://data-lake/raw/"
- `[describe columns]` → e.g., "order_id, customer_id, amount, order_date"
- Gold format → Choose: "Reporting & Dashboards" or "Ad-hoc Analytics" or "ML/Feature Engineering" or "API/Real-time"

---

### Scenario 2: Demo/Test Environment

```bash
# Step 1: Generate test data
GENERATE: "Create [N] synthetic [entity] records with columns: [list columns].
Include realistic data quality issues: [describe issues]."

# Step 2: Onboard test data
ONBOARD: "Onboard [entity] from s3://test-data/[entity].csv.
Silver: [cleaning rules].
Gold: [aggregation rules]."
```

**Example**:
```bash
GENERATE: "Create 1000 synthetic customer records with id, name, email, region, segment.
Include 5% invalid emails, 2% null regions, 1% duplicate IDs."

ONBOARD: "Onboard customers from s3://test-data/customers.csv.
Silver: Remove duplicates by ID, validate emails, fill null regions with 'Unknown'.
Gold: Create customer dimension table with SCD Type 1."
```

---

### Scenario 3: Link Two Existing Datasets

```bash
# Step 1: Verify both exist
ROUTE: "Check if [dataset1] and [dataset2] workloads exist"

# Step 2: Add relationship
ENRICH: "Link [dataset1].[fk_column] to [dataset2].[pk_column].
Join type: [LEFT/INNER/FULL].
Describe business relationship: [explanation]."
```

**Example**:
```bash
ROUTE: "Check if orders and customers workloads exist"

ENRICH: "Link orders.customer_id to customers.id.
Join type: LEFT JOIN (keep all orders, even without customer match).
Business rule: Orders without matching customer_id are guest checkouts."
```

---

### Scenario 4: Create Dashboard

```bash
# Step 1: Ensure data is in Gold
ROUTE: "Check if [dataset] has Gold zone data"

# Step 2: Create dashboard
CONSUME: "Create [dashboard_type] dashboard showing:
- [Metric 1]
- [Metric 2]
- [Metric 3]
Filters: [list filters]
Refresh: [schedule]"
```

**Example**:
```bash
ROUTE: "Check if sales workload has Gold zone data"

CONSUME: "Create executive dashboard showing:
- Total revenue by month (last 12 months)
- Revenue by product category (top 10)
- Customer acquisition trend
Filters: Region, Product Line, Customer Segment
Refresh: Daily at 6am"
```

---

### Scenario 5: Audit/Compliance Request

```bash
# Trace lineage
GOVERN: "Trace lineage for [specific_field] from source to all destinations"

# Show access history
GOVERN: "Show all users who accessed [dataset] in last [N] days"

# Generate report
GOVERN: "Generate [compliance_type] report for [dataset] showing:
- Data sources
- Transformations applied
- PII handling
- Access controls
- Encryption methods"
```

**Example**:
```bash
GOVERN: "Trace lineage for customer_ssn field from RDS source through all zones to dashboards"

GOVERN: "Show all users who accessed customer_gold table in last 90 days"

GOVERN: "Generate GDPR compliance report for customer data showing:
- Source: RDS prod database
- PII fields: email, phone, ssn
- Encryption: AES-256 with KMS
- Access: Role-based with Lake Formation
- Retention: 7 years in archive"
```

---

## 📋 Workflow Templates

### Template A: Single Dataset Onboarding

```
1. ROUTE → Check existence
2. ONBOARD → Create pipeline
3. CONSUME → Create initial dashboard
4. GOVERN → Document lineage
```

**Time**: ~2-4 hours (depending on data complexity)

---

### Template B: Multi-Dataset Integration

```
1. ROUTE → Check all datasets
2. GENERATE → Create test data if needed
3. ONBOARD → Dataset 1
4. ONBOARD → Dataset 2
5. ONBOARD → Dataset 3
6. ENRICH → Link Dataset 1 ↔ Dataset 2
7. ENRICH → Link Dataset 2 ↔ Dataset 3
8. CONSUME → Create integrated dashboard
9. GOVERN → Document full lineage
```

**Time**: ~1-2 days

---

### Template C: Production Cutover

```
Day 1: Test Environment
1. GENERATE → Test data
2. ONBOARD → Test pipeline
3. CONSUME → Test dashboard
4. Validate all works

Day 2: Production
5. ONBOARD → Production data (same config)
6. CONSUME → Update dashboard to prod tables
7. GOVERN → Document production lineage
8. Monitor quality scores
```

---

## 🔄 Prompt Execution Patterns

### Sequential Pattern (Must Complete in Order)

```bash
ROUTE: "Check customers" \
&& ONBOARD: "Onboard customers" \
&& ENRICH: "Link to orders" \
&& CONSUME: "Create dashboard"
```

Each step waits for the previous to complete.

---

### Parallel Pattern (Independent Operations)

```bash
# Onboard multiple datasets simultaneously
ONBOARD: "Onboard customers" &
ONBOARD: "Onboard products" &
ONBOARD: "Onboard orders" &
wait

# Then link them
ENRICH: "Link orders → customers" &
ENRICH: "Link orders → products" &
wait
```

Use when operations don't depend on each other.

---

### Conditional Pattern (Run If Needed)

```bash
# Only enrich if both datasets exist
ROUTE: "Check customers and orders" \
&& ENRICH: "Link orders → customers" \
|| echo "Datasets not found, skipping ENRICH"
```

---

## 🎨 Workflow Visualization Styles

### Style 1: Linear Flow

```
ROUTE → ONBOARD → ENRICH → CONSUME → GOVERN
```

Simple, single dataset, no branching.

---

### Style 2: Branching Flow

```
        GENERATE
           ↓
        ONBOARD
           ↓
      ┌────┴────┐
   ENRICH    CONSUME
      └────┬────┘
           ↓
        GOVERN
```

Multiple operations after onboarding.

---

### Style 3: Parallel Flow

```
    ONBOARD(A)      ONBOARD(B)      ONBOARD(C)
         ↓               ↓               ↓
         └───────────────┴───────────────┘
                         ↓
                 ENRICH(link all)
                         ↓
                     CONSUME
```

Multiple datasets integrated.

---

## 🛠️ Troubleshooting Guide

### Issue: "Workload already exists"

**Solution**: Use ROUTE to check, then decide:
- Update existing: Re-run ONBOARD with updates
- Use existing: Skip to ENRICH or CONSUME

---

### Issue: "Sub-agent tests failing"

**Solution**: Check test results, fix issue, re-run ONBOARD
- The test gate will retry automatically (max 2 times)
- If still failing, human intervention needed

---

### Issue: "MCP server not available"

**Solution**: Check `.mcp.json` configuration
```bash
# Test MCP server
uvx awslabs.aws-dataprocessing-mcp-server@latest --help

# Check logs
cat logs/mcp/*/latest.log | grep ERROR
```

---

### Issue: "Quality score below threshold"

**Solution**: Adjust quality rules or fix data
```bash
# Option 1: Lower threshold temporarily
ONBOARD: "Update quality threshold to 0.70 for Silver"

# Option 2: Fix source data issues
ONBOARD: "Add data cleaning rules: [describe fixes]"
```

---

## 📊 Monitoring Your Workflows

### Real-Time Monitoring

```bash
# Watch console output
tail -f logs/mcp/[workload]/latest.log

# Watch MCP operations
watch -n 5 'ls -lh logs/mcp/[workload]/'
```

---

### Post-Execution Analysis

```bash
# Count successful operations
jq '[.steps[] | select(.status == "✓ SUCCESS")] | length' \
   logs/mcp/[workload]/[timestamp].json

# Find failures
jq '.steps[] | select(.status == "✗ FAILED")' \
   logs/mcp/[workload]/[timestamp].json

# Total duration
jq '[.steps[].duration_seconds] | add' \
   logs/mcp/[workload]/[timestamp].json
```

---

## 🎯 Success Criteria

### ROUTE Success
- ✅ Returns list of existing workloads
- ✅ Correctly identifies duplicates
- ✅ Runs in < 5 seconds

### GENERATE Success
- ✅ Creates realistic synthetic data
- ✅ Includes specified quality issues
- ✅ Uploads to S3 successfully

### ONBOARD Success
- ✅ All 4 sub-agents complete
- ✅ All tests pass
- ✅ MCP operations succeed
- ✅ Pipeline deployed to AWS
- ✅ Quality scores meet thresholds

### ENRICH Success
- ✅ Relationship metadata stored
- ✅ Join semantics defined
- ✅ Test query validates relationship

### CONSUME Success
- ✅ Dashboard created
- ✅ Queries return data
- ✅ Visualizations render correctly

### GOVERN Success
- ✅ Lineage diagram generated
- ✅ Audit logs retrieved
- ✅ Compliance report complete

---

## 🚨 Emergency Commands

### Stop All Running Workflows

```bash
# Kill all Python processes running orchestrator
pkill -f orchestrator.py

# Check MCP server status
ps aux | grep mcp-server
```

---

### Rollback Last ONBOARD

```bash
# Delete workload directory
rm -rf workloads/[workload_name]/

# Delete MCP resources (via AWS Console or CLI)
aws glue delete-crawler --name [crawler_name]
aws glue delete-job --job-name [job_name]
aws states delete-state-machine --state-machine-arn [arn]
```

---

### Force Cleanup

```bash
# Remove all logs
rm -rf logs/mcp/*/

# Reset MCP configuration
cp .mcp.json.backup .mcp.json

# Restart MCP servers
# (They auto-restart on next prompt execution)
```

---

## 📚 Related Documentation

- **Full Workflow Guide**: `PROMPT_WORKFLOW_GUIDE.md`
- **Prompt Examples**: `PROMPTS_EXAMPLES.md`
- **MCP Integration**: `MCP_INTEGRATION_SUMMARY.md`
- **Architecture**: `PROMPT_ARCHITECTURE.md`
- **Agent Skills**: `SKILLS.md`
- **Tool Mapping**: `TOOLS.md`
- **MCP Guardrails**: `MCP_GUARDRAILS.md`

---

## 💡 Pro Tips

1. **Always ROUTE first** - Saves time on duplicates
2. **Use GENERATE for testing** - Don't test on prod data
3. **Test gates are your friend** - They catch errors early
4. **Check MCP logs** - Understand what was actually executed
5. **Document as you go** - Use GOVERN throughout, not just at end
6. **Parallel when possible** - Speed up multi-dataset onboarding
7. **Name conventions matter** - Use consistent naming across prompts
8. **Review before deploy** - Always check the Phase 5 summary

---

## ✅ Checklist for First-Time Users

- [ ] Read `PROMPT_WORKFLOW_GUIDE.md`
- [ ] Review `.mcp.json` configuration
- [ ] Test with GENERATE → ONBOARD workflow
- [ ] Verify MCP logs are created
- [ ] Run verification scripts
- [ ] Create first dashboard with CONSUME
- [ ] Document with GOVERN
- [ ] Review AWS resources created

---

**Ready to start?** Pick a scenario above and copy-paste the commands!
