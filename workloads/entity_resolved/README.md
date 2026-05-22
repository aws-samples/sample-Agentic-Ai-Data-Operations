# Entity Resolved Workload

Canonical multi-region public-company entity master. Acts as the join key
across pricing, fundamentals, estimates, ownership, and other equity
workloads. Identifiers: `entity_id` (`{TICKER}-{COUNTRY}`), `ticker`, `isin`,
`cusip`, `aliases[]`.

## Source

- **Type**: S3 (CSV)
- **Location**: `s3://{data_lake_bucket}/raw/reference/entity_resolved/`
- **Frequency**: Ad-hoc (manual upload). DAG `schedule=None`.
- **Owner**: reference-data-team

## Pipeline

```
S3 Sensor -> Bronze (raw CSV -> Parquet, immutable) -> Silver (Iceberg, cleansed) -> Quality Gate
```

No Gold zone in this onboarding (Phase 1 scope: Bronze + Silver only).

## Data Zones

| Zone | Format | Quality Gate | Key Feature |
|------|--------|--------------|-------------|
| Bronze | Parquet (partitioned by `ingestion_date`) | None | Immutable, raw-source-preserved |
| Silver | Apache Iceberg on S3 Tables | >= 80%, no critical failures | Latest-wins dedup on `entity_id`, `aliases` exploded to `array<string>` |

## Phase 1 Decisions (HUMAN-PROVIDED)

| Decision | Value |
|---|---|
| Zone scope | Bronze + Silver |
| PII / compliance | None (public reference data) |
| Ingestion | Manual S3 upload, ad-hoc |
| Bronze retention | Keep all versions indefinitely (S3 versioning on) |
| Silver primary key | `entity_id` |
| Dedup strategy | Latest wins on `entity_id`, ordered by `ingestion_ts` |
| Null handling | Drop `sedol` (100% null in source); keep `cusip` nullable |
| `aliases` shape | Pipe-delimited string -> `array<string>` |
| Silver refresh | Full overwrite each run |
| Silver quality threshold | >= 0.80 (default) |
| Schedule | Manual trigger only |
| Business rules | `fiscal_year_end_month` in [1,12] (critical), ISIN format (warning), `country` ISO 3166-1 alpha-2 (critical) |

## Silver Schema

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `entity_id` | string | NOT NULL | PK, unique |
| `entity_name` | string | NOT NULL | |
| `ticker` | string | NOT NULL | |
| `aliases` | array&lt;string&gt; | yes | Split from pipe-delimited source |
| `isin` | string | yes | Format `^[A-Z0-9]{12}$` (warning if invalid) |
| `cusip` | string | yes | Non-US/CA entities lack one |
| `exchange` | string | yes | |
| `country` | string | NOT NULL | ISO 3166-1 alpha-2 |
| `sector` | string | yes | |
| `industry` | string | yes | |
| `fiscal_year_end_month` | int | yes | Must be in [1,12] |
| `ingestion_ts` | timestamp | yes | Set by Silver transform |

Source columns dropped in Silver: `sedol` (100% null in current sample).

## Tool Routing Decisions

| Phase | Intent | Tool | MCP Server | Notes |
|---|---|---|---|---|
| 3 | Discover schema | `glue-crawler` | glue-athena (REQUIRED) | Source is S3 CSV |
| 3 | Profile data | `athena-tablesample` | glue-athena (REQUIRED) | 5% sample |
| 3 | Detect PII | `pii-detection` | pii-detection (WARN) | Audit-only; no PII expected |
| 4 | Bronze ingest | `s3-copy-sync` | core (WARN) | S3 -> S3, no transforms |
| 4 | Silver transform | `glue-etl-iceberg-silver` | glue-athena (REQUIRED) | Clean + dedup + Iceberg |
| 4 | Quality check | `glue-data-quality` | glue-athena (REQUIRED) | DQDL rules |
| 5 | Verify deploy | `redshift-query-verify` | redshift (WARN) | Confirm tables queryable |
| 5 | Audit trail | `cloudtrail-lookup` | cloudtrail (WARN) | Verify ops logged |

## Logging

- Every Glue script wires `StructuredLogger` with `run_id` from Airflow.
- DAG passes `{{ run_id }}` as `--run_id` to all script tasks.
- `logs/` collects `trace_events.jsonl` per run (created at runtime by AgentTracer).

## References

- Tool Selection: `TOOL_ROUTING.md`
- MCP Guardrails: `MCP_GUARDRAILS.md`
- Agent Skills: `SKILLS.md`
