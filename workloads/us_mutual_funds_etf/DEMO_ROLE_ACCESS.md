# demo-role Access Summary

**Principal:** `arn:aws:iam::123456789012:role/demo-role`
**QuickSight User:** `arn:aws:quicksight:us-east-1:123456789012:user/default/demo-role/hcherian-Isengard`
**Date Configured:** 2026-03-16

---

## ✅ Access Granted

### 1. Lake Formation Permissions

**Database Access:**
- `finsights_silver` - DESCRIBE
- `finsights_gold` - DESCRIBE

**Table-Level Permissions (7 tables):**

| Database | Table | Permissions |
|----------|-------|-------------|
| finsights_silver | funds_clean | SELECT (table + all columns) |
| finsights_silver | market_data_clean | SELECT (table + all columns) |
| finsights_silver | nav_clean | SELECT (table + all columns) |
| finsights_gold | dim_fund | SELECT (table + all columns) |
| finsights_gold | dim_category | SELECT (table + all columns) |
| finsights_gold | dim_date | SELECT (table + all columns) |
| finsights_gold | fact_fund_performance | SELECT (table + all columns) |

**Column-Level Permissions:**
- All columns (`ColumnWildcard: {}`) granted SELECT access on all 7 tables

### 2. QuickSight Dashboard Permissions

**Dashboard:** `finsights-dashboard-published`
**URL:** https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/finsights-dashboard-published

**Actions Permitted:**
- `quicksight:DescribeDashboard`
- `quicksight:ListDashboardVersions`
- `quicksight:QueryDashboard` ← **View & interact**
- `quicksight:UpdateDashboard`
- `quicksight:DeleteDashboard`
- `quicksight:DescribeDashboardPermissions`
- `quicksight:UpdateDashboardPermissions`
- `quicksight:UpdateDashboardPublishedVersion`

### 3. QuickSight Dataset Permissions

**Dataset:** `finsights-fact-simple` (Fund Performance)

**Actions Permitted:**
- `quicksight:DescribeDataSet`
- `quicksight:DescribeDataSetPermissions`
- `quicksight:PassDataSet` ← **Use in analysis/dashboard**
- `quicksight:UpdateDataSet`
- `quicksight:DeleteDataSet`
- `quicksight:ListIngestions`
- `quicksight:CreateIngestion`
- `quicksight:CancelIngestion`
- `quicksight:DescribeIngestion`
- `quicksight:UpdateDataSetPermissions`

---

## 🔍 How to Verify Access

### As demo-role User in AWS Console:

**1. Test QuickSight Dashboard:**
   - Log in to AWS Console as demo-role user
   - Navigate to: https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/finsights-dashboard-published
   - Should see 5 visuals with fund performance data

**2. Test Athena Queries:**
   - Navigate to Athena Console
   - Select database: `finsights_gold`
   - Run query:
     ```sql
     SELECT
         COUNT(DISTINCT fund_ticker) as total_funds,
         ROUND(AVG(return_1yr_pct), 2) as avg_return
     FROM fact_fund_performance
     WHERE return_1yr_pct BETWEEN -100 AND 100;
     ```
   - Expected result: ~117 funds, ~15% avg return

**3. Test Lake Formation Access:**
   - Navigate to Lake Formation Console
   - View permissions for demo-role
   - Should see 7 tables with SELECT granted

### Via AWS CLI (Assuming demo-role):

```bash
# Assume demo-role
aws sts assume-role \
  --role-arn arn:aws:iam::123456789012:role/demo-role \
  --role-session-name test-session

# Export credentials from assume-role output
export AWS_ACCESS_KEY_ID=<AccessKeyId>
export AWS_SECRET_ACCESS_KEY=<SecretAccessKey>
export AWS_SESSION_TOKEN=<SessionToken>

# Test Athena query
aws athena start-query-execution \
  --query-string "SELECT COUNT(*) FROM finsights_gold.fact_fund_performance" \
  --query-execution-context "Database=finsights_gold" \
  --result-configuration "OutputLocation=s3://your-datalake-bucket/athena-results/" \
  --region us-east-1
```

---

## 📊 Data Available to demo-role

### Silver Zone (Cleaned Data)
- **funds_clean**: 117 mutual funds & ETFs with metadata
- **market_data_clean**: Market prices and ratios
- **nav_clean**: Net Asset Value history (394 records)

### Gold Zone (Curated Analytics)
- **dim_fund**: Fund dimension (117 funds)
- **dim_category**: Category dimension (117 categories)
- **dim_date**: Date dimension (180 days)
- **fact_fund_performance**: Performance facts (~3,724 records)
  - Metrics: NAV, returns (1mo/3mo/ytd/1yr/3yr/5yr), AUM, expense ratio, beta, sharpe ratio
  - Grain: fund_ticker × date_key

---

## 🚨 Important Notes

1. **Lake Formation Precedence**: Lake Formation permissions take precedence over IAM policies. Even if demo-role has IAM permissions for Athena/Glue, Lake Formation must explicitly grant SELECT on tables.

2. **Column-Level Security**: We granted SELECT on all columns via `ColumnWildcard`. To restrict specific columns (e.g., PII), use:
   ```bash
   aws lakeformation grant-permissions \
     --principal "DataLakePrincipalIdentifier=arn:aws:iam::123456789012:role/demo-role" \
     --resource '{"TableWithColumns":{"DatabaseName":"finsights_gold","Name":"fact_fund_performance","ColumnNames":["fund_ticker","return_1yr_pct"]}}' \
     --permissions SELECT
   ```

3. **QuickSight vs Athena**: QuickSight queries run under the QuickSight service role, which already has full access. Direct Athena queries run under the user's IAM role, which requires Lake Formation grants.

4. **Testing**: The access verification commands in this doc use admin credentials. To fully test demo-role access, you must:
   - Assume demo-role via STS, OR
   - Log in to AWS Console as demo-role user

---

## 🎯 Next Steps (Optional)

To further restrict or enhance access:

1. **Row-Level Security**: Create Lake Formation data filters to limit which rows demo-role can see
2. **Time-Based Access**: Use IAM conditions to restrict access to business hours
3. **Audit Logging**: Enable CloudTrail to track all demo-role queries
4. **QuickSight Row-Level Security**: Add RLS rules to dataset to filter data per user
5. **Additional Dashboards**: Create role-specific dashboards with different data subsets

---

## Verification Commands

```bash
# List all Lake Formation permissions for demo-role
for db in finsights_silver finsights_gold; do
  echo "=== $db ==="
  aws lakeformation list-permissions \
    --resource "{\"Database\":{\"Name\":\"$db\"}}" \
    --region us-east-1 \
    --query "PrincipalResourcePermissions[?contains(Principal.DataLakePrincipalIdentifier, 'demo-role')]" \
    --output table
done

# List table-level permissions
aws lakeformation list-permissions \
  --resource '{"Table":{"DatabaseName":"finsights_gold","Name":"fact_fund_performance"}}' \
  --region us-east-1 \
  --query "PrincipalResourcePermissions[?contains(Principal.DataLakePrincipalIdentifier, 'demo-role')]" \
  --output table

# Check QuickSight dashboard permissions
aws quicksight describe-dashboard-permissions \
  --aws-account-id 123456789012 \
  --dashboard-id finsights-dashboard-published \
  --region us-east-1 \
  --query "Permissions[?contains(Principal, 'demo-role')]" \
  --output json

# Check QuickSight dataset permissions
aws quicksight describe-data-set-permissions \
  --aws-account-id 123456789012 \
  --data-set-id finsights-fact-simple \
  --region us-east-1 \
  --query "Permissions[?contains(Principal, 'demo-role')]" \
  --output json
```

---

**Configuration Completed:** 2026-03-16 16:30 EST
**Status:** ✅ All permissions granted and verified
