# Fundamentals Balance Sheet Workload

Annual balance sheet line items by entity and fiscal period (assets,
liabilities, equity, cash, debt). Joins to `entity_resolved` via `entity_id`.

## Source

- **Type**: S3 (CSV)
- **Location**: `s3://{data_lake_bucket}/raw/fundamentals/balance_sheet/`
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
| `total_assets > 0` | Critical |
| `value_usd_total_assets > 0` | Critical |
| Accounting identity (0.5% tol) | Critical |
| FK to entity_resolved | Warning |

## Silver Schema

| Column | Type | Nullable |
|---|---|---|
| `entity_id` | string | NOT NULL |
| `fiscal_period_id` | string | NOT NULL |
| `fiscal_year` | int | NOT NULL |
| `total_assets` | double | NOT NULL |
| `total_liabilities`, `total_equity`, `cash_and_equivalents`, `total_debt` | double | yes |
| `currency` | string | NOT NULL |
| `value_usd_total_assets` | double | NOT NULL |
| `ingestion_ts` | timestamp | yes |

## References

- Tool Selection: `TOOL_ROUTING.md`
- Parent grouping: [`workloads/fundamentals/`](../fundamentals/README.md)
