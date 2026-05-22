# Supplier Chain Data Workload

Buyer-supplier relationships, supply concentration, and contract values.
**Contains PII** (`contact_email`, `supplier_address`) — protected via Lake
Formation LF-Tags. Joins to `entity_resolved` via `buyer_ticker -> ticker`
(warning-level FK; ticker is not unique across countries).

## Source

- **Type**: S3 (CSV)
- **Location**: `s3://{data_lake_bucket}/raw/supplier_chain_data/`
- **Frequency**: Ad-hoc (manual upload). DAG `schedule=None`.
- **Owner**: supply-chain-team

## Pipeline

```
S3 Sensor -> Bronze (raw CSV -> Parquet, immutable)
          -> Silver (Iceberg, with quarantine for invalid rows)
          -> Quality Gate
          -> PII Tagging (Lake Formation)
```

## Phase 1 Decisions (HUMAN-PROVIDED)

| Decision | Value |
|---|---|
| Zone scope | Bronze + Silver |
| PII | `contact_email` (EMAIL/HIGH), `supplier_address` (ADDRESS/HIGH) — LF-Tag + mask in logs |
| Silver PK | `(buyer_ticker, supplier_ticker, effective_date, product_category)` |
| Dedup | Latest wins on `ingestion_ts` |
| Silver refresh | Full overwrite |
| `supply_concentration_pct ∈ [0, 100]` | Critical (also enforced as quarantine in transform) |
| `contract_value_usd >= 0` | Critical |
| Invalid `effective_date` | Quarantine |
| Null `supplier_ticker` | Quarantine |
| FK to entity_resolved (buyer_ticker -> ticker) | Warning |

## Known Source Data Issues (handled via quarantine)

| Issue | Sample row | Resolution |
|---|---|---|
| Invalid date `2024-13-45` | row 5149 | `to_date()` returns null → quarantine |
| `supply_concentration_pct = 143.51` | row 5150 | Out of [0,100] → quarantine |
| Negative concentration `-21.7` | row 1 | Out of [0,100] → quarantine |
| Null `supplier_ticker`/`supplier_name` | row 7 | Quarantine |
| Null `supplier_address`/`contact_email` | rows 7, 5151 | Allowed; warning on email format if non-null |

## Silver Schema

| Column | Type | Nullable | PII |
|---|---|---|---|
| `buyer_name` | string | yes | |
| `buyer_ticker` | string | NOT NULL | |
| `supplier_name` | string | yes | |
| `supplier_ticker` | string | NOT NULL | |
| `relationship_type` | string | NOT NULL | |
| `supply_concentration_pct` | double | yes | |
| `product_category` | string | NOT NULL | |
| `effective_date` | date | NOT NULL | |
| `contract_value_usd` | double | yes | |
| `supplier_address` | string | yes | **ADDRESS / HIGH** |
| `contact_email` | string | yes | **EMAIL / HIGH** |
| `ingestion_ts` | timestamp | yes | |

## Lake Formation LF-Tags (applied post-deployment)

- `PII_Classification = CONTAINS_PII` (table-level)
- `PII_Type = [EMAIL, ADDRESS]` (column-level on contact_email / supplier_address)
- `Data_Sensitivity = HIGH` (column-level on contact_email / supplier_address)

## References

- Tool Selection: `TOOL_ROUTING.md`
- PII tooling: `shared/utils/pii_detection_and_tagging.py`
- Joins to: [`entity_resolved`](../entity_resolved/README.md)
