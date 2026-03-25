# MCP Orchestrator DAG - Deployment Guide

## Overview

`mcp_orchestrator_dag.py` is a **dynamic, MCP-powered orchestrator** that:

1. **Auto-discovers** all workloads from `workloads/` directory
2. **Orchestrates** Bronze → Silver → Gold pipeline for each workload
3. **Respects dependencies** between workloads (e.g., order_transactions waits for customer_master)
4. **Uses MCP servers** for all AWS operations with detailed logging
5. **Generates agent-aware logs** in `agent_run_logs/{workload}/{timestamp}_agent_logs/`
6. **Uploads to MWAA** - syncs all DAGs to S3 as the final step

---

## Quick Start

### 1. Set Airflow Variables

```bash
# Required
airflow variables set orchestrator_schedule "0 6 * * *"  # Daily at 6am UTC
airflow variables set mwaa_bucket "my-mwaa-environment-bucket"
airflow variables set mwaa_dags_prefix "dags/"

# Optional (with defaults)
airflow variables set base_path "/opt/airflow/dags"
airflow variables set quality_threshold_silver "0.80"
airflow variables set quality_threshold_gold "0.95"
airflow variables set workload_dependencies '{}'
airflow variables set glue_crawler_role "GlueCrawlerRole"
airflow variables set glue_dq_role "GlueDataQualityRole"
airflow variables set s3_bronze_bucket "data-lake-bronze"
airflow variables set s3_tables_bucket "data-lake-s3-tables"
airflow variables set sns_alert_topic_arn "arn:aws:sns:us-east-1:ACCOUNT:alerts"
```

### 2. Configure Workload Dependencies

Set `workload_dependencies` to define which workloads must wait for others:

```bash
airflow variables set workload_dependencies '{
  "order_transactions": ["customer_master"],
  "shipment_tracking": ["order_transactions"],
  "revenue_reporting": ["order_transactions", "customer_master"]
}'
```

**Result**: The DAG will ensure:
- `order_transactions` runs AFTER `customer_master` completes
- `shipment_tracking` runs AFTER `order_transactions` completes
- `revenue_reporting` runs AFTER both `order_transactions` AND `customer_master` complete

### 3. Test Locally

```bash
# Dry run to check DAG structure
airflow dags test mcp_orchestrator_dynamic 2026-03-16

# Check discovered workloads
airflow dags list | grep mcp_orchestrator

# Check task structure
airflow tasks list mcp_orchestrator_dynamic --tree
```

### 4. Deploy to MWAA

```bash
# Manual first-time upload (or let the DAG do it automatically after first run)
aws s3 cp dags/mcp_orchestrator_dag.py s3://my-mwaa-environment-bucket/dags/

# Verify in MWAA UI
# https://console.aws.amazon.com/mwaa/home -> Your Environment -> DAGs
```

---

## How It Works

### 1. Workload Discovery

At DAG parse time (every 30 seconds in MWAA), the orchestrator:

1. Scans `workloads/` directory
2. For each subdirectory, looks for `config/source.yaml`
3. If found, reads configuration from:
   - `config/source.yaml` - Source details
   - `config/schedule.yaml` - Schedule and dependencies
   - `config/transformations.yaml` - Transformation rules
   - `config/quality_rules.yaml` - Quality thresholds
4. Creates a TaskGroup for that workload with 4 stages:
   - Extract (Bronze)
   - Transform to Silver + Quality Gate
   - Curate to Gold + Quality Gate
   - Update Catalog

**Example**: If you have `workloads/sales_transactions/` and `workloads/customer_master/`, the DAG creates:
- `workload_sales_transactions` TaskGroup
- `workload_customer_master` TaskGroup

### 2. Pipeline Stages (Per Workload)

```
Extract (Bronze)
    ├── Create Glue Crawler
    └── Run Crawler (schema discovery)
          ↓
Transform to Silver
    ├── Create Silver Iceberg table
    ├── Run Glue ETL (Bronze → Silver)
    └── Quality Gate (>= 0.80)
          ↓
Curate to Gold
    ├── Create Gold Iceberg table
    ├── Run Glue ETL (Silver → Gold)
    └── Quality Gate (>= 0.95)
          ↓
Update Catalog
    ├── Update SageMaker Catalog metadata
    └── Store metrics in SynoDB
```

### 3. MCP Server Integration

All AWS operations route through MCP servers:

| MCP Server | Operations |
|------------|-----------|
| `aws-dataprocessing` | Glue Crawler, Glue Jobs, Athena, Glue Data Quality |
| `s3-tables` | Iceberg table creation/updates on S3 Tables |
| `s3` | S3 operations (reads, writes, copies) |
| `sagemaker-catalog` | Business metadata storage (custom metadata columns) |
| `dynamodb` | SynoDB metrics storage |
| `local-filesystem` | Workload discovery, config file reading |

**Result**: Every operation is:
- Logged with detailed timing
- Tracked by agent (Metadata, Transformation, Quality)
- Saved to `agent_run_logs/` for audit

### 4. Agent-Aware Logging

Each workload execution creates detailed logs in:

```
agent_run_logs/{workload_name}/{timestamp}_agent_logs/
├── {timestamp}_console.log          # Master log (all agents combined)
├── {timestamp}_structured.json      # Master JSON (machine-readable)
└── agent_logs/
    ├── Metadata_Agent.log           # Metadata Agent operations only
    ├── Metadata_Agent.json
    ├── Transformation_Agent.log     # Transformation Agent operations only
    ├── Transformation_Agent.json
    ├── Quality_Agent.log            # Quality Agent operations only
    └── Quality_Agent.json
```

**Use Cases**:
- Audit: Who did what, when, and how long did it take?
- Debugging: Which agent failed and why?
- Performance: Which MCP servers are slowest?
- Cost tracking: How much time per workload/agent?

### 5. MWAA Upload (Final Step)

After all workloads complete successfully, the orchestrator uploads:

1. **Orchestrator DAG**: `dags/mcp_orchestrator_dag.py`
2. **Workload DAGs**: All `workloads/*/dags/*.py`
3. **Shared utilities**: All `shared/**/*.py`

To S3: `s3://${MWAA_BUCKET}/${MWAA_DAGS_PREFIX}`

**Result**: Any changes to DAGs are automatically synced to MWAA on the next successful run.

---

## Configuration Reference

### Airflow Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `orchestrator_schedule` | No | `0 6 * * *` | Cron schedule for orchestrator |
| `mwaa_bucket` | **Yes** | N/A | S3 bucket for MWAA environment |
| `mwaa_dags_prefix` | No | `dags/` | S3 prefix for DAGs |
| `workload_dependencies` | No | `{}` | JSON mapping of dependencies |
| `base_path` | No | `/opt/airflow/dags` | Base path for workloads |
| `quality_threshold_silver` | No | `0.80` | Silver zone quality threshold |
| `quality_threshold_gold` | No | `0.95` | Gold zone quality threshold |
| `glue_crawler_role` | No | `GlueCrawlerRole` | IAM role for Glue Crawler |
| `glue_dq_role` | No | `GlueDataQualityRole` | IAM role for Glue Data Quality |
| `s3_bronze_bucket` | No | `data-lake-bronze` | S3 bucket for Bronze zone |
| `s3_tables_bucket` | No | `data-lake-s3-tables` | S3 bucket for Iceberg tables |
| `sns_alert_topic_arn` | No | `arn:aws:sns:...` | SNS topic for failure alerts |

### Workload Dependencies Format

```json
{
  "downstream_workload": ["upstream_workload1", "upstream_workload2"],
  "another_downstream": ["dependency1"]
}
```

**Example**:

```json
{
  "order_transactions": ["customer_master"],
  "shipment_tracking": ["order_transactions"],
  "revenue_reporting": ["order_transactions", "customer_master"]
}
```

**Visualization**:

```
customer_master
    ├── order_transactions
    │       ├── shipment_tracking
    │       └── revenue_reporting
    └── revenue_reporting
```

---

## Frequency-Based Execution

The orchestrator can run at different frequencies. Each workload's `config/schedule.yaml` defines its execution frequency:

### Example 1: Different Schedules Per Workload

**Orchestrator**: Runs hourly (`0 * * * *`)

**Workloads**:
- `sales_transactions/config/schedule.yaml`:
  ```yaml
  frequency: hourly
  cron: "0 * * * *"
  ```
- `customer_master/config/schedule.yaml`:
  ```yaml
  frequency: daily
  cron: "0 6 * * *"
  ```

**Result**:
- Orchestrator runs every hour
- `sales_transactions` processes every hour
- `customer_master` only processes at 6am (skipped other hours)

### Example 2: Complex Dependencies with Different Schedules

**Scenario**: Real-time orders, daily customers, weekly reports

```json
{
  "order_transactions": ["customer_master"],
  "weekly_revenue_report": ["order_transactions", "customer_master"]
}
```

**Schedules**:
- Orchestrator: Hourly
- `customer_master`: Daily at 6am
- `order_transactions`: Every 15 minutes
- `weekly_revenue_report`: Sunday at 8am

**Orchestrator behavior**:
- Every 15 min: Process `order_transactions` (if customer_master already ran today)
- Every day at 6am: Process `customer_master`, then `order_transactions`
- Every Sunday at 8am: Process all three (full pipeline)

---

## Monitoring & Troubleshooting

### View Agent Logs

```bash
# View master console log
cat agent_run_logs/sales_transactions/20260316_110100_console.log

# View specific agent
cat agent_run_logs/sales_transactions/20260316_110100_agent_logs/Transformation_Agent.log

# Parse JSON for metrics
jq '.statistics' agent_run_logs/sales_transactions/20260316_110100_structured.json

# Find slowest operations
jq '.steps | sort_by(.timing.duration_seconds) | reverse | .[0:5]' \
   agent_run_logs/sales_transactions/20260316_110100_structured.json
```

### View in Airflow UI

1. Open MWAA console: https://console.aws.amazon.com/mwaa/home
2. Click on your environment → "Open Airflow UI"
3. Navigate to DAGs → `mcp_orchestrator_dynamic`
4. Click on latest run → Graph View
5. Click on any task → Logs

### Common Issues

#### Issue: "Workload not discovered"

**Cause**: Missing `config/source.yaml`

**Fix**:
```bash
# Ensure source.yaml exists
ls workloads/my_workload/config/source.yaml

# Check DAG logs for discovery errors
airflow dags test mcp_orchestrator_dynamic 2026-03-16 | grep -i "discover"
```

#### Issue: "Quality gate failed"

**Cause**: Data quality below threshold

**Fix**:
```bash
# Check quality score in logs
cat agent_run_logs/{workload}/{timestamp}_agent_logs/Quality_Agent.log

# Lower threshold temporarily (not recommended for production)
airflow variables set quality_threshold_silver "0.70"

# Or fix data issues in Bronze/Silver
```

#### Issue: "Dependency not satisfied"

**Cause**: Upstream workload failed or skipped

**Fix**:
```bash
# Check upstream workload status
airflow tasks state mcp_orchestrator_dynamic workload_customer_master.catalog.update_catalog 2026-03-16

# Check dependency configuration
airflow variables get workload_dependencies
```

#### Issue: "MWAA upload failed"

**Cause**: S3 bucket not accessible or incorrect permissions

**Fix**:
```bash
# Check bucket exists
aws s3 ls s3://my-mwaa-environment-bucket/

# Check IAM role permissions
aws iam get-role --role-name MWAA-ExecutionRole

# Verify S3 bucket policy allows MWAA role
```

---

## Advanced Configuration

### Custom MCP Server Endpoints

If using custom MCP servers, set their paths:

```bash
airflow variables set mcp_server_sagemaker_catalog "/opt/airflow/dags/shared/mcp/servers/sagemaker-catalog-mcp-server/server.py"
```

### Per-Workload Quality Thresholds

Override global thresholds in `config/quality_rules.yaml`:

```yaml
thresholds:
  silver: 0.85  # Override global 0.80
  gold: 0.98    # Override global 0.95
```

### Custom Agent Logging Paths

```bash
airflow variables set agent_logs_base_dir "/mnt/logs/agent_run_logs"
```

---

## Performance Tuning

### Parallel Workload Execution

By default, independent workloads run in parallel. To limit concurrency:

```python
# In DAG definition
max_active_runs=1        # Only 1 DAG run at a time
max_active_tasks=10      # Max 10 tasks across all runs
```

### Reduce MCP Logging Overhead

For high-frequency workloads, reduce logging verbosity:

```python
# In orchestrator_enhanced.py
# Set shorter log retention
LOG_RETENTION_DAYS = 7  # Instead of 30
```

### Optimize Glue Job Execution

In `workloads/{name}/config/transformations.yaml`:

```yaml
glue_job_config:
  worker_type: G.2X       # Larger workers
  number_of_workers: 10   # More parallelism
  max_retries: 1          # Fewer retries for faster failure
```

---

## Production Checklist

- [ ] All Airflow Variables set
- [ ] `workload_dependencies` configured correctly
- [ ] MWAA S3 bucket accessible from DAG
- [ ] IAM roles for Glue Crawler and Data Quality exist
- [ ] SNS topic configured for alerts
- [ ] All workloads have `config/source.yaml`
- [ ] Quality thresholds match business requirements
- [ ] Agent logs directory writable
- [ ] Tested with `airflow dags test` locally
- [ ] Uploaded to MWAA S3 bucket
- [ ] DAG visible in MWAA UI
- [ ] First manual run successful
- [ ] Auto-sync to MWAA working (check S3 after DAG run)
- [ ] CloudWatch logs enabled for MWAA
- [ ] Monitoring dashboard set up (optional)

---

## Migration from Existing DAGs

### From Individual Workload DAGs

**Before**: Each workload has its own DAG in `workloads/{name}/dags/{name}_dag.py`

**After**: One orchestrator DAG auto-discovers and orchestrates all workloads

**Steps**:

1. Keep existing workload DAGs as reference
2. Deploy orchestrator DAG to MWAA
3. Disable old workload DAGs in Airflow UI
4. Verify orchestrator runs successfully
5. Archive old DAGs: `mv workloads/*/dags/*.py workloads/*/dags/archive/`

### From `end_to_end_pipeline_dag.py`

**Before**: Hardcoded pipeline for 2 workloads (customer_master, order_transactions)

**After**: Dynamic discovery of all workloads with configurable dependencies

**Steps**:

1. Set `workload_dependencies` matching old DAG logic:
   ```bash
   airflow variables set workload_dependencies '{"order_transactions": ["customer_master"]}'
   ```
2. Deploy orchestrator DAG
3. Run side-by-side for 1 week to validate
4. Disable old `end_to_end_pipeline_daily` DAG
5. Archive: `mv dags/end_to_end_pipeline_dag.py dags/archive/`

---

## Future Enhancements

- [ ] **Dynamic schedule adjustment** - Workloads auto-adjust frequency based on data volume
- [ ] **Cost tracking** - Integrate AWS Cost Explorer API to track per-workload costs
- [ ] **Data quality ML** - Predict quality scores before running expensive transformations
- [ ] **Auto-remediation** - Retry with adjusted parameters on quality failure
- [ ] **Multi-region support** - Orchestrate workloads across AWS regions
- [ ] **Real-time monitoring dashboard** - Live view of agent operations via WebSocket
- [ ] **A/B testing** - Run two transformation versions in parallel, compare quality
- [ ] **Intelligent scheduling** - ML-based optimal scheduling based on historical patterns

---

## Support

For issues or questions:

1. Check this guide's Troubleshooting section
2. Review agent logs in `agent_run_logs/`
3. Check Airflow task logs in MWAA UI
4. Review CLAUDE.md for architecture details
5. Review MCP_SERVERS.md for MCP server configuration
6. Open issue in project repository (if applicable)

---

## Related Documentation

- `CLAUDE.md` - Project architecture and conventions
- `SKILLS.md` - Agent skill definitions
- `TOOLS.md` - AWS tooling reference
- `MCP_SERVERS.md` - Complete MCP server mapping
- `agent_run_logs/README.md` - Logging guide
- `PROMPT_WORKFLOW_GUIDE.md` - User-facing workflow documentation
- `shared/mcp/ENHANCED_LOGGING_GUIDE.md` - Orchestrator logging details
