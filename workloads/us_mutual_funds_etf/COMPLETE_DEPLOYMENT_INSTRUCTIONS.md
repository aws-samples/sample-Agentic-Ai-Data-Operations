# Complete Deployment Instructions — US Mutual Funds & ETF Workload

**Last Updated:** 2026-03-16
**Status:** ✅ Infrastructure deployed, ⏸️ Pipeline running
**AWS Account:** 123456789012
**Region:** us-east-1

---

## 🎯 Overview

This guide provides step-by-step instructions to fully deploy and run the US Mutual Funds & ETF data pipeline.

**Pipeline Flow:**
```
Bronze (Generate) → Silver (Clean) → Gold (Model) → QuickSight (Visualize)
     130 funds         120 funds         120 funds        9 visuals
```

**Duration:** ~1 hour first deployment, ~30 min subsequent runs

---

## ✅ What's Already Deployed

| Component | Status | Details |
|-----------|--------|---------|
| **S3 Bucket** | ✅ Created | `s3://your-datalake-bucket/` |
| **Glue Databases** | ✅ Created | finsights_silver, finsights_gold |
| **Scripts** | ✅ Uploaded | 11 files (84.9 KiB) |
| **Glue Jobs** | ✅ Registered | 10 jobs (Bronze, Silver, Gold, Quality) |
| **IAM Policy** | ✅ Attached | demo-role has backend access |
| **Bronze Job** | ⏸️ Running | Job Run ID: jr_b2d269... |

---

## 📋 Prerequisites Checklist

Before proceeding, ensure you have:

- [ ] AWS Account with admin access
- [ ] AWS CLI configured (`aws configure`)
- [ ] Python 3.11+ installed
- [ ] boto3 installed (`pip install boto3`)
- [ ] IAM role `GlueServiceRole` exists (or create one)
- [ ] QuickSight subscription (for dashboard step)
- [ ] Budget approved (~$50-100 for first month)

---

## 🚀 Step-by-Step Deployment

### **PHASE 1: Verify Infrastructure (5 minutes)**

#### 1.1: Check S3 Bucket

```bash
aws s3 ls s3://your-datalake-bucket/

# Expected output:
#                            PRE scripts/
```

#### 1.2: Check Glue Databases

```bash
aws glue get-databases --query 'DatabaseList[?Name==`finsights_silver` || Name==`finsights_gold`].[Name,Description]' --output table

# Expected output:
# +-------------------+----------------------------------------------------+
# |  finsights_gold   |  Star schema for analytics (Iceberg tables)        |
# |  finsights_silver |  Cleaned and validated fund data (Iceberg tables)  |
# +-------------------+----------------------------------------------------+
```

#### 1.3: Check Glue Jobs

```bash
aws glue list-jobs --query 'JobNames' --output json | grep -E "bronze|silver|gold|quality"

# Expected: 10 job names listed
```

#### 1.4: Check IAM Role

```bash
aws iam get-role --role-name GlueServiceRole 2>&1

# If error "NoSuchEntity", create role:
aws iam create-role \
  --role-name GlueServiceRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "glue.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach AWS managed policy
aws iam attach-role-policy \
  --role-name GlueServiceRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole
```

---

### **PHASE 2: Run ETL Pipeline (30-45 minutes)**

#### 2.1: Start Bronze Data Generation

```bash
# Start Job 1
aws glue start-job-run --job-name bronze_data_generation

# Output:
# {
#     "JobRunId": "jr_abc123..."
# }

# Save the JobRunId for monitoring
export BRONZE_RUN_ID="jr_abc123..."
```

#### 2.2: Monitor Bronze Job

```bash
# Check status every 30 seconds
watch -n 30 "aws glue get-job-run --job-name bronze_data_generation --run-id $BRONZE_RUN_ID --query 'JobRun.[JobRunState,ExecutionTime]' --output table"

# Wait for status: SUCCEEDED
# Expected duration: 5-8 minutes
```

**Status Meanings:**
- `WAITING` → Provisioning Glue workers (1-2 min)
- `RUNNING` → Job is executing (3-5 min)
- `SUCCEEDED` → Job completed successfully
- `FAILED` → Job failed (check error logs)

**View Logs:**
```bash
aws glue get-job-run --job-name bronze_data_generation --run-id $BRONZE_RUN_ID --query 'JobRun.ErrorMessage'
```

#### 2.3: Verify Bronze Data

```bash
# Check S3 for Bronze Parquet files
aws s3 ls s3://your-datalake-bucket/bronze/ --recursive --human-readable

# Expected:
# 2026-03-16 12:xx:xx  xxxx raw_funds/part-00000.parquet
# 2026-03-16 12:xx:xx  xxxx raw_market_data/part-00000.parquet
# 2026-03-16 12:xx:xx  xxxx raw_nav_prices/part-00000.parquet
```

#### 2.4: Start Silver Jobs (Parallel)

```bash
# Start all 3 Silver cleaning jobs in parallel
aws glue start-job-run --job-name silver_funds_clean
aws glue start-job-run --job-name silver_market_data_clean
aws glue start-job-run --job-name silver_nav_clean

# Save Job Run IDs
export SILVER_FUNDS_RUN=$(aws glue start-job-run --job-name silver_funds_clean --query 'JobRunId' --output text)
export SILVER_MARKET_RUN=$(aws glue start-job-run --job-name silver_market_data_clean --query 'JobRunId' --output text)
export SILVER_NAV_RUN=$(aws glue start-job-run --job-name silver_nav_clean --query 'JobRunId' --output text)
```

#### 2.5: Monitor Silver Jobs

```bash
# Monitor all 3 jobs
while true; do
  echo "=== Silver Jobs Status ==="
  aws glue get-job-run --job-name silver_funds_clean --run-id $SILVER_FUNDS_RUN --query 'JobRun.JobRunState' --output text
  aws glue get-job-run --job-name silver_market_data_clean --run-id $SILVER_MARKET_RUN --query 'JobRun.JobRunState' --output text
  aws glue get-job-run --job-name silver_nav_clean --run-id $SILVER_NAV_RUN --query 'JobRun.JobRunState' --output text
  sleep 30
done

# Stop monitoring: Ctrl+C when all show SUCCEEDED
# Expected duration: 5-8 minutes each
```

#### 2.6: Run Silver Quality Gate

```bash
# After all Silver jobs succeed
aws glue start-job-run --job-name quality_checks_silver

export SILVER_QC_RUN=$(aws glue start-job-run --job-name quality_checks_silver --query 'JobRunId' --output text)

# Monitor
watch -n 30 "aws glue get-job-run --job-name quality_checks_silver --run-id $SILVER_QC_RUN --query 'JobRun.[JobRunState,ErrorMessage]' --output table"

# Expected: SUCCEEDED (score >= 0.80, no critical failures)
# Duration: 3-5 minutes
```

#### 2.7: Verify Silver Tables

```bash
# List Silver tables
aws glue get-tables --database-name finsights_silver --query 'TableList[*].[Name,StorageDescriptor.Location]' --output table

# Expected:
# +------------------------+------------------------------------------------+
# |  funds_clean           |  s3://your-datalake-bucket/silver/funds_clean/   |
# |  market_data_clean     |  s3://your-datalake-bucket/silver/...            |
# |  nav_clean             |  s3://your-datalake-bucket/silver/nav_clean/     |
# +------------------------+------------------------------------------------+

# Query a table via Athena
aws athena start-query-execution \
  --query-string "SELECT COUNT(*) FROM finsights_silver.funds_clean" \
  --result-configuration "OutputLocation=s3://your-datalake-bucket/athena-results/" \
  --query-execution-context "Database=finsights_silver"

# Expected: ~120 rows
```

#### 2.8: Start Gold Jobs (Parallel for Dims, Sequential for Fact)

```bash
# Start 3 dimension jobs in parallel
aws glue start-job-run --job-name gold_dim_fund
aws glue start-job-run --job-name gold_dim_category
aws glue start-job-run --job-name gold_dim_date

export GOLD_DIM_FUND_RUN=$(aws glue start-job-run --job-name gold_dim_fund --query 'JobRunId' --output text)
export GOLD_DIM_CAT_RUN=$(aws glue start-job-run --job-name gold_dim_category --query 'JobRunId' --output text)
export GOLD_DIM_DATE_RUN=$(aws glue start-job-run --job-name gold_dim_date --query 'JobRunId' --output text)

# Monitor dims
while true; do
  echo "=== Gold Dimension Jobs Status ==="
  aws glue get-job-run --job-name gold_dim_fund --run-id $GOLD_DIM_FUND_RUN --query 'JobRun.JobRunState' --output text
  aws glue get-job-run --job-name gold_dim_category --run-id $GOLD_DIM_CAT_RUN --query 'JobRun.JobRunState' --output text
  aws glue get-job-run --job-name gold_dim_date --run-id $GOLD_DIM_DATE_RUN --query 'JobRun.JobRunState' --output text
  sleep 30
done

# After all dims succeed, start fact table
aws glue start-job-run --job-name gold_fact_fund_performance

export GOLD_FACT_RUN=$(aws glue start-job-run --job-name gold_fact_fund_performance --query 'JobRunId' --output text)

# Monitor fact
watch -n 30 "aws glue get-job-run --job-name gold_fact_fund_performance --run-id $GOLD_FACT_RUN --query 'JobRun.[JobRunState,ExecutionTime]' --output table"

# Expected duration: 5-8 minutes for dims, 6-10 minutes for fact
```

#### 2.9: Run Gold Quality Gate

```bash
# After fact table succeeds
aws glue start-job-run --job-name quality_checks_gold

export GOLD_QC_RUN=$(aws glue start-job-run --job-name quality_checks_gold --query 'JobRunId' --output text)

# Monitor
watch -n 30 "aws glue get-job-run --job-name quality_checks_gold --run-id $GOLD_QC_RUN --query 'JobRun.[JobRunState,ErrorMessage]' --output table"

# Expected: SUCCEEDED (score >= 0.95, no critical failures)
# Duration: 3-5 minutes
```

#### 2.10: Verify Gold Tables

```bash
# List Gold tables
aws glue get-tables --database-name finsights_gold --query 'TableList[*].Name' --output table

# Expected:
# +------------------------------+
# |  dim_fund                    |
# |  dim_category                |
# |  dim_date                    |
# |  fact_fund_performance       |
# +------------------------------+

# Query fact table
aws athena start-query-execution \
  --query-string "SELECT COUNT(*) FROM finsights_gold.fact_fund_performance" \
  --result-configuration "OutputLocation=s3://your-datalake-bucket/athena-results/" \
  --query-execution-context "Database=finsights_gold"

# Expected: ~140 rows
```

---

### **PHASE 3: Grant Lake Formation Permissions (5 minutes)**

Now that tables exist, grant Lake Formation permissions:

```bash
cd /path/to/claude-data-operations/workloads/us_mutual_funds_etf

# Re-run access grant script (will grant LF permissions now)
./scripts/access/grant_access_hcherian.sh

# Expected output:
# ✅ IAM Policy: Already exists
# ✅ Lake Formation: 5/5 grants successful
# ✅ QuickSight: Skipped (not yet deployed)
```

**Verify:**
```bash
aws lakeformation list-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::123456789012:role/demo-role \
  --resource Database={Name=finsights_gold} \
  --query 'PrincipalResourcePermissions[*].[Principal.DataLakePrincipalIdentifier,Permissions]' \
  --output table

# Expected: demo-role has DESCRIBE on database
```

---

### **PHASE 4: Deploy QuickSight Dashboard (15-20 minutes)**

#### 4.1: Subscribe to QuickSight

Follow instructions in `QUICKSIGHT_SETUP_GUIDE.md`:

```bash
# Open QuickSight Console
open "https://console.aws.amazon.com/quicksight/home?region=us-east-1"

# Sign up for QuickSight Standard Edition ($9/month, 30-day trial)
# Grant access to:
#   - Amazon Athena
#   - S3 bucket: your-datalake-bucket
#   - AWS Glue Data Catalog
```

#### 4.2: Add User as QuickSight Author

```bash
# Get current IAM user
aws sts get-caller-identity --query 'Arn' --output text

# Register as QuickSight user
aws quicksight register-user \
  --aws-account-id 123456789012 \
  --namespace default \
  --identity-type IAM \
  --iam-arn arn:aws:iam::123456789012:user/demo-profile \
  --user-role AUTHOR \
  --email your-email@example.com \
  --region us-east-1

# Get QuickSight user ARN
export QS_USER_ARN=$(aws quicksight describe-user \
  --aws-account-id 123456789012 \
  --namespace default \
  --user-name demo-profile \
  --region us-east-1 \
  --query 'User.Arn' \
  --output text)

echo "QuickSight User ARN: $QS_USER_ARN"
```

#### 4.3: Update QuickSight Script

```bash
# Edit the script to use your actual values
# Update lines 17-19 in scripts/quicksight/quicksight_dashboard_setup.py

# Current placeholder values:
# ACCOUNT_ID = "123456789012"
# QS_AUTHOR_ARN = "arn:aws:quicksight:us-east-1:123456789012:user/default/admin"

# Replace with:
# ACCOUNT_ID = "123456789012"
# QS_AUTHOR_ARN = "arn:aws:quicksight:us-east-1:123456789012:user/default/demo-profile"

# Or use sed:
sed -i '' 's/ACCOUNT_ID = "123456789012"/ACCOUNT_ID = "123456789012"/' scripts/quicksight/quicksight_dashboard_setup.py
sed -i '' "s|QS_AUTHOR_ARN = \".*\"|QS_AUTHOR_ARN = \"$QS_USER_ARN\"|" scripts/quicksight/quicksight_dashboard_setup.py
```

#### 4.4: Run QuickSight Provisioning

```bash
python3 scripts/quicksight/quicksight_dashboard_setup.py

# Expected duration: 10-15 minutes
# Watch for:
#   [STEP 1] Creating Athena Data Source... ✅
#   [STEP 2] Creating Datasets... ✅
#   [STEP 3] Creating Analysis... ✅
#   [STEP 4] Publishing Dashboard... ✅
#   [STEP 5] Refresh Schedule... ✅
```

#### 4.5: Access Dashboard

```bash
# Open dashboard in browser
open "https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/finsights-finance-dashboard"

# Or copy URL from script output
```

---

### **PHASE 5: Verification & Testing (10 minutes)**

#### 5.1: Test Athena Query

```sql
-- Query Gold tables via Athena
SELECT
    d.fund_name,
    d.fund_type,
    AVG(f.return_1yr_pct) AS avg_1yr_return,
    SUM(f.total_assets_millions) / 1000 AS total_aum_billions
FROM finsights_gold.fact_fund_performance f
JOIN finsights_gold.dim_fund d ON f.fund_ticker = d.fund_ticker
GROUP BY d.fund_name, d.fund_type
ORDER BY avg_1yr_return DESC
LIMIT 10;
```

#### 5.2: Test QuickSight Dashboard

- ✅ All 9 visuals render without errors
- ✅ KPIs show realistic values (~120 funds, ~$XXB AUM)
- ✅ Filters work (date range, fund type)
- ✅ Export to CSV works
- ✅ Mobile view responsive

#### 5.3: Verify Access for demo-role

```bash
# Test as demo-role
aws sts assume-role \
  --role-arn arn:aws:iam::123456789012:role/demo-role \
  --role-session-name test-session \
  --duration-seconds 3600

# Set credentials (copy from output)
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."

# Test query
aws athena start-query-execution \
  --query-string "SELECT COUNT(*) FROM finsights_gold.dim_fund" \
  --result-configuration "OutputLocation=s3://your-datalake-bucket/athena-results/" \
  --query-execution-context "Database=finsights_gold"

# Expected: Query succeeds, returns ~120
```

#### 5.4: Review Audit Logs

```bash
# Check CloudTrail for all deployment events
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=PutObject \
  --start-time 2026-03-16T00:00:00Z \
  --end-time 2026-03-16T23:59:59Z \
  --max-results 50 \
  --query 'Events[*].[EventTime,EventName,Username,RequestParameters]' \
  --output table

# Expected: PutObject events for script uploads
```

---

## 📊 Deployment Status Dashboard

### Current State

| Component | Count | Status | Location |
|-----------|-------|--------|----------|
| **S3 Bucket** | 1 | ✅ | s3://your-datalake-bucket/ |
| **Scripts** | 11 | ✅ | s3://.../scripts/ |
| **Glue Databases** | 2 | ✅ | finsights_silver, finsights_gold |
| **Glue Jobs** | 10 | ✅ | Registered |
| **Silver Tables** | 3 | ⏸️ | Running... |
| **Gold Tables** | 4 | ⏸️ | Pending |
| **IAM Policy** | 1 | ✅ | demo-role/FinsightsWorkloadAccess |
| **LF Grants** | 5 | ⏸️ | Pending tables |
| **QuickSight** | 0 | ⏸️ | Pending subscription |

---

## ⏱️ Expected Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| 1. Infrastructure Setup | 5 min | ✅ Complete |
| 2. Bronze Job | 5-8 min | ⏸️ Running |
| 3. Silver Jobs (parallel) | 5-8 min | ⏸️ Pending |
| 4. Silver Quality Gate | 3-5 min | ⏸️ Pending |
| 5. Gold Jobs (parallel dims) | 5-8 min | ⏸️ Pending |
| 6. Gold Fact Job | 6-10 min | ⏸️ Pending |
| 7. Gold Quality Gate | 3-5 min | ⏸️ Pending |
| 8. Lake Formation Grants | 2 min | ⏸️ Pending |
| 9. QuickSight Dashboard | 10-15 min | ⏸️ Pending |
| **TOTAL** | **45-70 min** | **~15% Complete** |

---

## 💰 Cost Breakdown

### First Month Estimate

| Service | Usage | Unit Cost | Monthly Total |
|---------|-------|-----------|---------------|
| **Glue ETL** | 10 jobs × 2 workers × 0.25 DPU-hour | $0.44/DPU-hour | ~$2-5 |
| **S3 Storage** | 100 MB | $0.023/GB | <$1 |
| **Glue Data Catalog** | 7 tables | $1/month per 100K objects | <$1 |
| **Athena** | ~500 queries × 100 MB scanned | $5/TB scanned | <$1 |
| **QuickSight** | 1 author, 10 GB SPICE | $9/user/month | $9 |
| **CloudTrail** | Management events | Free tier | $0 |
| **TOTAL** | — | — | **~$15-20/month** |

### Ongoing Monthly Estimate

- **Glue Jobs:** $2-3 (if run monthly)
- **S3:** <$1
- **QuickSight:** $9-10
- **Athena:** <$1
- **TOTAL:** **~$12-15/month**

---

## 🔧 Troubleshooting Guide

### Issue: "Glue job stuck in WAITING"

**Cause:** No available Glue workers in your account/region.

**Fix:**
```bash
# Check service quotas
aws service-quotas get-service-quota \
  --service-code glue \
  --quota-code L-B5292A61 \
  --region us-east-1

# Request quota increase if needed
```

### Issue: "AccessDeniedException: User not authorized"

**Cause:** Missing IAM permissions.

**Fix:**
```bash
# Verify current user has required permissions
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::123456789012:user/demo-profile \
  --action-names glue:StartJobRun glue:GetJobRun s3:PutObject \
  --resource-arns "*"

# Add missing permissions to user policy
```

### Issue: "Quality gate failed: score < threshold"

**Cause:** Data quality issues in Bronze data.

**Fix:**
1. Check quality report: `s3://your-datalake-bucket/output/quality_reports/`
2. Review failed checks
3. Re-run Bronze job with fixes
4. Re-run Silver jobs

### Issue: "Table not found" in Athena

**Cause:** Table wasn't registered in Glue Data Catalog.

**Fix:**
```bash
# Check if table exists
aws glue get-table --database-name finsights_gold --name dim_fund

# If not found, re-run the Gold job that creates it
aws glue start-job-run --job-name gold_dim_fund
```

### Issue: "SPICE ingestion failed"

**Cause:** Insufficient SPICE capacity.

**Fix:**
1. Check capacity: QuickSight Console → Admin → SPICE capacity
2. Free up space or purchase more SPICE ($0.25/GB/month)
3. Re-trigger ingestion:
   ```bash
   aws quicksight create-ingestion \
     --aws-account-id 123456789012 \
     --data-set-id finsights-fact-performance \
     --ingestion-id retry-001 \
     --region us-east-1
   ```

---

## 🎯 Next Steps After Deployment

### Immediate (Day 1)

1. ✅ Verify all pipeline jobs completed successfully
2. ✅ Test dashboard with stakeholders
3. ✅ Grant access to additional users
4. ✅ Set up CloudWatch alarms for job failures

### Short-term (Week 1)

1. Deploy Airflow DAG for automated scheduling
2. Set up SNS notifications for failures
3. Create runbook for operations team
4. Document troubleshooting procedures

### Long-term (Month 1)

1. Add more seed questions to semantic.yaml
2. Create additional QuickSight dashboards
3. Integrate with ML pipelines
4. Add real-time data sources (replace synthetic)

---

## 📞 Support Contacts

**Questions or issues?**

- **Data Engineering Team:** data-eng@company.com
- **Slack Channel:** #data-pipeline-alerts
- **On-call:** PagerDuty rotation (see Confluence)
- **AWS Support:** Open ticket in AWS Console

**Documentation:**
- Project README: `workloads/us_mutual_funds_etf/README.md`
- Deployment Plan: `workloads/us_mutual_funds_etf/DEPLOYMENT_PLAN.md`
- QuickSight Guide: `workloads/us_mutual_funds_etf/QUICKSIGHT_SETUP_GUIDE.md`

---

**Status:** 🚀 Deployment in progress. Check back in ~30 minutes for pipeline completion.
