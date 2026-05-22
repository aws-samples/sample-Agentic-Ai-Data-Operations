# Estimates (parent grouping)

Sell-side analyst estimates. Three sibling workloads share the source domain
but have distinct grains and PKs, so they are split:

| Workload | Grain | Source file |
|---|---|---|
| [`estimates_eps`](../estimates_eps/README.md) | One row per (entity_id, estimate_date, period_type) | `fe_eps.csv` |
| [`estimates_ratings`](../estimates_ratings/README.md) | One row per (entity_id, rating_date) | `fe_ratings.csv` |
| [`estimates_sales_ntm`](../estimates_sales_ntm/README.md) | One row per (entity_id, estimate_date, metric) | `fe_sales_ntm.csv` |

All three:
- Bronze + Silver only (no Gold yet)
- Manual trigger, full overwrite each run
- Silver quality gate >= 0.80, no critical failures
- No PII (sell-side aggregates)
- Reference [`entity_resolved`](../entity_resolved/README.md) via `entity_id`; FK enforced as a warning rule.
