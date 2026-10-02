---
name: discovery-protocol
description: ADOP's Phase 1 discovery — the human-in-the-loop gate. Load this before asking a user anything about a dataset and before writing any spec. Defines the profile-then-ask ordering, the zone-targeted question sets for Bronze, Silver and Gold, the mandatory ontology opt-in, the completion checklist, and the things the agent must never infer on the user's behalf. The human provides the rules; the agent does not guess them.
---

# Discovery protocol — the human-in-the-loop gate

Derived from `.claude/rules/00-zone-questions.md` and `.claude/rules/01-human-gate-examples.md`
in the ADOP repository.

**One caveat about this being a skill.** In a checkout those rules are always in context, and a
`PreToolUse` hook independently blocks writes until discovery completes. Neither is true here: a
skill body loads on demand, and the plugin does not install git-level or project-level hooks into
your repository. So the gate in this plugin is carried by the command body, which *is* always
loaded when `/adop:onboard-workflow` runs — and by this skill for detail. If you are reading this
from a sub-agent, the gate has already been passed by the orchestrator; your job is not to
re-open it but not to widen it either.

## Ordering: profile first, then ask

1. **Identify the zone** from the user's prompt.
2. **Auto-discover** what you can — format, schema, row count, null rates, distinct counts,
   partition pattern, five sample rows.
3. **Present the findings** in a visual block before asking anything.
4. **Ask only what you could not discover**, using the zone-specific sets below.
5. **Wait for answers.** Do not generate while a question is outstanding.

Presenting first cuts the question count by roughly 60%. Use
`shared.utils.ascii_display.discovery_block()` so the presentation is identical in the terminal
and in `trace_events.jsonl`:

```text
+--------------------------------------------------------------------+
|  DISCOVERED: Source Profile                                        |
+--------------------------------------------------------------------+
|  * Format: CSV, 31 columns, 50 rows                                |
|  * Likely PK: claim_id (unique, 0% nulls)                          |
|  * PHI detected: member_ssn, member_dob, member_email              |
|  * Nulls: denial_reason (82%), all others 0%                       |
|  * Enums: claim_type (4 vals), claim_status (4), plan_type (5)     |
+--------------------------------------------------------------------+
```

Every presentation and every answer is logged via `tracer.log_exchange()`, so the full Q&A ends
up in the trace.

## Bronze — raw ingestion

Triggered by "onboard", "ingest", "S3", "raw data", "Bronze", "new dataset".

1. **Source and access** — S3 path, IAM role or credentials, KMS requirements
2. **Ingestion pattern** — batch (daily/hourly) or streaming; one-time or recurring
3. **Retention** — how long to keep raw data; is a full archive needed

Auto-discover instead of asking: file format, schema, compression, partitioning.

## Silver — cleansing and conforming

Triggered by "clean", "deduplicate", "Silver", "conform", "transform Bronze".

1. **Uniqueness** — what defines a unique record (PK), and how to handle duplicates
2. **Null handling** — acceptable thresholds; quarantine or drop bad records
3. **Business logic** — SCD Type 1 or 2; late-arriving data; entity matching
4. **Transformations — MANDATORY, NEVER SKIP.** Even when type casts are inferable from the
   schema, you must ask about anything beyond casting and dedup. Present what you auto-discovered
   (type casts, dedup, PII masking) and then ask: *"Beyond these, do you want any derived
   columns, calculations, or custom transforms?"*
5. **Refresh** — incremental or full

Auto-discover: current Bronze schema, column types, null rates. Never skip item 4.

## Gold — business analytics

Triggered by "dashboard", "reporting", "Gold", "KPIs", "analytics", "star schema".

1. **Business outcome** — what questions should this answer, and who consumes it
2. **Metrics** — which KPIs, at what aggregation grain (daily, monthly, by region)
3. **Schema** — star schema (fact + dimensions) or flat denormalised
4. **Freshness** — SLA for data freshness; query concurrency needs
5. **Tool** — which BI tool queries this (Athena, Tableau, QuickSight)

Auto-discover: Silver schema, available dimensions, row counts.

For a multi-zone request, ask all three sets grouped by zone, Bronze first, and do not ask the
Gold questions until Bronze and Silver answers are confirmed.

## Always ask, regardless of zone

1. **PII and compliance** — which columns are PII; GDPR / CCPA / HIPAA / SOX / PCI?
2. **Quality** — thresholds per dimension; which rules are critical versus warning
3. **Scheduling** — cron expression, dependencies, failure handling

## Ontology enrichment — always ask, never assume "no"

Ask whether the Ontology Agent should generate semantic-layer artifacts (OWL + R2RML), which
enables business-term search and NL→SQL downstream. It costs about two minutes at build time.

If the user says **yes**, four follow-ups are mandatory before writing `semantic.yaml`. Present
what you discovered, then ask — the user's domain expertise determines the ontology, not the
column names:

1. **Entities** — "I identified these from your schema: […]. Correct? Any to add, remove, rename?"
2. **Entity types** — which is the fact table (measures, events) and which are dimensions
3. **Relationships and cardinality** — "I see Claim → Member via member_id. Correct? 1:many or
   many:many?" Cardinality drives R2RML join generation.
4. **Use cases and consumers** — NL→SQL, data discovery, BI dashboards, ML features, compliance
   audit? Who uses it? This sets the depth: a compliance audit needs full lineage and provenance
   annotations; NL→SQL needs clear business-term mappings.
5. **Business terms and KPI definitions** — "Loss Ratio", "Clean Claim Rate", "Days to
   Adjudicate", and the formula for each.

## Completion checklist — every item needs a human-provided answer

```
[ ] Zone identified (Bronze, Silver, Gold, or all)
[ ] Zone-specific questions answered
[ ] Transformation rules confirmed by the user — derived columns, calculations, custom logic.
    Never skip this even if you believe none are needed.
[ ] PII columns and compliance requirements confirmed by the user
[ ] Quality thresholds explicitly stated, or the user said "use defaults"
[ ] Schedule explicitly stated by the user
[ ] Ontology opt-in confirmed
[ ] If ontology yes: entities, relationships, use cases, consumers and business terms confirmed
```

If any item is missing, ask. Do not proceed.

## NEVER do these

- NEVER guess a dedup strategy from column names
- NEVER infer null handling from observed null rates
- NEVER assume quality thresholds the user has not stated
- NEVER derive a schedule from observed source frequency — ask
- NEVER assume PII columns from names alone — ask the user to confirm
- NEVER skip the transformation question, even after auto-deriving type casts and PII masking
- NEVER skip the ontology question
- NEVER auto-generate ontology entities, relationships or business terms without confirmation

You MAY profile data and present observations, then you MUST ask: "How would you like to handle
these?"

## Worked contrasts

Correct:

- User says "onboard sales data from S3" → ask about dedup, nulls, thresholds, schedule
- A column is named `email` → ask "Would you like to dedup by email?", do not emit
  `dedup_by: email`
- A 5% null rate is observed → say "Column X has 5% nulls. How would you like to handle nulls?",
  do not emit `drop_nulls=True`
- The source updates daily → ask "What schedule do you want?", do not assume `@daily`
- Profiling finds outliers → present them, then ask what thresholds to set

Violations:

- Writing `transformations.yaml` before asking for cleaning rules
- Assuming `quality_threshold: 0.95` without the user stating it
- Emitting `@daily` because the source updates daily
- Writing `dedup_by: email` because a column is named `email`
- Setting `null_handling: drop` because nulls were observed
- Creating quality rules from an observed distribution without asking

## When the gate does not apply

- Fixing a bug the user has already described
- Answering questions about architecture or existing workloads
- Reading or summarising existing workload configs
- Running tests, or profiling existing data — read-only operations
- Deploying artifacts that were already approved

## If you are a sub-agent and a write is denied

In a checkout, `.claude/hooks/check-discovery-gate.sh` denies writes under
`workloads/{name}/{config,scripts,dags,sql}/` for a workload with neither `config/source.yaml`
nor a `.discovery_complete` marker, and its message ends "create
`workloads/{name}/.discovery_complete` to proceed".

**That instruction is addressed to the orchestrator**, which is the only party holding
`AskUserQuestion` and therefore the only party that can have asked the questions. Sub-agents are
launched without it. So:

- **Do NOT create `.discovery_complete`.** Creating it turns the guardrail into a no-op for every
  later write in that workload.
- Return `status: "blocked"` with the gate named in `blocking_issues`.
- Existing answers in `run/context.json` are **not** a substitute. They may be complete, but the
  marker records that the orchestrator verified them, and that is the orchestrator's call.
