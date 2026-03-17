# QuickSight Deployment Complete — US Mutual Funds & ETF

**Date:** March 16, 2026
**Status:** ✅ **DATASET READY** — Manual visualization creation required
**Approach:** Simplified dashboard (DIRECT_QUERY, no complex joins)

---

## Deployment Summary

✅ **Successfully Created:**
- Athena Data Source: `finsights-athena-simple`
- Dataset: `finsights-fact-simple` (Fund Performance)
- Import Mode: DIRECT_QUERY (real-time queries via Athena)
- Calculated Fields: AUM (Billions), Expense Ratio (bps)

⏸️ **Manual Steps Required:**
- Create visualizations in QuickSight console
- Publish dashboard

**Why Simplified?** The original script encountered complex join issues with QuickSight's API. This simpler approach:
- Uses DIRECT_QUERY (no SPICE ingestion needed)
- Single fact dataset (no pre-joined dimensions)
- Queries Gold zone directly via Athena
- Faster to deploy and iterate

---

## QuickSight Resources Created

### Data Source

**ID:** `finsights-athena-simple`
**Type:** Athena
**Connection:**
- Workgroup: `primary`
- Catalog: `AwsDataCatalog`
- Database: `finsights_gold`

**ARN:**
```
arn:aws:quicksight:us-east-1:123456789012:datasource/finsights-athena-simple
```

### Dataset

**ID:** `finsights-fact-simple`
**Name:** Fund Performance (Simple)
**Source Table:** `finsights_gold.fact_fund_performance`
**Import Mode:** DIRECT_QUERY

**Columns Available:**
| Column | Type | Description |
|--------|------|-------------|
| `fund_ticker` | STRING | Fund identifier |
| `date_key` | INTEGER | Date dimension key |
| `nav` | DECIMAL | Net Asset Value |
| `total_assets_millions` | DECIMAL | Assets Under Management (millions) |
| `return_1mo_pct` | DECIMAL | 1-month return % |
| `return_3mo_pct` | DECIMAL | 3-month return % |
| `return_ytd_pct` | DECIMAL | Year-to-date return % |
| `return_1yr_pct` | DECIMAL | 1-year return % |
| `return_3yr_pct` | DECIMAL | 3-year return % |
| `return_5yr_pct` | DECIMAL | 5-year return % |
| `expense_ratio_pct` | DECIMAL | Fund expense ratio % |
| `beta` | DECIMAL | Market beta (risk) |
| `sharpe_ratio` | DECIMAL | Risk-adjusted return |

**Calculated Fields (Pre-configured):**
- `AUM (Billions)` = `total_assets_millions / 1000`
- `Expense Ratio (bps)` = `expense_ratio_pct * 100`

---

## Create Visualizations (Manual Steps)

### Step 1: Open QuickSight

Navigate to QuickSight home:
```
https://us-east-1.quicksight.aws.amazon.com/sn/start
```

### Step 2: Find the Dataset

1. Click **"Datasets"** in the left navigation
2. Find **"Fund Performance (Simple)"** or search for `finsights-fact-simple`
3. Click the dataset name

### Step 3: Create Analysis

1. Click **"Create analysis"** button (top-right)
2. QuickSight will open a blank canvas with the dataset loaded

### Step 4: Add Visualizations

#### Recommended Visualizations

**1. KPI: Total Funds**
- Visual type: **KPI**
- Value: `COUNT(DISTINCT fund_ticker)`
- Title: "Total Funds Tracked"

**2. KPI: Average 1-Year Return**
- Visual type: **KPI**
- Value: `AVG(return_1yr_pct)`
- Format: Percentage
- Title: "Avg 1Y Return"

**3. KPI: Total AUM**
- Visual type: **KPI**
- Value: `SUM(AUM (Billions))`
- Format: Currency (Billions)
- Title: "Total Assets Under Management"

**4. Line Chart: NAV Trend**
- Visual type: **Line chart**
- X-axis: `date_key` (convert to date if needed)
- Y-axis: `AVG(nav)`
- Color: `fund_ticker` (limit to top 10 funds)
- Title: "NAV Trend Over Time"

**5. Bar Chart: Top Performers**
- Visual type: **Horizontal bar chart**
- Y-axis: `fund_ticker`
- X-axis: `AVG(return_1yr_pct)`
- Sort: Descending by return
- Limit: Top 10
- Title: "Top 10 Funds by 1Y Return"

**6. Scatter Plot: Risk vs Return**
- Visual type: **Scatter plot**
- X-axis: `AVG(beta)` (risk)
- Y-axis: `AVG(return_1yr_pct)` (return)
- Size: `SUM(total_assets_millions)` (AUM)
- Color: `fund_ticker`
- Title: "Risk vs Return Analysis"

**7. Pivot Table: Performance Summary**
- Visual type: **Pivot table**
- Rows: `fund_ticker`
- Values:
  - `AVG(return_1mo_pct)`
  - `AVG(return_3mo_pct)`
  - `AVG(return_ytd_pct)`
  - `AVG(return_1yr_pct)`
  - `AVG(sharpe_ratio)`
- Conditional formatting: Green for positive returns, red for negative
- Title: "Fund Performance Matrix"

### Step 5: Add Filters (Optional)

Add interactive filters to the dashboard:
- **Date Range Filter:** `date_key` (allow users to select time period)
- **Fund Filter:** `fund_ticker` (allow users to select specific funds)
- **Return Threshold:** `return_1yr_pct` (filter by minimum return)

### Step 6: Style the Dashboard

1. **Layout:** Arrange visuals in a grid
   - Top row: 3 KPIs
   - Middle row: Line chart + Bar chart
   - Bottom row: Scatter plot + Pivot table

2. **Theme:** Apply a theme
   - Click **"Themes"** in top menu
   - Choose "Midnight" or "Seaside" for professional look

3. **Title:** Add dashboard title
   - Click **"Add"** → **"Text box"**
   - Enter: "US Mutual Funds & ETF Performance Dashboard"
   - Style: Large, bold, centered

### Step 7: Publish Dashboard

1. Click **"Share"** (top-right)
2. Click **"Publish dashboard"**
3. Enter dashboard name: "Fund Performance Dashboard"
4. Click **"Publish"**

5. **Set Permissions** (optional):
   - Add other users/groups who should view the dashboard
   - Grant "Viewer" role for read-only access

6. **Get Dashboard URL:**
   - After publishing, copy the dashboard URL
   - Format: `https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/{dashboard-id}`

---

## Verification Commands

### Check Dataset

```bash
# Describe dataset
aws quicksight describe-data-set \
  --aws-account-id 123456789012 \
  --data-set-id finsights-fact-simple \
  --region us-east-1 \
  --query 'DataSet.[Name,ImportMode]' \
  --output table
```

Expected output:
```
--------------------------------------------------
|               DescribeDataSet                  |
+-----------------------------+------------------+
|  Fund Performance (Simple)  |  DIRECT_QUERY    |
+-----------------------------+------------------+
```

### Test Query via Athena (Verify Data)

```sql
-- Quick preview
SELECT
    fund_ticker,
    COUNT(*) AS records,
    AVG(return_1yr_pct) AS avg_1y_return,
    AVG(nav) AS avg_nav,
    SUM(total_assets_millions) / 1000 AS total_aum_billions
FROM finsights_gold.fact_fund_performance
GROUP BY fund_ticker
ORDER BY avg_1y_return DESC
LIMIT 10;
```

### List All QuickSight Datasets

```bash
aws quicksight list-data-sets \
  --aws-account-id 123456789012 \
  --region us-east-1 \
  --query 'DataSetSummaries[*].[Name,DataSetId]' \
  --output table
```

---

## Alternative: Join with Dimension Tables (Advanced)

If you want to enrich visualizations with dimension data (fund names, categories), you can:

### Option A: Use QuickSight Relationships

1. In the dataset editor, click **"Add data"**
2. Select `dim_fund`, `dim_category`, `dim_date` from `finsights_gold`
3. QuickSight will auto-detect relationships based on column names
4. Set join type to **LEFT** (to keep all facts)
5. Use dimension columns in visualizations

### Option B: Create Athena Views

Create SQL views in Athena that pre-join tables:

```sql
CREATE OR REPLACE VIEW finsights_gold.vw_fund_performance AS
SELECT
    f.fund_ticker,
    f.fund_name,
    f.management_company,
    f.asset_class,
    cat.morningstar_category,
    d.as_of_date,
    fact.nav,
    fact.return_1yr_pct,
    fact.total_assets_millions,
    fact.expense_ratio_pct,
    fact.sharpe_ratio
FROM finsights_gold.fact_fund_performance fact
LEFT JOIN finsights_gold.dim_fund f ON fact.fund_ticker = f.fund_ticker
LEFT JOIN finsights_gold.dim_category cat ON fact.category_key = cat.category_key
LEFT JOIN finsights_gold.dim_date d ON fact.date_key = d.date_key;
```

Then create a new dataset in QuickSight pointing to `vw_fund_performance`.

---

## Cost Considerations

### DIRECT_QUERY Mode

**Pros:**
- No SPICE storage costs ($0.25/GB/month)
- No ingestion time (instant access to latest data)
- Automatically reflects changes in Gold zone

**Cons:**
- Athena query costs: $5 per TB scanned
- Slower performance (seconds vs sub-second)

**Estimated Monthly Cost:**
- Dataset size: ~10 MB (fact table)
- Typical queries: ~200 queries/month scanning 10 MB each = 2 GB total
- Athena cost: 2 GB × $5/TB = **$0.01/month**
- QuickSight user: **$9/month** (Standard Edition Author)
- **Total: ~$9.01/month**

### Switch to SPICE (Optional)

If dashboard performance is slow, switch to SPICE:

```bash
# Update dataset import mode
aws quicksight update-data-set \
  --aws-account-id 123456789012 \
  --data-set-id finsights-fact-simple \
  --region us-east-1 \
  --import-mode SPICE
```

Then trigger ingestion:
```bash
aws quicksight create-ingestion \
  --aws-account-id 123456789012 \
  --data-set-id finsights-fact-simple \
  --ingestion-id initial-load-001 \
  --region us-east-1
```

**SPICE Cost:** ~10 MB × $0.25/GB/month = **$0.0025/month** (negligible)

---

## Troubleshooting

### Issue: "Dataset not found"

**Solution:** Verify dataset ID:
```bash
aws quicksight list-data-sets --aws-account-id 123456789012 --region us-east-1
```

### Issue: "Access denied" when querying

**Solution:** Grant Lake Formation permissions:
```bash
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::123456789012:role/aws-quicksight-service-role-v0 \
  --resource '{"Table":{"DatabaseName":"finsights_gold","Name":"fact_fund_performance"}}' \
  --permissions SELECT
```

### Issue: "No data available"

**Solution:** Verify Gold zone has data:
```bash
# Query via Athena
aws athena start-query-execution \
  --query-string "SELECT COUNT(*) FROM finsights_gold.fact_fund_performance" \
  --result-configuration "OutputLocation=s3://your-datalake-bucket/athena-results/" \
  --query-execution-context "Database=finsights_gold"
```

### Issue: Slow query performance

**Solution 1:** Limit data in visualizations (top 10, date filters)
**Solution 2:** Switch to SPICE import mode
**Solution 3:** Add partitioning to fact table (already partitioned by date_key)

---

## Next Steps

1. ✅ **Dataset Ready** — QuickSight can query Gold zone
2. ⏸️ **Create Visualizations** — Follow manual steps above (~15 minutes)
3. ⏸️ **Publish Dashboard** — Share with team
4. ⏸️ **Schedule Refreshes** (if using SPICE) — Daily at 06:00 ET
5. ⏸️ **Grant Access** — Add team members as Viewers

---

## Documentation References

| Document | Purpose |
|----------|---------|
| **QUICKSIGHT_DEPLOYED.md** | This file — simplified deployment |
| **QUICKSIGHT_SETUP_GUIDE.md** | Original complex setup guide |
| **PIPELINE_COMPLETE.md** | Full ETL pipeline summary |
| **TROUBLESHOOTING.md** | All pipeline issues & resolutions |

---

## Contact & Support

**QuickSight Console:**
```
https://us-east-1.quicksight.aws.amazon.com/sn/start
```

**Dataset ARN:**
```
arn:aws:quicksight:us-east-1:123456789012:dataset/finsights-fact-simple
```

**Questions?**
- QuickSight Docs: https://docs.aws.amazon.com/quicksight/
- AWS Support: Open ticket in Console

---

**Status:** ✅ QuickSight dataset deployed, ready for manual visualization creation
**Last Updated:** March 16, 2026 at 15:40 EST
