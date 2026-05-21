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
4. **Transformations (MANDATORY — NEVER SKIP)** — derived columns, business calculations, joins, renames? Even if you can infer type casts from the schema, you MUST ask the user about additional transformations beyond casting and dedup. Present what you auto-discovered (type casts, dedup, PII masking) and ask: "Beyond these, do you want any derived columns, calculations, or custom transforms?"
5. **Refresh** — incremental or full refresh?

Skip (auto-discover): current Bronze schema, column types, null rates
NEVER skip: Transformations (item 4) — always ask even if you think there are none

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

## Ontology Collection (MANDATORY — ask for ALL zones)

After zone-specific questions are answered, ALWAYS ask about ontology enrichment. This is **never skipped** regardless of zone.

Present this as an opt-in choice with a visual summary:

```
┌─────────────────────────────────────────────────────────┐
│  ONTOLOGY ENRICHMENT (Optional — but you must ask)      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  The Ontology Agent can enrich your workload with:      │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────┐  │
│  │  OWL Classes │───>│  R2RML Maps  │───>│  Semantic│  │
│  │  (concepts)  │    │  (wiring)    │    │  Layer   │  │
│  └──────────────┘    └──────────────┘    └──────────┘  │
│                                                         │
│  Benefits:                                              │
│  • Business terms linked to physical columns            │
│  • Relationships between entities discovered            │
│  • NL→SQL enabled via AWS Semantic Layer                │
│  • SageMaker Catalog custom metadata populated          │
│                                                         │
│  Cost: Adds ~2 min to pipeline build (one-time)         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Ask: "Would you like the Ontology Agent to generate semantic layer artifacts (OWL + R2RML) for this workload? This enables business term search and NL→SQL in downstream tools."

Options:
- **Yes** → Ontology Agent runs after Gold build, produces `config/ontology.ttl` + `config/mappings.ttl`
- **No** → Skip ontology, can be added later via `/ontology` command

Record the answer in the checklist. Do NOT assume "no" — always ask.

### If User Says YES to Ontology — MANDATORY Follow-Up Questions

When the user opts in to ontology enrichment, you MUST ask these confirmation questions BEFORE generating `semantic.yaml`. Do NOT auto-derive entities, relationships, or business terms without user confirmation.

**Step 1: Present auto-discovered entities and ask for confirmation**

```
┌─────────────────────────────────────────────────────────────┐
│  DISCOVERED ENTITIES (from your schema)                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  I found these potential business entities:                 │
│                                                             │
│  ┌─────────┐     ┌──────────┐     ┌─────────┐             │
│  │  Entity │     │  Entity  │     │  Entity │             │
│  │  Name   │     │  Name    │     │  Name   │             │
│  │ (N cols)│     │ (N cols) │     │ (N cols)│             │
│  └─────────┘     └──────────┘     └─────────┘             │
│                                                             │
│  Each entity becomes an OWL Class with properties.          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Ask:
1. **Entities** — "I identified these entities from your schema: [list]. Are these correct? Should any be added, removed, or renamed?"
2. **Entity types** — "Which is the fact table (measures/events) and which are dimensions (descriptive attributes)?"

**Step 2: Ask about relationships**

Ask:
3. **Relationships** — "I see these potential relationships: [Claim → Member via member_id, etc.]. Are these correct? Any missing relationships?"
4. **Cardinality** — "Are these 1:many or many:many?" (important for R2RML join generation)

**Step 3: Ask about business terms**

Ask:
5. **Business terms** — "What are the key business terms your team uses for this data? Examples: 'Loss Ratio', 'Clean Claim Rate', 'Days to Adjudicate'. These become searchable in the semantic layer."
6. **KPI definitions** — "For each term, what's the formula or definition?"

**NEVER do these with ontology:**
- NEVER auto-generate business terms from column names alone
- NEVER assume relationships without user confirmation
- NEVER decide entity boundaries (what is a separate entity vs. a column group) without asking
- NEVER skip these questions because "the schema is obvious"

Present findings, then ask. The user's domain expertise determines the ontology — not the column names.
