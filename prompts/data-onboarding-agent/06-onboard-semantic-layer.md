# 06 — SEMANTIC: Onboard Workload to Semantic Layer

> Phase 6 (optional). Add a deployed workload to the consolidated VKG ontology + R2RML mappings, with entity-aware link discovery against already-onboarded workloads.

## Purpose

After a workload is deployed (Phase 5 complete) and its Silver and/or Gold tables exist in the workload-specific Glue database (`{workload}_db`), this skill:

1. Detects which zones (Silver, Gold, or both) are deployed for the workload, asks the user which zone(s) to map into the semantic layer (default: Gold if available, else Silver)
2. Detects whether the workload spans **multiple physical tables** (e.g. `fundamentals` → `silver_fundamentals_balance_sheet`, `silver_fundamentals_cash_flow`, ...). For multi-table workloads, asks the user up-front whether to model as one unified class or per-table record classes (recommended: per-table, with shared dimension classes for any keys that span tables)
3. Profiles the chosen zone's columns and proposes column-level **descriptions** for each (using domain-aware inference from `semantic.yaml` + sample values)
4. Confirms descriptions with the user, writes them back into `workloads/{name}/config/semantic.yaml`
5. Reads each workload's `semantic.yaml` for **pre-declared `relationship:` blocks** (`target_table`, `target_column`) — these are high-confidence link candidates that bypass embedding-based discovery. Verifies each via Athena join.
6. Discovers any **remaining** candidate links via embedding similarity (entity-class + domain + description + sample-values-for-categoricals) — then verifies each candidate by querying the underlying Athena data (join match rate, fan-out check)
7. Confirms the relationships with the user
8. Emits the merged consolidated artifacts at `semantic-layer/ontology.ttl` (OWL VKG) and `semantic-layer/r2rml-mappings.ttl` (R2RML), incrementally updated each onboarding. R2RML `logicalTable` targets the zone the user selected per workload (Silver or Gold) — both zones are first-class citizens of the semantic layer.

This skill produces **artifacts only** — it does not deploy to Neptune / Ontop / OpenSearch. That is Phase 7 (`07-deploy-semantic-layer.md`).

### Bootstrap onboarding (first workload)

When `semantic-layer/ontology.ttl` does not yet exist, this is the **bootstrap onboarding**. Steps 5–7 (link discovery + Athena verification + relationship confirmation) become **no-ops** — there's nothing for the new workload to link to. The workload's classes and properties are written to a fresh ontology, and its corpus is established as the baseline against which future workloads will be matched. Document this state in `manifest.json` under the workload's `notes` field.

## Hard Scope Boundary

### You DO

1. Detect which zones (Silver, Gold, or both) are deployed for the workload — call `glue-athena` MCP `get_table` against the workload's Glue database. Note the actual layout in this repo is **per-workload Glue databases** (`{workload}_db` such as `fundamentals_db`, `entity_resolved_db`) with `silver_*` / `gold_*` table prefixes — not a centralized `fip_silver` / `fip_gold`. Ask the user which zone to anchor onto. Default: Gold if it exists; otherwise Silver. The user MAY map both zones when the Gold zone is heavily aggregated/denormalized and the Silver zone preserves grain useful for the VKG (use grain-based class names — never `Silver`/`Gold` suffixes).
2. **Detect multi-table workloads up-front.** When a workload directory implies multiple physical tables (e.g. `fundamentals` covers `silver_fundamentals_{balance_sheet,cash_flow,ratios,sales}`), ask the user whether to model as: (a) one unified class with all properties, (b) per-table record classes with shared dimension classes for join keys (recommended), or (c) hybrid (some merged, some split). Verify the actual table grain across tables (row count, distinct entity_id, distinct period count) BEFORE asking — the user's answer should be informed by data, not guessed.
3. Read the workload's existing `config/semantic.yaml` and the chosen zone's Glue schema(s) via `glue-athena` MCP `get_table`.
4. Run a 5% Athena sample (`glue-athena` MCP `start_query_execution`) on each chosen zone to capture cardinality + sample values per column.
5. Propose descriptions per column based on (existing description if any) + (column name) + (dtype) + (sample values) + (`semantic.yaml` `domain` and `business_description`) + (zone — Silver vs Gold semantics differ). Present to user for approval. **If existing descriptions are complete**, skip re-proposing and use as-is — but always offer to enrich low-cardinality dimension columns (currency codes, period codes, sector names) with `sample_values:` for embedding disambiguation.
6. Persist approved descriptions back into `workloads/{name}/config/semantic.yaml` (column-level `description:` field). Use a `zones:` sub-block on the column entry when the same logical column exists in both zones with different semantics.
7. **Read pre-declared relationships first.** Each workload's `semantic.yaml` may already contain `relationship:` blocks (`target_table`, `target_column`, `type`). These are high-confidence FK declarations from the original onboarding — verify each via Athena join (Step 9) but skip embedding-based discovery for these columns. They're the cheapest, highest-confidence links available.
8. Read the consolidated `semantic-layer/ontology.ttl` (if it exists) plus every `workloads/*/config/semantic.yaml` to build the link-candidate corpus for **remaining** columns (those without pre-declared relationships). The corpus is zone-aware — a column in Silver and a column in Gold produce two distinct embedding entries when both are mapped.
9. Generate embeddings via Bedrock Titan Embeddings v2 (`amazon.titan-embed-text-v2:0`) — one per (column, zone), with text constructed as:
   ```
   [{domain}/{zone}] {entity_class}.{column}: {description}
   {sample_values_if_categorical}
   ```
   `entity_class` is the OWL class the column maps to. `zone` is `silver` or `gold`. Sample values included only when column distinct count ≤ 50 (categorical).
10. For each new column without a pre-declared relationship, find top-K (default 5) similar columns across already-onboarded workloads via cosine similarity. Threshold: ≥ 0.82. Cross-zone matches are allowed — flag these in the user-confirmation step.
11. **Verify every candidate (pre-declared AND embedding-based) by running an Athena join sample** — count match rate on a 1000-row sample, querying each candidate against its actual zone-qualified table. Reject candidates with < 5% match rate. Flag fan-out (1:N where N > 100). For obvious shared keys (`entity_id` string in both tables), the verification IS the only evidence needed — embedding score is irrelevant if the join works.
12. Present the verified candidates to the user with match-rate evidence and source/target zone. User approves / rejects each one.
13. Emit the merged consolidated artifacts at `semantic-layer/ontology.ttl` and `semantic-layer/r2rml-mappings.ttl`. Update incrementally — preserve existing classes/maps for already-onboarded workloads. R2RML `rr:logicalTable` `rr:tableName` is `{workload}_db.silver_*` or `{workload}_db.gold_*` per the user's selection.
14. **Materialize shared dimension classes via R2RML `SELECT DISTINCT`.** When the same join key appears in multiple tables (e.g. `fiscal_period_id` across 4 fundamentals tables), pick the most-complete source table for the dimension and create a `<#{Dimension}Map>` with `rr:sqlQuery """SELECT DISTINCT col1, col2 FROM most_complete.table"""`. Other tables join to this dimension via `rr:parentTriplesMap` + `rr:joinCondition`. This is the canonical pattern for `Sector`, `Industry`, `Exchange`, `Country`, `FiscalPeriod`, etc.
15. **Polymorphic predicates are supported.** When a predicate applies to multiple record classes (e.g. `forEntity` on every record class linking to `Entity`), declare ALL its `rdfs:domain` values in the OWL TTL — multiple `rdfs:domain` triples on one property are read as a UNION (the property may apply to instances of any listed class). Note: OBQC must support union-domain semantics for this to validate correctly — see Phase 7 deploy spec.
16. **Reverse predicates require their own R2RML mapping.** Do NOT declare reverse object properties (`hasBalanceSheet`, `hasCashFlow`) unless you also write the R2RML to materialize them. Ontop only produces triples for predicates with explicit R2RML — declared-but-unmapped predicates return empty bindings at query time. Default: declare only the forward direction (record → Entity via `forEntity`); the agent traverses backwards in SPARQL: `?bs forEntity ?e`.
17. Write `semantic-layer/manifest.json` recording: workloads onboarded, ontology version, last-updated timestamp, per-workload zone mapping (and sub-table list for multi-table workloads), and per-relationship match-rate evidence (with source/target zone).

### You DO NOT

- ❌ Skip the Athena join verification — embedding similarity alone is not sufficient evidence of a real FK relationship. Even pre-declared `relationship:` blocks in `semantic.yaml` need verification.
- ❌ Generate links without entity-class context. The same `earnings` column appearing in `estimates` (analyst forecast) and `fundamentals` (as-reported) MUST embed as different classes.
- ❌ Modify the workload's Silver/Gold tables, ETL scripts, or DAGs — semantic-layer changes do not touch the data pipeline.
- ❌ Deploy to Neptune, Ontop ECS, or OpenSearch — that is Phase 7.
- ❌ Author SHACL constraints — defer to AWS Semantic Layer.
- ❌ Auto-approve relationships without user confirmation — even at 100% match rate.
- ❌ Declare reverse predicates without backing R2RML. If the ontology says `Entity hasBalanceSheet BalanceSheetRecord` but no `rr:TriplesMap` produces that triple, queries traversing it return empty.
- ❌ Use class names with `Silver` / `Gold` suffix. Zone is a deployment detail, not part of the queryable ontology vocabulary. When both zones map for one workload, distinguish by grain (`Trade` vs `DailyTradeSummary`) or function — never zone.

## When You Run

Invoked manually after Phase 5 deployment is complete and verified. Typical trigger:
> "Onboard `{workload_name}` to the semantic layer."

Preconditions:
- Workload `{name}` has passed Phase 5.9 post-deployment verification — at least one of the Silver or Gold tables exists and is queryable via Athena.
- `workloads/{name}/config/semantic.yaml` exists.

## Inputs

| Input | Source | Required |
|---|---|---|
| `workload_name` | user / orchestrator | Yes |
| `zones` | user choice: `["silver"]`, `["gold"]`, or `["silver", "gold"]` (default: `["gold"]` if Gold exists, else `["silver"]`) | Yes |
| `silver_table` | the Silver table FQN (`fip_silver.{table}`) | Required if `silver` in `zones` |
| `gold_table` | the Gold table FQN (`fip_gold.{table}`) | Required if `gold` in `zones` |
| `entity_class_name` | user-confirmed OWL class name (default: PascalCase workload name with `Record` suffix where the workload represents per-row event/measurement records, or a domain noun for entity masters — e.g. `Entity` for entity_resolved, `PriceRecord` for pricing, `EstimateRecord` for estimates). **Do not include Silver/Gold in the class name** — zone is a deployment detail, not part of the queryable ontology vocabulary. When both zones are mapped, use `rdfs:subClassOf` or distinguishing nouns based on grain (e.g. `Trade` vs `DailyTradeSummary`), not zone suffixes. | Yes |
| `existing_consolidated_ontology` | `semantic-layer/ontology.ttl` if present | No |
| `link_threshold` | cosine similarity floor for link candidates | No (default 0.82) |
| `match_rate_threshold` | min Athena join match rate to accept | No (default 0.05) |

## Workflow

### Step 1 — Detect zones + select scope

- Probe both `fip_silver.{table}` and `fip_gold.{table}` via `glue-athena` MCP `get_table`. Record which exist.
- Present the user with what was found and ask which zone(s) to onboard. Default selection:
  - Both exist → recommend Gold-only unless the user has a reason to map Silver (e.g. Silver preserves grain Gold loses).
  - Only one exists → use that one.
- Capture the `zones` input and the per-zone class name(s).

### Step 2 — Profile the chosen zone(s)

For each zone in `zones`:

- Call `glue-athena` MCP `get_table` for `fip_{zone}.{table}` → column list with dtypes + comments.
- Run an Athena 5% sample query: `SELECT * FROM fip_{zone}.{table} TABLESAMPLE BERNOULLI(5) LIMIT 5000`.
- For each column, compute: distinct count, null %, top-10 sample values, min/max for numerics + dates.
- Cross-check against `workloads/{name}/config/semantic.yaml` — note any columns missing from semantic.yaml or any drift.

Present the profile to the user grouped by zone (concise: column, dtype, distinct count, sample, existing description). When both zones are mapped, highlight column differences between Silver and Gold (added/dropped/renamed) so descriptions can be written zone-aware.

### Step 3 — Propose + confirm descriptions

For each (column, zone) lacking a description (or where the existing description is templated/generic):

1. Generate a candidate description using:
   - Column name + dtype
   - Zone (Silver = cleansed/conformed grain; Gold = curated/aggregated)
   - Domain context from `semantic.yaml` (`domain`, `business_description`)
   - Sample values
   - The entity class the column belongs to

2. Use `AskUserQuestion` (one batch per ~10 columns, grouped by zone) with the proposed description and 2–3 alternatives. User approves / edits / writes their own.

3. Write approved descriptions back into `workloads/{name}/config/semantic.yaml` under the matching column's `description:` field. When both zones are mapped and a column exists in both with different semantics, use a `zones:` sub-block:
   ```yaml
   - name: revenue
     role: measure
     zones:
       silver:
         description: "Per-transaction line-item revenue, raw."
       gold:
         description: "Daily aggregated revenue at entity grain."
   ```
   When a single zone is mapped or the description is identical across zones, keep the flat `description:` field.

**Do not infer.** If column intent is ambiguous (e.g. `value` with no other context), ask the user to provide the description outright — do not guess.

### Step 4 — Build the link-candidate corpus

1. Read the consolidated `semantic-layer/ontology.ttl` if it exists, plus every `workloads/*/config/semantic.yaml`.
2. For each (column, zone) already in the semantic layer, construct the embedding text:
   ```
   [{domain}/{zone}] {entity_class}.{column_name}: {description}
   sample values: {top_5_if_categorical_else_omitted}
   ```
   Categorical = distinct count ≤ 50.
3. Construct the same embedding text for each new (column, zone) being onboarded. A column mapped in both Silver and Gold yields two corpus entries.
4. Cache embeddings by `(entity_class, zone, column_name, content_hash)` in `semantic-layer/.embedding_cache/` so re-runs are cheap.
5. Embed via Bedrock `amazon.titan-embed-text-v2:0` (1024-dim).

### Step 5 — Discover + verify candidates

For each new (column, zone):

1. Compute cosine similarity against all existing-column embeddings (across all zones in the corpus).
2. Take the top 5 with similarity ≥ 0.82.
3. For each candidate, formulate the join SQL using the **actual zone-qualified table** for each side and run on Athena:
   ```sql
   WITH new_sample AS (
     SELECT {new_col} FROM fip_{new_zone}.{new_table} TABLESAMPLE BERNOULLI(5) LIMIT 1000
   ),
   existing_sample AS (
     SELECT {existing_col} FROM fip_{existing_zone}.{existing_table} TABLESAMPLE BERNOULLI(5) LIMIT 1000
   )
   SELECT
     COUNT(*) AS new_rows,
     SUM(CASE WHEN e.{existing_col} IS NOT NULL THEN 1 ELSE 0 END) AS matched,
     COUNT(*) FILTER (WHERE matched > 100) AS fan_out_flag
   FROM new_sample n
   LEFT JOIN existing_sample e ON n.{new_col} = e.{existing_col}
   ```
4. Compute: match rate = matched / new_rows. Reject if < 5%. Flag fan-out separately.
5. Classify cardinality (1:1, 1:N, N:1, N:M) from the join result.
6. Tag each candidate with `cross_zone: true` when source and target zones differ — this often indicates a legitimate Silver-fact-to-Gold-dimension link, but warrants explicit user attention.

### Step 6 — Confirm relationships with the user

Present each verified candidate as a single batched `AskUserQuestion`:
> Match found between `{new_workload}.{new_zone}.{new_col}` and `{existing_workload}.{existing_zone}.{existing_col}`.
> Match rate: {%}, cardinality: {N:1}, fan-out: {none/flagged}, cross-zone: {true/false}.
> Proposed link: `{NewClass}` `--{predicate}-->` `{ExistingClass}`.
> Accept / Reject / Modify?

User-driven: accept all, accept some, reject all. For accepted links, capture the predicate name (e.g. `belongsToEntity`, `forFiscalPeriod`).

### Step 7 — Merge into consolidated artifacts

Use `shared/semantic_layer/owl_inducer.py` + `shared/semantic_layer/r2rml_mapper.py` patterns:

1. **`semantic-layer/ontology.ttl`** (consolidated OWL):
   - Append one new entity class per (workload, zone) being mapped — `{ClassName} a owl:Class ; rdfs:label ... ; rdfs:comment ...`. **Class names do NOT include Silver/Gold** — zone is a physical-storage detail and would pollute the ontology vocabulary. When both Silver and Gold are mapped for one workload, distinguish by grain or role (e.g. `Trade` for Silver-level rows, `DailyTradeSummary` for Gold aggregates), and link with `rdfs:subClassOf` only when there is a true taxonomic relationship.
   - Append datatype properties for each column with approved description as `rdfs:comment`. The class's properties carry the description for that class's zone.
   - Append object properties for each approved relationship with `rdfs:domain` + `rdfs:range`.
   - Preserve existing classes — add only, never overwrite (unless the user explicitly approves).
   - Validate the merged file with `rdflib` before writing.

2. **`semantic-layer/r2rml-mappings.ttl`** (consolidated R2RML):
   - Append one `<#{ClassName}Map>` `rr:TriplesMap` per (workload, zone) being mapped.
   - `rr:logicalTable [ rr:tableName "fip_{zone}.{table}" ]` — Silver maps target `fip_silver.*`, Gold maps target `fip_gold.*`.
   - One `rr:predicateObjectMap` per column.
   - For each approved relationship: an additional `rr:predicateObjectMap` with `rr:parentTriplesMap` + `rr:joinCondition`. Cross-zone joins are valid R2RML — Ontop translates them to cross-database Athena joins.
   - Validate with `rdflib` (Turtle parse).

3. **`semantic-layer/manifest.json`**: append entry with workload name, ontology version, timestamp, per-workload zone mapping, list of new classes/properties/relationships, and per-relationship `match_rate` + `cardinality` + `cross_zone` evidence.

4. Run `pytest semantic-layer/tests/` (or create scaffold tests if not present) covering: Turtle validates, all R2RML logical tables exist as Glue tables in the correct zone database, all object-property domain/range classes exist in the ontology.

### Step 8 — Present the diff + finalize

Show the user:
- New OWL classes added: count + names (zone-tagged)
- New properties added: count (per zone)
- New relationships: list with match rates + cross-zone tags
- Updated semantic.yaml column descriptions: count
- Per-workload zone mapping summary
- Modified files: `semantic-layer/ontology.ttl`, `semantic-layer/r2rml-mappings.ttl`, `semantic-layer/manifest.json`, `workloads/{name}/config/semantic.yaml`

Stop. Phase 7 deployment is a separate skill the user invokes when ready.

## Outputs

| File | Action |
|---|---|
| `semantic-layer/ontology.ttl` | Created or appended (consolidated OWL VKG) |
| `semantic-layer/r2rml-mappings.ttl` | Created or appended (consolidated R2RML) |
| `semantic-layer/manifest.json` | Created or appended |
| `semantic-layer/.embedding_cache/*.npy` | Embedding cache for incremental re-runs |
| `workloads/{name}/config/semantic.yaml` | Column-level descriptions enriched and confirmed |

## Tests Required

- `semantic-layer/tests/test_consolidated_turtle.py` — both files parse cleanly with `rdflib`.
- `semantic-layer/tests/test_r2rml_table_existence.py` — every `rr:tableName` resolves to a real Glue table in the correct zone database (`fip_silver` or `fip_gold`) via `glue-athena` MCP `get_table`.
- `semantic-layer/tests/test_ontology_referential_integrity.py` — every `rdfs:domain`/`rdfs:range` references a class that exists in the ontology.
- `semantic-layer/tests/test_relationship_evidence.py` — every relationship in `manifest.json` has `match_rate ≥ 0.05`.
- `semantic-layer/tests/test_zone_class_consistency.py` — when both zones are mapped for one workload, both classes share a parent or are linked via `fip:zoneOf`; column overlap is consistent with what the schemas declare.

## NEVER Do

- ❌ Add a relationship to the ontology without Athena join verification.
- ❌ Embed without entity-class context — `earnings` in `estimates` and `fundamentals` MUST embed as different classes (`EstimateRecord.earnings` vs `FundamentalsRecord.earnings`). For zone disambiguation, use grain-based class names (`Trade` vs `DailyTradeSummary`) — never `Silver`/`Gold` in the class name itself.
- ❌ Auto-write descriptions without user approval. The proposed description is a starting point, not a commit.
- ❌ Overwrite existing classes or maps in the consolidated TTL files. Append only — modification requires explicit user approval per class.
- ❌ Run during Phase 4 build — this skill requires at least one deployed table (Silver or Gold).
- ❌ Map a zone the user did not explicitly select. If the user picks Gold-only, do not silently create a Silver class.

## Reference Implementation

Architecture follows the OWL2 + R2RML VKG pattern designed for Ontop on AWS. The canonical OWL style is **record-oriented classes** — one `owl:Class` per logical row type (e.g. `Entity`, `PriceRecord`, `EstimateRecord`), with datatype properties for columns and object properties for joins via `rr:parentTriplesMap` + `rr:joinCondition`. Relationships use noun-phrase predicates (`belongsToSector`, `hasFiscalPeriod`, `listedOn`) rather than generic `hasX` patterns.

Bootstrap example to follow: `semantic-layer/ontology.ttl` (the `Entity` class + dimension classes) and `semantic-layer/r2rml-mappings.ttl` (the `<#EntityMap>` TriplesMap + dimension maps via `rr:sqlQuery DISTINCT`). These are the canonical pattern this repo uses — new workloads onboarding to the semantic layer should follow the same structure.
