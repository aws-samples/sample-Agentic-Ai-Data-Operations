# Fundamentals (parent grouping)

Sourced from a fundamentals data vendor. Four sibling workloads share the
source domain but have distinct grains and PKs, so they are split:

| Workload | Grain | Source file |
|---|---|---|
| [`fundamentals_balance_sheet`](../fundamentals_balance_sheet/README.md) | One row per (entity_id, fiscal_period_id) — annual | `ff_balance_sheet.csv` |
| [`fundamentals_cash_flow`](../fundamentals_cash_flow/README.md) | One row per (entity_id, fiscal_period_id) — annual | `ff_cash_flow.csv` |
| [`fundamentals_ratios`](../fundamentals_ratios/README.md) | One row per (entity_id, fiscal_period_id) — annual | `ff_ratios.csv` |
| [`fundamentals_sales`](../fundamentals_sales/README.md) | One row per (entity_id, fiscal_period_id, metric) — annual + quarterly | `ff_sales.csv` |

All four:
- Bronze + Silver only (no Gold yet)
- Manual trigger, full overwrite each run
- Silver quality gate >= 0.80, no critical failures
- No PII (corporate financials)
- Reference [`entity_resolved`](../entity_resolved/README.md) via `entity_id`; FK enforced as a warning rule.

Per-workload critical rules of note:
- BS: total_assets ≈ total_liabilities + total_equity (0.5% tolerance)
- CF: free_cash_flow ≈ operating_cash_flow − capital_expenditure (0.5% tolerance)
- Ratios: drops 100%-null source columns (roa, debt_to_equity, current_ratio, load_timestamp) in Silver
- Sales: fiscal_period ∈ {FY, Q1, Q2, Q3, Q4} (critical); value_usd ≥ 0 (critical)
