# Fundamentals Cash Flow Workload

Annual cash flow line items by entity and fiscal period (operating CF, capex,
FCF, dividends, buybacks). Joins to `entity_resolved` via `entity_id`.

## Source

- **Type**: S3 (CSV)
- **Location**: `s3://{data_lake_bucket}/raw/fundamentals/cash_flow/`
- **Frequency**: Ad-hoc (manual upload). DAG `schedule=None`.
- **Owner**: fundamentals-data-team

## Pipeline

```
S3 Sensor -> Bronze (raw CSV -> Parquet, immutable) -> Silver (Iceberg) -> Quality Gate
```

## Phase 1 Decisions (HUMAN-PROVIDED)

| Decision | Value |
|---|---|
| Zone scope | Bronze + Silver |
| PII | None |
| Silver PK | `(entity_id, fiscal_period_id)` |
| Dedup | Latest wins on `ingestion_ts` |
| Period grain | Annual only (sample) |
| Silver refresh | Full overwrite |
| FCF identity (0.5% tol) | Critical |
| FK to entity_resolved | Warning |

## Silver Schema

| Column | Type | Nullable |
|---|---|---|
| `entity_id` | string | NOT NULL |
| `fiscal_period_id` | string | NOT NULL |
| `fiscal_year` | int | NOT NULL |
| `operating_cash_flow`, `capital_expenditure`, `free_cash_flow`, `dividends_paid`, `share_buybacks` | double | yes |
| `currency` | string | NOT NULL |
| `value_usd_fcf` | double | yes |
| `load_timestamp`, `ingestion_ts` | timestamp | yes |

## References

- Tool Selection: `TOOL_ROUTING.md`
- Parent grouping: [`workloads/fundamentals/`](../fundamentals/README.md)
