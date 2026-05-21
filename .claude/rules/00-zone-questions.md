# Zone-Specific Discovery Questions

When the user mentions Bronze/Silver/Gold work, identify the zone from their prompt and ask TARGETED questions for that zone. Use `AskUserQuestion` tool when possible.

## Protocol

1. **Identify the zone** from their prompt
2. **Auto-discover** what you can (schema, format, data profile via Athena/Glue)
3. **Present findings** — "I found CSV with 12 columns, 3% nulls in email..."
4. **Ask zone-specific questions** below (skip what you auto-discovered)
5. **Wait for answers** before generating code

## Bronze Questions (Raw Ingestion)

Trigger: "onboard", "ingest", "S3", "raw data", "Bronze", "new dataset"

Ask:
1. **Source & Access** — S3 path, IAM role/credentials, KMS requirements
2. **Ingestion Pattern** — batch (daily/hourly) or streaming? One-time or recurring?
3. **Retention** — how long to keep raw data? Full archive needed?

Skip (auto-discover): file format, schema, compression, partitioning

## Silver Questions (Cleansing & Conforming)

Trigger: "clean", "deduplicate", "Silver", "conform", "transform Bronze"

Ask:
1. **Uniqueness** — what defines a unique record (PK)? How to handle duplicates?
2. **Null handling** — acceptable null thresholds? Quarantine or drop bad records?
3. **Business logic** — SCD Type 1 or 2? Late-arriving data? Entity matching?
4. **Transformations** — standardizations, derived columns, joins?
5. **Refresh** — incremental or full refresh?

Skip (auto-discover): current Bronze schema, column types, null rates

## Gold Questions (Business Analytics)

Trigger: "dashboard", "reporting", "Gold", "KPIs", "analytics", "star schema"

Ask:
1. **Business outcome** — what questions should this answer? Who consumes it?
2. **Metrics** — what KPIs? What aggregation grain (daily, monthly, by region)?
3. **Schema** — star schema (fact + dims) or flat denormalized?
4. **Freshness** — SLA for data freshness? Query concurrency needs?
5. **Tool** — which BI tool queries this (Athena, Tableau, QuickSight)?

Skip (auto-discover): Silver schema, available dimensions, row counts

## Multi-Zone Requests

If user says "onboard from Bronze through Gold" — ask questions for ALL zones, grouped by zone. Present Bronze questions first, then Silver, then Gold. Do not ask Gold questions until Bronze+Silver answers are confirmed.

## What to Auto-Discover Before Asking

```
- File format (CSV, Parquet, JSON)
- Schema (column names, types)
- Row count and file sizes
- Null percentages per column
- Distinct value counts (for potential PKs)
- Partition patterns in S3 prefix
- Sample rows (5 rows)
```

Present findings, then ask ONLY what you couldn't discover. This reduces questions by ~60%.
