# Estimates Ratings Workload

Sell-side consensus analyst ratings and 12-month target prices by entity and date.

## Source

- **Type**: S3 (CSV)
- **Location**: `s3://{data_lake_bucket}/raw/estimates/ratings/`
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
| Silver | Apache Iceberg on S3 Tables (partitioned by `months(rating_date)`) | >= 80%, no critical failures |

## Phase 1 Decisions (HUMAN-PROVIDED)

| Decision | Value |
|---|---|
| Zone scope | Bronze + Silver |
| PII | None |
| Silver PK | `(entity_id, rating_date)` |
| Dedup | Latest wins on `ingestion_ts` |
| Silver refresh | Full overwrite |
| Silver quality threshold | >= 0.80 |
| `target_price_low <= mean <= high` | Critical |
| `buy_count + hold_count + sell_count >= 1` | Critical |
| `consensus_rating` vocabulary | Warning |
| FK to entity_resolved | Warning |

## Silver Schema

| Column | Type | Nullable |
|---|---|---|
| `entity_id` | string | NOT NULL |
| `rating_date` | date | NOT NULL |
| `consensus_rating` | string | NOT NULL |
| `buy_count`, `hold_count`, `sell_count` | int | yes |
| `target_price_mean`, `target_price_high`, `target_price_low` | double | yes |
| `currency` | string | yes |
| `ingestion_ts` | timestamp | yes |

## References

- Tool Selection: `TOOL_ROUTING.md`
- Parent grouping: [`workloads/estimates/`](../estimates/README.md)
