# Employee Attendance Workload

Daily employee attendance records — check-in/out times, hours worked, status.

## Source

- **Type**: S3 (CSV)
- **Location**: `s3://{data_lake_bucket}/raw/hr/attendance/`
- **Frequency**: Daily batch (cron: `0 3 * * *`)
- **Owner**: hr-analytics-team

## Pipeline

```
S3 Sensor → Bronze (raw CSV → Parquet) → Silver (Iceberg, cleaned) → Gold (Star Schema)
```

## Data Zones

| Zone | Format | Quality Gate | Key Feature |
|------|--------|-------------|-------------|
| Bronze | Parquet (partitioned by ingestion_date) | None | Immutable, raw |
| Silver | Apache Iceberg on S3 Tables | >= 80% | Deduplicated, typed, validated |
| Gold | Apache Iceberg (star schema) | >= 95% | fact_attendance + dim_employee + dim_location |

## PII Columns

| Column | PII Type | Sensitivity | Action |
|--------|----------|-------------|--------|
| `full_name` | NAME | HIGH | Mask in logs, LF-Tag restricted |
| `email` | EMAIL | HIGH | Mask in logs, LF-Tag restricted |

## Tool Routing Decisions

| Phase | Intent | Tool Selected | MCP Server | Reason |
|-------|--------|---------------|------------|--------|
| 2 | Check source exists | `local-file-scan` | None | Source is S3, check workloads/ locally |
| 2 | Verify IAM | `iam-simulate` | iam (REQUIRED) | Simulate s3:GetObject on source |
| 3 | Discover schema | `glue-crawler` | glue-athena (REQUIRED) | Source is S3 CSV |
| 3 | Profile data | `athena-tablesample` | glue-athena (REQUIRED) | Source in S3, 5% sample |
| 3 | Detect PII | `pii-detection` | pii-detection (WARN) | AI-driven name+content scan |
| 4 | Bronze ingest | `s3-copy-sync` | core (WARN) | S3→S3, no transforms |
| 4 | Silver transform | `glue-etl-iceberg-silver` | glue-athena (REQUIRED) | Clean + dedup + Iceberg |
| 4 | Quality check | `glue-data-quality` | glue-athena (REQUIRED) | DQDL rules |
| 4 | Gold transform | `glue-etl-iceberg-gold` | glue-athena (REQUIRED) | Star schema, SCD2 |
| 5 | Grant access | `lake-formation-grant` | lakeformation (REQUIRED) | PII column restriction |
| 5 | Verify deploy | `redshift-query-verify` | redshift (WARN) | Confirm tables queryable |
| 5 | Audit trail | `cloudtrail-lookup` | cloudtrail (WARN) | Verify ops logged |

## Gold Schema (Star)

Decision path (TOOL_ROUTING.md Step 5):
- Query latency: Seconds → Iceberg with partition pruning
- Data size: < 1 GB → could be flat, but dashboards need star schema
- Read pattern: Dashboards → star schema chosen

## References

- Tool Selection: `TOOL_ROUTING.md`
- MCP Guardrails: `MCP_GUARDRAILS.md`
- Agent Skills: `SKILLS.md`
