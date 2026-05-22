# Estimates Sales NTM Workload

NTM (next-twelve-month) consensus sales/revenue estimates by entity. Schema is
multi-metric ready: PK includes `metric`, so the same Silver table can hold
future metrics (FE_EBITDA_NTM, etc.).

## Source

- **Type**: S3 (CSV)
- **Location**: `s3://{data_lake_bucket}/raw/estimates/sales_ntm/`
- **Frequency**: Ad-hoc (manual upload). DAG `schedule=None`.
- **Owner**: estimates-data-team

## Pipeline

```
S3 Sensor -> Bronze (raw CSV -> Parquet, immutable) -> Silver (Iceberg) -> Quality Gate
```

## Data Zones

| Zone | Format | Quality Gate |
|------|--------|--------------|
| Bronze | Parquet (partitioned by `ingestion_date`) | None |
| Silver | Apache Iceberg on S3 Tables (partitioned by `metric`, `months(estimate_date)`) | >= 80%, no critical failures |

## Phase 1 Decisions (HUMAN-PROVIDED)

| Decision | Value |
|---|---|
| Zone scope | Bronze + Silver |
| PII | None |
| Silver PK | `(entity_id, estimate_date, metric)` |
| Dedup | Latest wins on `ingestion_ts` |
| Silver refresh | Full overwrite |
| Currency strategy | Keep both `value` (native) and `value_usd` (canonical) |
| `value_usd >= 0` | Critical |
| FK to entity_resolved | Warning |

## Silver Schema

| Column | Type | Nullable |
|---|---|---|
| `entity_id` | string | NOT NULL |
| `estimate_date` | date | NOT NULL |
| `metric` | string | NOT NULL |
| `value` | double | yes |
| `currency` | string | NOT NULL |
| `value_usd` | double | NOT NULL |
| `num_analysts` | int | yes |
| `source` | string | yes |
| `load_timestamp` | timestamp | yes |
| `ingestion_ts` | timestamp | yes |

## References

- Tool Selection: `TOOL_ROUTING.md`
- Parent grouping: [`workloads/estimates/`](../estimates/README.md)
