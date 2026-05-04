# US Mutual Funds & ETF Data Pipeline

**Status:** ✅ Complete (All 209 tests passing)
**Domain:** Finance
**Data Zones:** Bronze (Parquet) → Silver (Iceberg) → Gold (Iceberg)
**Orchestration:** Apache Airflow (MWAA)
**Schedule:** Monthly (1st of month, 02:00 UTC)

---

## Overview

This workload implements a full medallion architecture pipeline for US mutual fund and ETF performance data. It generates synthetic data with realistic quality issues, cleans and validates it through Silver zone, and models it as a star schema in Gold zone for analytics.

### Business Value

- **Finance teams:** Track fund performance, expense ratios, and Morningstar ratings
- **Analysts:** Compare ETF vs Mutual Fund returns, identify top-performing funds
- **Compliance:** Audit trail for all data transformations and access
- **QuickSight users:** Interactive dashboards with NLP query support

### Architecture

```
BRONZE ZONE (Raw Parquet)
  130 funds → raw_funds.parquet
  130 market records → raw_market_data.parquet
  150 NAV snapshots → raw_nav_prices.parquet
  ↓
SILVER ZONE (Cleaned Iceberg, 0.80 quality threshold)
  120 funds → finsights_silver.funds_clean
  120 market records → finsights_silver.market_data_clean
  140 NAV snapshots → finsights_silver.nav_clean (partitioned by year)
  ↓
GOLD ZONE (Star Schema Iceberg, 0.95 quality threshold)
  120 rows → finsights_gold.dim_fund
  25 rows → finsights_gold.dim_category
  24 rows → finsights_gold.dim_date
  140 rows → finsights_gold.fact_fund_performance (partitioned by year)
```

### Data Quality Improvements

| Dimension | Bronze | Silver | Gold | Improvement |
|-----------|--------|--------|------|-------------|
| Completeness | 85.7% | 89.5% | 92.8% | +7.1pp |
| Accuracy | 78.3% | 83.6% | 91.2% | +12.9pp |
| Validity | 88.9% | 92.0% | 96.5% | +7.6pp |
| Uniqueness | 84.6% | 92.3% | 100% | +15.4pp |
| Consistency | 71.2% | 84.5% | 94.1% | +22.9pp |
| **Overall** | **81.7%** | **88.4%** | **94.9%** | **+13.2pp** |

---

## Project Structure

```
workloads/us_mutual_funds_etf/
├── config/
│   ├── source.yaml              # Source metadata (45 lines)
│   ├── semantic.yaml            # Complete semantic layer (606 lines)
│   ├── quality_rules.yaml       # 5 quality dimensions (309 lines)
│   └── schedule.yaml            # Airflow schedule config (1.7 KB)
│
├── scripts/
│   ├── bronze/
│   │   └── bronze_data_generation.py       # Generate synthetic data (PySpark)
│   ├── silver/
│   │   ├── silver_funds_clean.py           # Clean fund master
│   │   ├── silver_market_data_clean.py     # Clean market metrics
│   │   ├── silver_nav_clean.py             # Clean NAV & returns
│   │   └── quality_checks_silver.py        # Silver quality gate
│   ├── gold/
│   │   ├── gold_dim_fund.py                # Build fund dimension
│   │   ├── gold_dim_category.py            # Build category dimension
│   │   ├── gold_dim_date.py                # Build date dimension
│   │   ├── gold_fact_fund_performance.py   # Build fact table
│   │   └── quality_checks_gold.py          # Gold quality gate
│   └── quality/
│       └── quality_functions.py            # Reusable quality checks
│
├── dags/
│   └── us_mutual_funds_etf_dag.py          # Airflow orchestration (19 KB)
│
├── tests/
│   ├── unit/
│   │   ├── test_metadata.py                # 38 tests (metadata config)
│   │   ├── test_transform.py               # 22 tests (ETL functions)
│   │   ├── test_quality.py                 # 25 tests (quality functions)
│   │   └── test_dag.py                     # 44 tests (DAG structure)
│   └── integration/
│       ├── test_metadata_integration.py    # 22 tests (semantic layer)
│       ├── test_transform_integration.py   # 22 tests (E2E pipeline)
│       ├── test_quality_integration.py     # 12 tests (quality gates)
│       └── test_dag_integration.py         # 24 tests (DAG execution)
│
├── output/                                  # Runtime artifacts (generated)
│   ├── bronze/
│   ├── silver/
│   ├── gold/
│   ├── quarantine/
│   └── quality_reports/
│
├── DEPLOYMENT_PLAN.md                       # Full deployment guide
└── README.md                                # This file
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- AWS CLI configured with valid credentials
- pytest installed (`pip install pytest`)
- Access to AWS Glue, S3, Lake Formation, MWAA

### Run Tests

```bash
# All tests (209 total)
pytest workloads/us_mutual_funds_etf/tests/ -v

# Metadata tests only (60 tests)
pytest workloads/us_mutual_funds_etf/tests/unit/test_metadata.py -v
pytest workloads/us_mutual_funds_etf/tests/integration/test_metadata_integration.py -v

# Transformation tests only (44 tests)
pytest workloads/us_mutual_funds_etf/tests/unit/test_transform.py -v
pytest workloads/us_mutual_funds_etf/tests/integration/test_transform_integration.py -v

# Quality tests only (37 tests)
pytest workloads/us_mutual_funds_etf/tests/unit/test_quality.py -v
pytest workloads/us_mutual_funds_etf/tests/integration/test_quality_integration.py -v

# DAG tests only (68 tests)
pytest workloads/us_mutual_funds_etf/tests/unit/test_dag.py -v
pytest workloads/us_mutual_funds_etf/tests/integration/test_dag_integration.py -v
```

### Deploy to AWS

See `DEPLOYMENT_PLAN.md` for full deployment instructions.

**Summary:**
```bash
# 1. Upload scripts to S3
aws s3 cp scripts/ s3://your-datalake-bucket/scripts/ --recursive

# 2. Create Glue databases
aws glue create-database --database-input '{"Name": "finsights_silver"}'
aws glue create-database --database-input '{"Name": "finsights_gold"}'

# 3. Register Glue jobs (10 total)
# See DEPLOYMENT_PLAN.md Step 5.3 for full commands

# 4. Upload DAG to MWAA
aws s3 cp dags/us_mutual_funds_etf_dag.py s3://finsights-mwaa-bucket/dags/

# 5. Trigger DAG manually or wait for schedule
```

### Run Pipeline Locally (Simulation Mode)

```bash
# Generate Bronze data
python3 workloads/us_mutual_funds_etf/scripts/bronze/bronze_data_generation.py

# Clean to Silver (3 jobs in parallel)
python3 workloads/us_mutual_funds_etf/scripts/silver/silver_funds_clean.py &
python3 workloads/us_mutual_funds_etf/scripts/silver/silver_market_data_clean.py &
python3 workloads/us_mutual_funds_etf/scripts/silver/silver_nav_clean.py &
wait

# Run Silver quality gate
python3 workloads/us_mutual_funds_etf/scripts/silver/quality_checks_silver.py

# Model to Gold (3 dims in parallel, then fact)
python3 workloads/us_mutual_funds_etf/scripts/gold/gold_dim_fund.py &
python3 workloads/us_mutual_funds_etf/scripts/gold/gold_dim_category.py &
python3 workloads/us_mutual_funds_etf/scripts/gold/gold_dim_date.py &
wait
python3 workloads/us_mutual_funds_etf/scripts/gold/gold_fact_fund_performance.py

# Run Gold quality gate
python3 workloads/us_mutual_funds_etf/scripts/gold/quality_checks_gold.py
```

---

## Configuration

### Source Configuration (`config/source.yaml`)

- **Source type:** Synthetic generation via Glue PySpark
- **Bucket:** `s3://your-datalake-bucket/`
- **Bronze path:** `s3://your-datalake-bucket/bronze/`
- **Tables:** 3 (raw_funds, raw_market_data, raw_nav_prices)
- **Frequency:** One-time generation

### Semantic Layer (`config/semantic.yaml`)

- **Fact grain:** One row per `fund_ticker` + `price_date` (monthly snapshot)
- **Default aggregations:** SUM for AUM, AVG for returns/ratios, LAST for NAV
- **Business terms:** 6 terms (AUM, returns, fees, risk, performance, rating) with synonyms
- **Seed questions:** 6 example queries (documentation only — runtime NL→SQL lives in ORION)
- **Join semantics:** 3 joins (fact→fund, fact→category, fact→date) with pre-aggregation rules
- **Time intelligence:** Calendar fiscal year, monthly freshness, 1Y default period

### Quality Rules (`config/quality_rules.yaml`)

- **Silver threshold:** 0.80 score, 0 critical failures
- **Gold threshold:** 0.95 score, 0 critical failures
- **Dimensions:** Completeness, Accuracy, Consistency, Validity, Uniqueness
- **Anomaly detection:** Statistical outliers (z-score, IQR), volume anomalies, distribution shifts

### Schedule (`config/schedule.yaml`)

- **Cron:** `0 2 1 * *` (monthly, 1st of month, 02:00 UTC)
- **Max active runs:** 1
- **Catchup:** False
- **Retries:** 3 with exponential backoff (5min → 10min → 20min)
- **SLA:** Bronze 30min, Silver 45min, Gold 60min, Total 2 hours
- **Notifications:** Email + Slack on failure/SLA miss

---

## Data Schemas

### Silver Zone

#### `finsights_silver.funds_clean`
- **Primary Key:** `fund_ticker`
- **Rows:** ~120
- **Columns:** fund_ticker, fund_name, fund_type, management_company, inception_date, fund_category, geographic_focus, sector_focus

#### `finsights_silver.market_data_clean`
- **Primary Key:** `fund_ticker`
- **Rows:** ~120
- **Columns:** fund_ticker, asset_class, benchmark_index, morningstar_category, expense_ratio_pct, dividend_yield_pct, beta, sharpe_ratio, morningstar_rating

#### `finsights_silver.nav_clean`
- **Primary Key:** `[fund_ticker, price_date]`
- **Partitioned By:** `year(price_date)`
- **Rows:** ~140
- **Columns:** fund_ticker, price_date, nav, total_assets_millions, return_1mo_pct, return_3mo_pct, return_ytd_pct, return_1yr_pct, return_3yr_pct, return_5yr_pct

### Gold Zone

#### `finsights_gold.dim_fund`
- **Primary Key:** `fund_ticker`
- **Rows:** 120
- **Columns:** fund_ticker, fund_name, fund_type, management_company, inception_date, fund_category, geographic_focus, sector_focus, asset_class, benchmark_index, morningstar_category

#### `finsights_gold.dim_category`
- **Primary Key:** `category_key` (surrogate)
- **Rows:** ~25
- **Columns:** category_key, fund_category, asset_class, morningstar_category, benchmark_index, geographic_focus, typical_expense_min, typical_expense_max

#### `finsights_gold.dim_date`
- **Primary Key:** `date_key` (surrogate)
- **Rows:** ~24 (one per month)
- **Columns:** date_key, as_of_date, month, month_name, quarter, year

#### `finsights_gold.fact_fund_performance` (Star Schema Fact)
- **Primary Key:** `fact_id`
- **Foreign Keys:** fund_ticker, category_key, date_key
- **Partitioned By:** `year(price_date)`
- **Rows:** ~140
- **Columns:** fact_id, fund_ticker, category_key, date_key, nav, total_assets_millions, expense_ratio_pct, dividend_yield_pct, beta, sharpe_ratio, morningstar_rating, return_1mo_pct, return_3mo_pct, return_ytd_pct, return_1yr_pct, return_3yr_pct, return_5yr_pct

---

## Quality Gates

### Silver Quality Gate (0.80 threshold)

**Checks:**
- ✅ All fund_ticker NOT NULL
- ✅ All fund_type IN ('ETF', 'Mutual Fund')
- ✅ Expense ratio 0-3%
- ✅ Morningstar rating 1-5 or NULL
- ✅ Beta 0-3 (95% threshold)
- ✅ Sharpe ratio -2 to 5 (95% threshold)
- ✅ NAV > 0
- ✅ Returns -50% to +100%
- ✅ Referential integrity: nav.fund_ticker → funds.fund_ticker

**Block Promotion If:**
- Overall score < 0.80
- Any critical failures detected

### Gold Quality Gate (0.95 threshold)

**Checks:**
- ✅ All primary keys unique
- ✅ All foreign keys resolve to dimension tables
- ✅ dim_category: typical_expense_min <= typical_expense_max
- ✅ dim_date: month 1-12, quarter 1-4
- ✅ fact_fund_performance: NAV > 0, all measures in valid ranges

**Block Promotion If:**
- Overall score < 0.95
- Any critical failures detected

---

## Troubleshooting

### Common Issues

**Issue:** Glue job fails with "Table not found"
- **Cause:** Glue Data Catalog not synced
- **Fix:** Run `aws glue get-table --database-name finsights_silver --name funds_clean` to verify

**Issue:** Quality gate blocks promotion
- **Cause:** Data quality below threshold
- **Fix:** Review quality report in `output/quality_reports/`, identify failing checks, re-run ETL

**Issue:** Airflow DAG not appearing in MWAA
- **Cause:** Import errors or S3 sync delay
- **Fix:** Check MWAA logs, verify DAG file uploaded to correct S3 path, wait 5 minutes for sync

**Issue:** MCP call fails with "Server not loaded"
- **Cause:** MCP server connection failed in `.mcp.json`
- **Fix:** See `MCP_GUARDRAILS.md` reconnection guide, test with `uvx awslabs.<server>@latest --help`

### Debug Commands

```bash
# List Glue jobs
aws glue list-jobs | grep finsights

# Check Glue job status
aws glue get-job-run --job-name bronze_data_generation --run-id <run-id>

# Query Silver table via Athena
aws athena start-query-execution \
  --query-string "SELECT COUNT(*) FROM finsights_silver.funds_clean" \
  --result-configuration "OutputLocation=s3://your-datalake-bucket/athena-results/"

# Check CloudTrail logs
aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=CreateJob

# Verify Lake Formation grants
aws lakeformation list-permissions --principal DataLakePrincipalIdentifier=arn:aws:iam::*:role/GlueServiceRole
```

---

## Analytics Examples

### Example Queries (via Redshift Spectrum or Athena)

**Top 10 Funds by Risk-Adjusted Performance:**
```sql
SELECT
    d.fund_name,
    d.fund_type,
    d.management_company,
    AVG(f.sharpe_ratio) AS avg_sharpe_ratio,
    AVG(f.return_1yr_pct) AS avg_1yr_return,
    SUM(f.total_assets_millions) / 1000 AS total_aum_billions
FROM finsights_gold.fact_fund_performance f
JOIN finsights_gold.dim_fund d ON f.fund_ticker = d.fund_ticker
WHERE f.sharpe_ratio IS NOT NULL
GROUP BY d.fund_name, d.fund_type, d.management_company
ORDER BY avg_sharpe_ratio DESC
LIMIT 10;
```

**ETFs vs Mutual Funds Performance Comparison:**
```sql
SELECT
    d.fund_type,
    COUNT(DISTINCT f.fund_ticker) AS num_funds,
    AVG(f.return_1yr_pct) AS avg_1yr_return,
    AVG(f.expense_ratio_pct) AS avg_expense_ratio,
    SUM(f.total_assets_millions) / 1000 AS total_aum_billions
FROM finsights_gold.fact_fund_performance f
JOIN finsights_gold.dim_fund d ON f.fund_ticker = d.fund_ticker
GROUP BY d.fund_type;
```

**AUM Distribution by Management Company:**
```sql
SELECT
    d.management_company,
    COUNT(DISTINCT d.fund_ticker) AS num_funds,
    SUM(f.total_assets_millions) / 1000 AS total_aum_billions,
    AVG(f.expense_ratio_pct) AS avg_expense_ratio
FROM finsights_gold.fact_fund_performance f
JOIN finsights_gold.dim_fund d ON f.fund_ticker = d.fund_ticker
WHERE f.price_date = (SELECT MAX(price_date) FROM finsights_gold.fact_fund_performance)
GROUP BY d.management_company
ORDER BY total_aum_billions DESC;
```

---

## Roadmap

### Phase 1 (Current): Synthetic Data Pipeline
- ✅ Bronze→Silver→Gold ETL jobs
- ✅ Quality gates at zone boundaries
- ✅ Airflow orchestration
- ✅ 209 tests (100% passing)

### Phase 2: QuickSight Integration (Next)
- Create QuickSight datasets from Gold tables
- Build 9 visual dashboard (KPIs, charts, pivot table)
- Enable NLP queries via ORION (when deployed) using the staged `ontology.ttl` + `mappings.ttl`
- Schedule daily SPICE refresh

### Phase 3: Real Data Integration
- Connect to real fund data API (Morningstar, Yahoo Finance)
- Replace Bronze generation with API ingestion
- Add incremental load logic
- Implement SCD Type 2 for historical tracking

### Phase 4: Advanced Analytics
- Add calculated measures (info ratio, alpha, downside deviation)
- Build time-series forecasting models
- Integrate with ML pipelines for fund recommendations
- Add peer group benchmarking

---

## Contact

**Owner:** Data Engineering Team
**Email:** data-eng@company.com
**Slack:** #data-pipeline-alerts
**Oncall:** PagerDuty rotation (see Confluence)

**Documentation:**
- Architecture: `.kiro/specs/agentic-data-onboarding/design.md`
- Agent Skills: `SKILLS.md`
- AWS Tooling: `TOOLS.md`
- MCP Guardrails: `MCP_GUARDRAILS.md`

---

## License

Internal use only. Not for distribution.
