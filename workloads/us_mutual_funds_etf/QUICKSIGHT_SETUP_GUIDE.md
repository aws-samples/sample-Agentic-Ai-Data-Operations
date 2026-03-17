# QuickSight Setup Guide — US Mutual Funds & ETF Dashboard

**Date:** 2026-03-16
**Dashboard ID:** `finsights-finance-dashboard`
**Account:** 123456789012

---

## Prerequisites

Before running the QuickSight provisioning script, ensure:

1. ✅ **AWS Account has QuickSight subscription** (Standard or Enterprise)
2. ✅ **User has QuickSight Author or Admin role**
3. ✅ **Glue Gold tables exist** (run ETL pipeline first)
4. ✅ **boto3 installed** (`pip install boto3`)

---

## Step 1: Subscribe to QuickSight

### Option A: Via AWS Console (Recommended)

1. **Navigate to QuickSight:**
   ```
   https://console.aws.amazon.com/quicksight/home?region=us-east-1
   ```

2. **Sign Up for QuickSight:**
   - Click "Sign up for QuickSight"
   - Choose **Standard Edition** ($9/user/month) or **Enterprise Edition** ($18/user/month)
   - 30-day free trial available

3. **Configure Account:**
   - **Account name:** `finsights-analytics`
   - **Notification email:** Your email
   - **QuickSight access to AWS services:**
     - ✅ Amazon Athena
     - ✅ Amazon S3 (select `your-datalake-bucket` bucket)
     - ✅ AWS Glue Data Catalog
   - **IAM role:** Create new role or use existing

4. **Finish Setup:**
   - Click "Finish"
   - Wait for account provisioning (~2 minutes)

### Option B: Via AWS CLI

```bash
# Check if QuickSight is already subscribed
aws quicksight describe-account-settings --aws-account-id 123456789012 --region us-east-1

# If not subscribed, use Console (CLI signup not supported)
```

---

## Step 2: Add User as QuickSight Author

### Via AWS Console

1. **Go to QuickSight:**
   ```
   https://us-east-1.quicksight.aws.amazon.com/sn/admin
   ```

2. **Manage Users:**
   - Click "Manage QuickSight" (top-right)
   - Click "Manage users"

3. **Invite User:**
   - Click "Invite users"
   - **User type:** IAM user
   - **IAM user:** `demo-profile` or your current IAM user
   - **Role:** Author (can create and publish dashboards)
   - Click "Invite"

4. **Verify User:**
   - User should appear in the user list
   - Status: "Active"
   - Role: "Author"

### Via AWS CLI

```bash
# Register IAM user as QuickSight user
aws quicksight register-user \
  --aws-account-id 123456789012 \
  --namespace default \
  --identity-type IAM \
  --iam-arn arn:aws:iam::123456789012:user/demo-profile \
  --user-role AUTHOR \
  --email your-email@example.com \
  --region us-east-1
```

---

## Step 3: Get QuickSight User ARN

### Via AWS Console

1. **List Users:**
   ```
   https://us-east-1.quicksight.aws.amazon.com/sn/admin#users
   ```

2. **Find User:**
   - Locate your user in the list
   - Copy the user ARN (format: `arn:aws:quicksight:us-east-1:123456789012:user/default/demo-profile`)

### Via AWS CLI

```bash
# List all QuickSight users
aws quicksight list-users \
  --aws-account-id 123456789012 \
  --namespace default \
  --region us-east-1 \
  --query 'UserList[*].[UserName,Arn,Role]' \
  --output table

# Get specific user ARN
aws quicksight describe-user \
  --aws-account-id 123456789012 \
  --namespace default \
  --user-name demo-profile \
  --region us-east-1 \
  --query 'User.Arn' \
  --output text
```

**Example Output:**
```
arn:aws:quicksight:us-east-1:123456789012:user/default/demo-profile
```

---

## Step 4: Update QuickSight Script

Edit `scripts/quicksight/quicksight_dashboard_setup.py`:

```python
# BEFORE (placeholder values):
AWS_REGION = "us-east-1"
ACCOUNT_ID = "123456789012"  # ❌ Placeholder
QS_AUTHOR_ARN = "arn:aws:quicksight:us-east-1:123456789012:user/default/admin"  # ❌ Placeholder

# AFTER (your actual values):
AWS_REGION = "us-east-1"
ACCOUNT_ID = "123456789012"  # ✅ Your AWS account ID
QS_AUTHOR_ARN = "arn:aws:quicksight:us-east-1:123456789012:user/default/demo-profile"  # ✅ Your QuickSight user ARN
```

**Find these values:**

```bash
# Get AWS Account ID
aws sts get-caller-identity --query 'Account' --output text

# Get QuickSight User ARN
aws quicksight describe-user \
  --aws-account-id 123456789012 \
  --namespace default \
  --user-name demo-profile \
  --region us-east-1 \
  --query 'User.Arn' \
  --output text
```

---

## Step 5: Run QuickSight Provisioning Script

```bash
cd /path/to/claude-data-operations/workloads/us_mutual_funds_etf

# Run the script
python3 scripts/quicksight/quicksight_dashboard_setup.py
```

**Expected Output:**

```
================================================================================
QUICKSIGHT DASHBOARD SETUP - US MUTUAL FUNDS & ETF
================================================================================

AWS Region: us-east-1
Account ID: 123456789012
Author ARN: arn:aws:quicksight:us-east-1:123456789012:user/default/demo-profile
Glue Database: finsights_gold

[STEP 1] Creating Athena Data Source...
  ✅ Data source created: finsights-athena-source

[STEP 2] Creating Datasets...
  ✅ Dataset created: finsights-dim-fund
  ✅ Dataset created: finsights-dim-category
  ✅ Dataset created: finsights-dim-date
  ✅ Dataset created: finsights-fact-performance (with joins)
  ✅ SPICE ingestion triggered: initial-ingestion-001

[STEP 3] Creating Analysis with 9 Visuals...
  ✅ Analysis created: finsights-finance-analysis

[STEP 4] Publishing Dashboard...
  ✅ Dashboard published: finsights-finance-dashboard

[STEP 5] Configuring SPICE Refresh Schedule...
  ✅ Daily refresh scheduled: 06:00 America/New_York

================================================================================
DEPLOYMENT SUMMARY
================================================================================

Resource                 | ID                              | Status
-------------------------|---------------------------------|--------
Athena Data Source       | finsights-athena-source         | ✅
Dataset: dim_fund        | finsights-dim-fund              | ✅
Dataset: dim_category    | finsights-dim-category          | ✅
Dataset: dim_date        | finsights-dim-date              | ✅
Dataset: fact (joined)   | finsights-fact-performance      | ✅
SPICE Ingestion          | initial-ingestion-001           | ✅
Analysis                 | finsights-finance-analysis      | ✅
Dashboard                | finsights-finance-dashboard     | ✅
Refresh Schedule         | daily-refresh-001               | ✅

Dashboard URL:
https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/finsights-finance-dashboard
```

**Duration:** ~10-15 minutes (includes SPICE ingestion)

---

## Step 6: Access the Dashboard

### Via AWS Console

```
https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/finsights-finance-dashboard
```

### Via QuickSight Home

1. Go to QuickSight home: `https://us-east-1.quicksight.aws.amazon.com/sn/start`
2. Click "Dashboards" in left nav
3. Find "Finsights Finance Dashboard"
4. Click to open

---

## Troubleshooting

### Error: "User is not authorized to access this resource"

**Cause:** Current IAM user doesn't have QuickSight permissions.

**Fix:**
1. Verify QuickSight subscription exists
2. Add user as QuickSight Author (see Step 2)
3. Update script with correct `QS_AUTHOR_ARN`

### Error: "Dashboard arn:aws:quicksight:...:dashboard/... is not found"

**Cause:** Dashboard hasn't been published yet or script failed.

**Fix:**
1. Check script output for errors in previous steps
2. Verify all datasets were created successfully
3. Re-run script (it's idempotent)

### Error: "Table not found" during dataset creation

**Cause:** Glue Gold tables don't exist yet.

**Fix:**
1. Run Glue ETL pipeline first: `aws glue start-job-run --job-name bronze_data_generation`
2. Wait for all jobs to complete (Bronze → Silver → Gold)
3. Verify tables exist: `aws glue get-tables --database-name finsights_gold`
4. Re-run QuickSight script

### Error: "SPICE ingestion failed"

**Cause:** Insufficient SPICE capacity or data source issue.

**Fix:**
1. Check QuickSight SPICE capacity: Console → Admin → SPICE capacity
2. Free up space or purchase more SPICE
3. Verify Athena can query the tables:
   ```sql
   SELECT COUNT(*) FROM finsights_gold.dim_fund;
   ```
4. Re-trigger ingestion:
   ```bash
   aws quicksight create-ingestion \
     --aws-account-id 123456789012 \
     --data-set-id finsights-fact-performance \
     --ingestion-id retry-001 \
     --region us-east-1
   ```

### Error: "InvalidParameterValueException: Invalid principal"

**Cause:** `QS_AUTHOR_ARN` format is incorrect.

**Fix:**
1. Verify ARN format: `arn:aws:quicksight:REGION:ACCOUNT:user/NAMESPACE/USERNAME`
2. Get correct ARN:
   ```bash
   aws quicksight list-users --aws-account-id 123456789012 --namespace default --region us-east-1
   ```
3. Update script and re-run

---

## Dashboard Features

Once deployed, the dashboard includes:

### **9 Visuals:**

1. **KPI: Total Funds** — COUNT(fund_ticker)
2. **KPI: Avg 1Y Return** — AVG(return_1yr_pct)
3. **KPI: Total AUM** — SUM(total_assets_millions) / 1000
4. **KPI: Avg Expense Ratio** — AVG(expense_ratio_pct)
5. **Bar Chart: Avg Returns by Asset Class** — Horizontal bar, multiple series
6. **Line Chart: NAV Trend Over Time** — Time series by fund type
7. **Donut Chart: AUM by Management Company** — Proportional breakdown
8. **Scatter Plot: Risk vs Return** — Beta vs 1Y return, sized by AUM
9. **Pivot Table: Category Performance** — Matrix with conditional formatting

### **Interactive Features:**

- ✅ Ad-hoc filtering (date range, fund type, management company)
- ✅ Export to CSV (any visual)
- ✅ Drill-down (click on chart elements)
- ✅ Auto-refresh (daily at 06:00 ET)
- ✅ Mobile-responsive

### **Calculated Fields:**

- `AUM Billions` = `total_assets_millions / 1000`
- `Expense Ratio bps` = `expense_ratio_pct * 100`
- `Risk-Adjusted Label` = `ifelse(sharpe_ratio >= 1.5, "High", ifelse(sharpe_ratio >= 0.5, "Medium", "Low"))`

---

## Post-Deployment

### Grant Dashboard Access to Others

```bash
# Grant view access to another user
aws quicksight update-dashboard-permissions \
  --aws-account-id 123456789012 \
  --dashboard-id finsights-finance-dashboard \
  --grant-permissions "Principal=arn:aws:quicksight:us-east-1:123456789012:user/default/OTHER_USER,Actions=quicksight:DescribeDashboard,Actions=quicksight:QueryDashboard" \
  --region us-east-1
```

### Embed Dashboard in Web App

```python
# Generate embed URL (requires QuickSight Enterprise)
import boto3

qs = boto3.client('quicksight', region_name='us-east-1')

response = qs.generate_embed_url_for_registered_user(
    AwsAccountId='123456789012',
    SessionLifetimeInMinutes=600,
    UserArn='arn:aws:quicksight:us-east-1:123456789012:user/default/demo-profile',
    ExperienceConfiguration={
        'Dashboard': {
            'InitialDashboardId': 'finsights-finance-dashboard'
        }
    }
)

print(response['EmbedUrl'])
```

### Monitor SPICE Usage

```bash
# Check SPICE capacity
aws quicksight describe-account-settings \
  --aws-account-id 123456789012 \
  --region us-east-1 \
  --query 'AccountSettings.DefaultNamespace'

# List ingestions
aws quicksight list-ingestions \
  --aws-account-id 123456789012 \
  --data-set-id finsights-fact-performance \
  --region us-east-1
```

---

## Cost Estimate

### QuickSight Costs

| Component | Unit Price | Monthly Est. |
|-----------|------------|--------------|
| **Standard Edition** | $9/user/month | $9 |
| **SPICE** | $0.25/GB/month | <$1 (dataset is ~100 MB) |
| **Enterprise Edition** (if needed) | $18/user/month | $18 |
| **TOTAL (Standard)** | — | **~$10/month** |

**Free Tier:** 30-day trial (4 SPICE users, 10 GB SPICE)

### Associated AWS Costs

| Service | Usage | Monthly Est. |
|---------|-------|--------------|
| **Athena** | Queries for SPICE refresh | <$1 (scans ~100 MB/day) |
| **Glue Data Catalog** | 7 tables | <$1 |
| **S3** | ~100 MB data | <$1 |
| **TOTAL** | — | **~$2/month** |

**Grand Total:** ~$12/month (Standard Edition)

---

## Next Steps

1. ✅ Subscribe to QuickSight
2. ✅ Add user as Author
3. ✅ Update script with correct ARN
4. ✅ Run provisioning script
5. ✅ Access dashboard
6. Share with team
7. Embed in internal tools (optional)
8. Set up alerts for data freshness

---

## Support

**Questions?**
- QuickSight Docs: https://docs.aws.amazon.com/quicksight/
- Community Forum: https://repost.aws/tags/TA4ckwVqt2TCqkh1p4fz3ctg/amazon-quick-sight
- AWS Support: Open ticket in AWS Console

**Project Contact:**
- Data Engineering: data-eng@company.com
- Slack: #data-pipeline-alerts
