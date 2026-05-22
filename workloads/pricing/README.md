# Pricing Workload

Daily equity pricing (close, volume, market cap) by entity. Joins to
`entity_resolved` via `entity_id`.

## Source

- **Type**: S3 (CSV)
- **Location**: `s3://{data_lake_bucket}/raw/pricing/`
- **Frequency**: Ad-hoc (manual upload). DAG `schedule=None`.
- **Owner**: pricing-data-team

## Pipeline

```
S3 Sensor -> Bronze (raw CSV -> Parquet, immutable) -> Silver (Iceberg) -> Quality Gate
```

## Phase 1 Decisions (HUMAN-PROVIDED)

| Decision | Value |
|---|---|
| Zone scope | Bronze + Silver |
| PII | None |
| Silver PK | `(entity_id, price_date)` |
| Dedup | Latest wins on `ingestion_ts` |
| Silver refresh | Full overwrite |
| `close_price > 0` | Critical |
| `volume >= 0` | Critical |
| `market_cap > 0` | Critical |
| FK to entity_resolved | Warning |

## Silver Schema

| Column | Type | Nullable |
|---|---|---|
| `entity_id` | string | NOT NULL |
| `price_date` | date | NOT NULL |
| `close_price` | double | NOT NULL |
| `volume` | bigint | yes |
| `market_cap` | double | yes |
| `currency` | string | NOT NULL |
| `ingestion_ts` | timestamp | yes |

## References

- Tool Selection: `TOOL_ROUTING.md`
- Joins to: [`entity_resolved`](../entity_resolved/README.md)
