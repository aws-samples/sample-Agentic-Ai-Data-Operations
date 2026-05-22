# Reference Workload

Hierarchical entity classifications (sample is GICS only). PK includes
`classification_system` so future systems (ICB, NAICS) can land in the same
table without schema change.

## Source

- **Type**: S3 (CSV)
- **Location**: `s3://{data_lake_bucket}/raw/reference/classifications/`
- **Frequency**: Ad-hoc (manual upload). DAG `schedule=None`.
- **Owner**: reference-data-team

## Pipeline

```
S3 Sensor -> Bronze (raw CSV -> Parquet, immutable) -> Silver (Iceberg) -> Quality Gate
```

## Phase 1 Decisions (HUMAN-PROVIDED)

| Decision | Value |
|---|---|
| Zone scope | Bronze + Silver |
| PII | None |
| Silver PK | `(entity_id, classification_system)` |
| Dedup | Latest wins on `ingestion_ts` |
| Silver refresh | Full overwrite |
| GICS-style numeric codes | Critical (`^[0-9]{2,8}$` on sector/industry_group/industry codes) |
| GICS hierarchy (codes nest) | Warning |
| FK to entity_resolved | Warning |

## Silver Schema

| Column | Type | Nullable |
|---|---|---|
| `entity_id` | string | NOT NULL |
| `classification_system` | string | NOT NULL |
| `sector_code`, `sector_name` | string | NOT NULL |
| `industry_group_code`, `industry_group_name` | string | NOT NULL |
| `industry_code`, `industry_name` | string | NOT NULL |
| `ingestion_ts` | timestamp | yes |

## References

- Tool Selection: `TOOL_ROUTING.md`
- Joins to: [`entity_resolved`](../entity_resolved/README.md)
