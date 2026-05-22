# Estimates EPS Workload

Sell-side analyst EPS estimates by entity, date, and forecast horizon
(NTM, FY1, FY2). Joins to `entity_resolved` via `entity_id`.

## Source

- **Type**: S3 (CSV)
- **Location**: `s3://{data_lake_bucket}/raw/estimates/eps/`
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
| Silver | Apache Iceberg on S3 Tables (partitioned by `period_type`, `months(estimate_date)`) | >= 80%, no critical failures |

## Phase 1 Decisions (HUMAN-PROVIDED)

| Decision | Value |
|---|---|
| Zone scope | Bronze + Silver |
| PII | None |
| Ingestion | Manual S3 upload, ad-hoc |
| Bronze retention | Keep all versions indefinitely |
| Silver PK | `(entity_id, estimate_date, period_type)` |
| Dedup | Latest wins on `ingestion_ts` |
| Silver refresh | Full overwrite |
| Silver quality threshold | >= 0.80 |
| `period_type` allowed values | `{NTM, FY1, FY2}` (critical) |
| `num_analysts >= 1` | Critical |
| `eps_low <= eps_mean <= eps_high` | Warning |
| FK to entity_resolved | Warning |

## Silver Schema

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `entity_id` | string | NOT NULL | FK to `silver_entity_resolved` (warning) |
| `estimate_date` | date | NOT NULL | |
| `period_type` | string | NOT NULL | NTM/FY1/FY2 |
| `eps_mean` | double | NOT NULL | |
| `eps_high` | double | yes | |
| `eps_low` | double | yes | |
| `num_analysts` | int | yes | Must be >= 1 (critical) |
| `currency` | string | yes | ISO 4217 (warning) |
| `ingestion_ts` | timestamp | yes | Set by Silver transform |

## References

- Tool Selection: `TOOL_ROUTING.md`
- Parent grouping: [`workloads/estimates/`](../estimates/README.md)
