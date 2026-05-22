# Fundamentals Sales Workload

Reported sales/revenue (annual + quarterly) by entity, fiscal period, and
metric. Multi-metric ready: `metric` is part of the PK so future metrics
(e.g., `FF_GROSS_PROFIT`) can land in the same Silver table.

## Source

- **Type**: S3 (CSV)
- **Location**: `s3://{data_lake_bucket}/raw/fundamentals/sales/`
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
| Silver PK | `(entity_id, fiscal_period_id, metric)` |
| Dedup | Latest wins on `ingestion_ts` |
| Period grain | Annual + quarterly |
| Silver refresh | Full overwrite |
| `fiscal_period ∈ {FY, Q1, Q2, Q3, Q4}` | Critical |
| `value_usd >= 0` | Critical |
| FK to entity_resolved | Warning |

## Silver Schema

| Column | Type | Nullable |
|---|---|---|
| `entity_id` | string | NOT NULL |
| `fiscal_period_id` | string | NOT NULL |
| `fiscal_year` | int | NOT NULL |
| `fiscal_period` | string | NOT NULL |
| `period_end_date` | date | yes |
| `metric` | string | NOT NULL |
| `value` | double | yes |
| `currency` | string | NOT NULL |
| `value_usd` | double | NOT NULL |
| `source` | string | yes |
| `load_timestamp`, `ingestion_ts` | timestamp | yes |

## References

- Tool Selection: `TOOL_ROUTING.md`
- Parent grouping: [`workloads/fundamentals/`](../fundamentals/README.md)
