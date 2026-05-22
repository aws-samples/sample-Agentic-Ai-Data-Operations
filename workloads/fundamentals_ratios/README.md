# Fundamentals Ratios Workload

Annual financial ratios (PE, PB, EV/EBITDA, ROE) by entity and fiscal period.
Joins to `entity_resolved` via `entity_id`.

## Source

- **Type**: S3 (CSV)
- **Location**: `s3://{data_lake_bucket}/raw/fundamentals/ratios/`
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
| Period grain | Annual only |
| Silver refresh | Full overwrite |
| 100%-null cols dropped | `roa`, `debt_to_equity`, `current_ratio`, `load_timestamp` |
| `pe_ratio ∈ [-1000, 1000]` | Warning |
| FK to entity_resolved | Warning |

## Silver Schema

| Column | Type | Nullable |
|---|---|---|
| `entity_id` | string | NOT NULL |
| `fiscal_period_id` | string | NOT NULL |
| `fiscal_year` | int | NOT NULL |
| `pe_ratio`, `pb_ratio`, `ev_ebitda`, `roe` | double | yes |
| `ingestion_ts` | timestamp | yes |

Source columns dropped in Silver: `roa`, `debt_to_equity`, `current_ratio`,
`load_timestamp` (all 100% null in current sample).

## References

- Tool Selection: `TOOL_ROUTING.md`
- Parent grouping: [`workloads/fundamentals/`](../fundamentals/README.md)
