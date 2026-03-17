# MWAA DAG Status — US Mutual Funds & ETF Pipeline

**Check Date:** 2026-03-16 17:00 EST
**DAG Status:** ❌ **NOT DEPLOYED**
**MWAA Environment:** ✅ AVAILABLE

---

## Summary

The Airflow DAG file **exists locally** but has **NOT been deployed** to the MWAA environment. This is why you don't see it in the Airflow UI.

| Component | Status | Details |
|-----------|--------|---------|
| **DAG File** | ✅ EXISTS | Local file in workloads/us_mutual_funds_etf/dags/ |
| **MWAA Environment** | ✅ AVAILABLE | DataZone-managed, Airflow 2.10.1 |
| **Deployed to MWAA** | ❌ NO | DAG not uploaded to S3 bucket |
| **demo-role Access** | ✅ YES | Has AdministratorAccess policy |

---

## DAG Details

### Local DAG File

**Location:**
```
/path/to/claude-data-operations/workloads/us_mutual_funds_etf/dags/us_mutual_funds_etf_dag.py
```

**Metadata:**
- **DAG ID:** `us_mutual_funds_etf_pipeline`
- **Schedule:** `0 2 1 * *` (Monthly on 1st at 02:00 UTC)
- **Start Date:** 2025-01-01
- **Owner:** data_engineering
- **Size:** 526 lines

### DAG Description

End-to-end Bronze→Silver→Gold pipeline for US mutual fund and ETF performance data.

**Orchestrates:**
- 8 Glue ETL jobs
- 2 quality check jobs (Silver @ 80%, Gold @ 95%)
- Medallion architecture: Bronze → Silver → Gold

**Jobs:**
1. Bronze: `bronze_data_generation`
2. Silver: `silver_funds_clean`, `silver_market_data_clean`, `silver_nav_clean`
3. Silver Quality: `quality_checks_silver`
4. Gold: `gold_dim_fund`, `gold_dim_category`, `gold_dim_date`, `gold_fact_fund_performance`
5. Gold Quality: `quality_checks_gold`

**Quality Gates:**
- Silver: 0.80 threshold (blocks progression if failed)
- Gold: 0.95 threshold (blocks progression if failed)

**Features:**
- TaskGroups for Bronze/Silver/Gold stages
- Slack notifications on failure (via `slack_data_alerts` connection)
- SLA monitoring (Bronze: 30 min, Silver: 60 min, Gold: 90 min)
- Exponential backoff retries (3 retries, 5 min delay)

---

## MWAA Environment Details

### Environment

**Name:** `DataZoneMWAAEnv-dzd_3r8vjvw09xh5yf-4rosjy6nd9pgdj-dev`

**Status:** AVAILABLE

**Airflow Version:** 2.10.1

**Region:** us-east-1

### Access URLs

**MWAA Console:**
```
https://console.aws.amazon.com/mwaa/home?region=us-east-1
```

**Airflow Web UI:**
```
https://c6c80ebf-b2ce-44d8-829e-20c89592fa76.c19.us-east-1.airflow.amazonaws.com
```

### S3 Paths

**DAG Bucket:**
```
s3://amazon-sagemaker-123456789012-us-east-1-e8cea5855b8a
```

**DAG S3 Path (Target for Upload):**
```
s3://amazon-sagemaker-123456789012-us-east-1-e8cea5855b8a/dzd_3r8vjvw09xh5yf/4rosjy6nd9pgdj/dev/workflows/project-files/workflows/dags/
```

### Execution Role

**Role ARN:**
```
arn:aws:iam::123456789012:role/datazone_usr_role_4rosjy6nd9pgdj_cxqit30yarj5bb
```

---

## Why You Don't See the DAG

### Reason

The DAG file was **created during pipeline development** but was **never uploaded** to the MWAA S3 bucket. It exists only in the local workload folder.

MWAA loads DAGs from S3, not from local files. The DAG will only appear in the Airflow UI after it's uploaded to the S3 path above.

### Current State

```
Local Workload Folder
└── dags/
    └── us_mutual_funds_etf_dag.py  ✅ EXISTS

MWAA S3 Bucket
└── dzd_3r8vjvw09xh5yf/4rosjy6nd9pgdj/dev/workflows/project-files/workflows/dags/
    └── (empty - no DAGs uploaded)  ❌ MISSING
```

---

## Deployment Options

### Option 1: Deploy via AWS CLI (Recommended)

**Command:**
```bash
# Upload DAG to MWAA S3 bucket
aws s3 cp workloads/us_mutual_funds_etf/dags/us_mutual_funds_etf_dag.py \
  s3://amazon-sagemaker-123456789012-us-east-1-e8cea5855b8a/dzd_3r8vjvw09xh5yf/4rosjy6nd9pgdj/dev/workflows/project-files/workflows/dags/ \
  --region us-east-1

# Verify upload
aws s3 ls s3://amazon-sagemaker-123456789012-us-east-1-e8cea5855b8a/dzd_3r8vjvw09xh5yf/4rosjy6nd9pgdj/dev/workflows/project-files/workflows/dags/ \
  --region us-east-1
```

**Wait Time:** DAGs are loaded every 30-60 seconds by default. Wait 1-2 minutes after upload.

**Verification:**
1. Go to Airflow UI: https://c6c80ebf-b2ce-44d8-829e-20c89592fa76.c19.us-east-1.airflow.amazonaws.com
2. Navigate to DAGs page
3. Look for `us_mutual_funds_etf_pipeline`
4. If it appears, deployment was successful

### Option 2: Deploy via MWAA Console

**Steps:**
1. Go to MWAA Console: https://console.aws.amazon.com/mwaa/home?region=us-east-1
2. Click environment: `DataZoneMWAAEnv-dzd_3r8vjvw09xh5yf-4rosjy6nd9pgdj-dev`
3. Note the S3 bucket path under "DAG code in S3"
4. Use S3 console to upload `us_mutual_funds_etf_dag.py` to that path
5. Wait 1-2 minutes for MWAA to detect the new DAG

### Option 3: Deploy via S3 Console

**Steps:**
1. Go to S3 Console: https://s3.console.aws.amazon.com/s3/buckets/amazon-sagemaker-123456789012-us-east-1-e8cea5855b8a
2. Navigate to: `dzd_3r8vjvw09xh5yf/4rosjy6nd9pgdj/dev/workflows/project-files/workflows/dags/`
3. Click **"Upload"**
4. Select `workloads/us_mutual_funds_etf/dags/us_mutual_funds_etf_dag.py`
5. Click **"Upload"**
6. Wait 1-2 minutes for MWAA to load the DAG

---

## After Deployment

### Expected Behavior

Once the DAG is uploaded:
1. **DAG appears in Airflow UI** within 1-2 minutes
2. **Initial state:** Paused (toggle to unpause)
3. **First run:** Will run on next scheduled date (1st of next month @ 02:00 UTC)
4. **Manual trigger:** Can trigger manually from Airflow UI

### Airflow Variables Required

The DAG expects these Airflow Variables to be configured:

| Variable | Default | Purpose |
|----------|---------|---------|
| `finsights_s3_bucket` | your-datalake-bucket | Data lake S3 bucket |
| `finsights_glue_role` | GlueServiceRole | Glue job execution role |
| `aws_region` | us-east-1 | AWS region |
| `glue_version` | 4.0 | Glue version |
| `glue_worker_type` | G.1X | Glue worker type |
| `slack_connection_id` | slack_data_alerts | Slack webhook connection |

**To set variables:**
1. Open Airflow UI
2. Go to Admin → Variables
3. Add each variable with the default value above

### Airflow Connections Required

The DAG uses Slack notifications. If you want notifications, configure:

**Connection ID:** `slack_data_alerts`
**Connection Type:** Slack Webhook
**Webhook URL:** Your Slack webhook URL

If Slack is not configured, the DAG will still run but skip notifications.

---

## demo-role Access

### IAM Policies

demo-role has the following policies attached:
- ✅ **AdministratorAccess** (AWS managed)
- ✅ **AmazonDataZoneFullAccess** (AWS managed)
- ✅ **FinsightsWorkloadAccess** (Inline policy)

### Permissions

With AdministratorAccess, demo-role can:
- ✅ Access MWAA console
- ✅ Open Airflow web UI
- ✅ Upload DAGs to S3
- ✅ View/trigger/pause DAG runs
- ✅ View logs and task details

### How to Access as demo-role

**Via Isengard (Federated Login):**
1. Log in to Isengard portal
2. Select AWS account: 123456789012
3. Assume role: demo-role
4. Navigate to MWAA console
5. Click "Open Airflow UI"

**Via CLI (STS Assume Role):**
```bash
# Assume demo-role
aws sts assume-role \
  --role-arn arn:aws:iam::123456789012:role/demo-role \
  --role-session-name mwaa-session

# Export credentials from output
export AWS_ACCESS_KEY_ID=<AccessKeyId>
export AWS_SECRET_ACCESS_KEY=<SecretAccessKey>
export AWS_SESSION_TOKEN=<SessionToken>

# Now you can run MWAA commands as demo-role
aws mwaa list-environments --region us-east-1
```

---

## DAG Execution Flow

### Task Dependency Graph

```
start
  ↓
bronze_stage (TaskGroup)
  ├── bronze_data_generation
  ↓
silver_stage (TaskGroup)
  ├── silver_funds_clean
  ├── silver_market_data_clean
  ├── silver_nav_clean
  └── quality_checks_silver
  ↓
gold_stage (TaskGroup)
  ├── gold_dim_fund
  ├── gold_dim_category
  ├── gold_dim_date
  ├── gold_fact_fund_performance
  └── quality_checks_gold
  ↓
end
```

### Execution Times (Expected)

| Stage | Tasks | Expected Duration |
|-------|-------|-------------------|
| Bronze | 1 job | 3-5 minutes |
| Silver | 3 jobs + 1 quality | 8-12 minutes |
| Gold | 4 jobs + 1 quality | 10-15 minutes |
| **Total** | **10 jobs** | **~25-30 minutes** |

### SLA Monitoring

| Stage | SLA Threshold | Action on Breach |
|-------|---------------|------------------|
| Bronze | 30 minutes | Slack alert |
| Silver | 60 minutes | Slack alert |
| Gold | 90 minutes | Slack alert |

---

## Troubleshooting

### Issue: DAG doesn't appear after upload

**Possible Causes:**
1. S3 path incorrect
2. DAG has syntax errors
3. MWAA hasn't refreshed yet

**Solution:**
1. Verify S3 path matches MWAA environment settings
2. Check DAG syntax: `python3 us_mutual_funds_etf_dag.py` (should not error)
3. Wait 2-3 minutes for MWAA to scan S3
4. Check Airflow logs in CloudWatch

### Issue: DAG appears but shows import errors

**Possible Causes:**
1. Missing Airflow providers
2. Airflow version incompatibility

**Solution:**
1. Check MWAA environment has required providers:
   - `apache-airflow-providers-amazon`
   - `apache-airflow-providers-slack`
2. MWAA Airflow 2.10.1 should have these by default

### Issue: Jobs fail with "Role not found"

**Possible Causes:**
1. `GlueServiceRole` doesn't exist
2. Airflow execution role can't assume GlueServiceRole

**Solution:**
1. Verify GlueServiceRole exists:
   ```bash
   aws iam get-role --role-name GlueServiceRole
   ```
2. Update Airflow Variable `finsights_glue_role` if role has different name

### Issue: Quality checks fail

**Possible Causes:**
1. Data quality below threshold
2. Lake Formation permissions missing

**Solution:**
1. Check CloudWatch logs for quality check jobs
2. Verify Lake Formation permissions (see LAKE_FORMATION_S3_REGISTRATION_FIX.md)
3. Adjust quality thresholds if needed (0.80 for Silver, 0.95 for Gold)

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| **PROJECT_COMPLETE.md** | Full project summary |
| **PIPELINE_COMPLETE.md** | ETL pipeline details |
| **DEMO_ROLE_ACCESS.md** | User access configuration |
| **LAKE_FORMATION_S3_REGISTRATION_FIX.md** | Lake Formation permissions fix |
| **MWAA_DAG_STATUS.md** | This document |

---

## Next Steps

1. **Deploy DAG** (choose one option above)
2. **Configure Airflow Variables** (in Airflow UI)
3. **Test with Manual Trigger** (trigger DAG manually)
4. **Monitor First Run** (check logs for any errors)
5. **Set Schedule** (unpause DAG for monthly runs)

---

**Document Created:** 2026-03-16 17:00 EST
**Status:** ❌ DAG NOT DEPLOYED (ready to deploy)
**Action Required:** Upload DAG file to MWAA S3 bucket
