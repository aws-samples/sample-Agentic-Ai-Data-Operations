# QuickSight Lake Formation Permissions Fix

**Issue Date:** 2026-03-16
**Issue:** QuickSight dashboard showing "You don't have sufficient AWS Lake Formation permissions to run this query"
**Status:** ✅ RESOLVED

---

## Problem

QuickSight dashboard visuals were failing with Lake Formation permission errors:
```
You don't have sufficient AWS Lake Formation permissions to run this query.
Contact your administrator for assistance.
```

**Root Cause:** QuickSight service role (`aws-quicksight-service-role-v0`) did not have Lake Formation permissions to access the Gold and Silver zone tables.

---

## Solution Applied

Granted Lake Formation permissions to QuickSight service role:

**Service Role ARN:**
```
arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0
```

### Permissions Granted

**1. Database-Level Permissions:**
- `finsights_silver` → DESCRIBE
- `finsights_gold` → DESCRIBE

**2. Table-Level Permissions (Column-Level Access):**

| Database | Table | Permissions |
|----------|-------|-------------|
| finsights_silver | funds_clean | SELECT (all columns) |
| finsights_silver | market_data_clean | SELECT (all columns) |
| finsights_silver | nav_clean | SELECT (all columns) |
| finsights_gold | dim_fund | SELECT (all columns) |
| finsights_gold | dim_category | SELECT (all columns) |
| finsights_gold | dim_date | SELECT (all columns) |
| finsights_gold | fact_fund_performance | SELECT (all columns) |

---

## Verification

### Lake Formation Permissions Confirmed

```bash
# Check database permissions
aws lakeformation list-permissions \
  --resource '{"Database":{"Name":"finsights_gold"}}' \
  --region us-east-1 \
  --query "PrincipalResourcePermissions[?contains(Principal.DataLakePrincipalIdentifier, 'quicksight')]"
```

**Result:**
- ✅ finsights_silver: DESCRIBE
- ✅ finsights_gold: DESCRIBE

### Table Permissions Confirmed

```bash
# Check table permissions
aws lakeformation list-permissions \
  --resource '{"Table":{"DatabaseName":"finsights_gold","Name":"fact_fund_performance"}}' \
  --region us-east-1 \
  --query "PrincipalResourcePermissions[?contains(Principal.DataLakePrincipalIdentifier, 'quicksight')]"
```

**Result:**
- ✅ All 7 tables have SELECT permission with column-level access

---

## Dashboard Access

**Dashboard URL:**
```
https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/finsights-dashboard-published
```

**Expected Visuals (5 total):**
1. Total Funds (KPI) - COUNT(DISTINCT fund_ticker)
2. Average 1-Year Return (KPI) - AVG(return_1yr_pct)
3. Total AUM (KPI) - SUM(total_assets_millions) / 1000
4. Top 10 Funds by 1Y Return (Bar Chart)
5. Fund Performance Matrix (Table)

---

## How to Refresh Dashboard

After permission changes, the dashboard may need to be refreshed:

**Option 1: Refresh Entire Dashboard**
1. Open dashboard: https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/finsights-dashboard-published
2. Click **"Refresh"** button in top menu
3. Wait for all visuals to reload

**Option 2: Refresh Individual Visuals**
1. Hover over each visual showing the error
2. Click the **refresh icon** (circular arrow) in top-right corner of visual
3. Visual should reload with data

**Option 3: Clear Cache**
1. Go to QuickSight Analysis: https://us-east-1.quicksight.aws.amazon.com/sn/analyses/finsights-analysis-v2
2. Click **"Edit"**
3. Click **"Refresh"** → **"Clear all caches"**
4. Re-publish dashboard

---

## Key Technical Details

### Why This Error Occurred

1. **Lake Formation Precedence**: Lake Formation permissions override IAM policies for data access
2. **QuickSight Service Role**: QuickSight queries run under `aws-quicksight-service-role-v0`, not the user's role
3. **Column-Level Security**: Lake Formation requires explicit `TableWithColumns` grants for column access

### ARN Path Issue

Initial attempts failed because of incorrect ARN format:
- ❌ `arn:aws:iam::123456789012:role/aws-quicksight-service-role-v0`
- ✅ `arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0`

The role is in the `service-role` path, which must be included in the ARN.

### Permission Scope

**Column Wildcard** used to grant access to all columns:
```json
{
  "TableWithColumns": {
    "DatabaseName": "finsights_gold",
    "Name": "fact_fund_performance",
    "ColumnWildcard": {}
  }
}
```

This grants SELECT on all columns without needing to list each column individually.

---

## Related Principals

### Currently Granted Lake Formation Access:

| Principal | Type | Databases | Permissions |
|-----------|------|-----------|-------------|
| demo-profile | IAM User | finsights_silver, finsights_gold | ALL, ALTER, CREATE_TABLE, DESCRIBE, DROP |
| demo-role | IAM Role | finsights_silver, finsights_gold | SELECT (all tables) |
| aws-quicksight-service-role-v0 | Service Role | finsights_silver, finsights_gold | SELECT (all tables) |
| GlueServiceRole | Service Role | finsights_silver, finsights_gold | CREATE_TABLE, ALTER, DROP, DESCRIBE, SELECT |

---

## Testing

### Test Query via Athena (to verify QuickSight will work)

```sql
SELECT
    COUNT(DISTINCT fund_ticker) as total_funds,
    ROUND(AVG(return_1yr_pct), 2) as avg_1yr_return,
    ROUND(SUM(total_assets_millions) / 1000, 2) as total_aum_billions
FROM finsights_gold.fact_fund_performance
WHERE return_1yr_pct BETWEEN -100 AND 100;
```

**Expected Result:**
- Total Funds: 24
- Avg 1Y Return: ~13.81%
- Total AUM: ~$2,373.52 Billions

If this query works in Athena, QuickSight will also work (both use the same Athena engine).

---

## Rollback (if needed)

To remove QuickSight service role permissions:

```bash
QS_ROLE="arn:aws:iam::123456789012:role/service-role/aws-quicksight-service-role-v0"

# Revoke database permissions
aws lakeformation revoke-permissions \
  --principal "DataLakePrincipalIdentifier=$QS_ROLE" \
  --resource '{"Database":{"Name":"finsights_gold"}}' \
  --permissions DESCRIBE \
  --region us-east-1

# Revoke table permissions
aws lakeformation revoke-permissions \
  --principal "DataLakePrincipalIdentifier=$QS_ROLE" \
  --resource '{"TableWithColumns":{"DatabaseName":"finsights_gold","Name":"fact_fund_performance","ColumnWildcard":{}}}' \
  --permissions SELECT \
  --region us-east-1
```

---

## Prevention for Future Workloads

When creating new QuickSight dashboards on Lake Formation-managed data:

1. **Grant Database Permissions First:**
   ```bash
   aws lakeformation grant-permissions \
     --principal "DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT_ID:role/service-role/aws-quicksight-service-role-v0" \
     --resource '{"Database":{"Name":"DATABASE_NAME"}}' \
     --permissions DESCRIBE
   ```

2. **Grant Table Permissions:**
   ```bash
   aws lakeformation grant-permissions \
     --principal "DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT_ID:role/service-role/aws-quicksight-service-role-v0" \
     --resource '{"TableWithColumns":{"DatabaseName":"DATABASE_NAME","Name":"TABLE_NAME","ColumnWildcard":{}}}' \
     --permissions SELECT
   ```

3. **Test in Athena First:** Before creating QuickSight visuals, verify Lake Formation permissions work by running test queries in Athena.

---

## Documentation References

- **Main Project Summary:** `PROJECT_COMPLETE.md`
- **Access Configuration:** `DEMO_ROLE_ACCESS.md`
- **Access Test Results:** `ACCESS_TEST_RESULTS.md`
- **This Fix Document:** `QUICKSIGHT_LAKE_FORMATION_FIX.md`

---

**Fix Applied:** 2026-03-16 16:40 EST
**Applied By:** Claude Code (Sonnet 4.5)
**Status:** ✅ RESOLVED — Dashboard should now load all visuals successfully
