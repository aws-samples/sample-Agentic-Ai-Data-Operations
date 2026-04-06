---
name: Source facts
description: S3 CSV source, 3 tables (stocks, portfolios, positions), SOX-compliant
type: project
---

## Source Overview

- **Type**: S3 CSV files
- **Path pattern**: `s3://data-onboarding-landing-.../financial_portfolios/`
- **Partition**: YYYY-MM-DD (daily)
- **Frequency**: Daily, expected arrival 09:00 ET

## Tables and Primary Keys

| Table | PK | Expected Rows | Description |
|---|---|---|---|
| stocks | ticker | 50 | Reference data for publicly traded stocks |
| portfolios | portfolio_id | 15 | Investment portfolios managed by the firm |
| positions | position_id | 138 | Current holdings across all portfolios |

## Foreign Key Relationships

- `positions.portfolio_id` -> `portfolios.portfolio_id` (N:1)
- `positions.ticker` -> `stocks.ticker` (N:1)

## Star Schema Design

- **Fact table**: positions (measures: shares, cost_basis, market_value, unrealized_gain_loss, weight_pct)
- **Dimension tables**: stocks (sector, industry, exchange), portfolios (manager, strategy, risk_level)
- Use case: Reporting & Dashboards

## Compliance

- **SOX** (Sarbanes-Oxley Act) — financial audit trails required
- **Retention**: 7 years
- **KMS key**: alias/sox-compliance-key
- **Audit recipients**: compliance@company.com, audit@company.com
