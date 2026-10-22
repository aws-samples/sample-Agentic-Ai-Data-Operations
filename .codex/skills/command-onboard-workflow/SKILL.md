---
name: command-onboard-workflow
description: "End-to-end data pipeline onboarding (Bronze → Silver → Gold) with Codex sub-agents. Use when the user runs /onboard-workflow or asks to onboard a dataset or pipeline end to end, optionally with a regulation (HIPAA, SOX, PCI, GDPR, CCPA)."
---

<!-- Codex-native ADOP workflow skill. The phases use the Codex agent runtime and normal user
     turns; the sub-agent prompts and human-gate rules are maintained here. -->

# /onboard-workflow — Dynamic Workflow Onboarding

You are the Data Onboarding Agent orchestrating a full Bronze→Silver→Gold pipeline with
Codex sub-agents (`spawn_agent` / `wait_agent`). They give you parallel sub-agents,
reasoning-effort routing, and per-phase results that you persist in the trace log.

**CRITICAL: Phase 1 discovery runs FIRST in this conversation. You do NOT generate or
spawn any sub-agent until ALL discovery questions have explicit human answers.**

---

## Step 1: Parse Arguments

The user invokes this command as:
```
/onboard-workflow                     ← no regulation
/onboard-workflow HIPAA               ← single regulation
/onboard-workflow CCPA GDPR           ← multiple regulations
```

Parse the argument(s) after `/onboard-workflow`. Valid values:
- `HIPAA`, `SOX`, `PCI`, `GDPR`, `CCPA`
- Multiple can be combined (e.g., `CCPA GDPR`)
- If no argument, regulation = "NONE"

Store the regulation(s) — they control compliance controls and review depth in Phase 4.

---

## Step 2: Phase 1 Discovery (MANDATORY — runs in THIS conversation)

You MUST ask ALL six question groups below. Ask one group at a time as a normal message
to the user (in Plan mode, use `request_user_input`). End your turn and wait for answers
before proceeding to the next group. Do NOT skip any group.

If the user's initial prompt already contains answers (e.g., "dedup on customer_id, daily at 02:00 UTC"),
acknowledge those answers and CONFIRM them — do not re-ask what's already stated. But still ask
anything NOT covered in the prompt.

### Group 1 — Source
```
[ ] Data source type (S3 / PostgreSQL / RDS / API / other)
[ ] Exact path, table, or endpoint
[ ] Data format (CSV / Parquet / JSON / JDBC / other)
[ ] Credentials or connection method (Secrets Manager reference — NEVER store credentials)
```

### Group 2 — Schema and Keys
```
[ ] Primary key (or composite key) — NEVER guess from column names
[ ] Dedup strategy (keep_latest / keep_first / dedupe-by-PK+timestamp / none)
[ ] Null handling per critical column (drop_row / quarantine / fill_default / allow)
```

### Group 3 — Business Logic and Transformations
```
[ ] Cleaning rules (type casting, date normalization, currency, etc.)
[ ] Gold zone schema type (star_schema / flat_iceberg / iceberg_dynamodb)
[ ] KPIs or business metrics Gold should support
[ ] Derived columns, calculations, custom transforms
```

### Group 4 — PII and Compliance
```
[ ] Which columns contain PII — list explicitly (present auto-detected candidates, user CONFIRMS)
[ ] Masking method per PII column (hash / encrypt / redact / tokenize / mask_partial)
[ ] Compliance regulation(s) (already parsed from args, but confirm with user)
[ ] Additional retention, access-control, or masking requirements beyond the regulation prompt
```

### Group 5 — Quality
```
[ ] Quality thresholds (Silver >= 0.80, Gold >= 0.95 are defaults — user must say "use defaults" or specify)
[ ] Which rules are CRITICAL (block) vs WARNING (log but pass)
[ ] Known data quirks or expected anomalies (e.g., "employer is null for Self-Employed — expected")
```

### Group 6 — Schedule
```
[ ] Refresh schedule (cron expression — NEVER derive from source frequency)
[ ] DAG dependencies (upstream DAGs to wait for, if any)
[ ] Failure handling (retry N times / alert + stop / skip and continue)
[ ] SLA (max acceptable delay before alerting)
```

### Completion Gate

```
ALL SIX GROUPS MUST HAVE EXPLICIT HUMAN ANSWERS BEFORE PROCEEDING.

If the user says "just use defaults" or "figure it out":
  → Respond: "I need explicit answers for Groups [X, Y]. These affect Cedar policies,
    quality gates, and generated artifacts. Let me ask the specific items."
  → Identify unanswered items and ask again.
  → Do NOT proceed with unknowns.

If the user cannot answer a question:
  → Explain WHY it matters and the consequence of each option.
  → Offer 2-3 concrete choices with tradeoffs.
  → User selects one. Record the selection.
```

---

## Step 3: Auto-Profile Source Data

Before asking Groups 2-6, profile the source data:
1. Read a sample (CSV: first 50 rows, S3: head object, DB: LIMIT 50 query)
2. Present findings using this format:

```
+--------------------------------------------------------------------+
|  DISCOVERED: Source Profile                                        |
+--------------------------------------------------------------------+
|  * Format: CSV, {N} columns, {M} rows                             |
|  * Likely PK: {column} (unique, 0% nulls)                         |
|  * PII detected: {columns}                                         |
|  * Nulls: {column} ({N}%), all others 0%                          |
|  * Enums: {column} ({N} values)                                    |
+--------------------------------------------------------------------+
```

3. Then ask ONLY what you couldn't discover. This reduces questions significantly.

---

## Step 4: Collect Args Object

After ALL groups are answered, build this JSON object from the answers:

```json
{
  "workload_name": "<snake_case_name>",
  "regulation": ["CCPA", "GDPR"],
  "source": {
    "type": "csv",
    "location": "s3://bucket/path/file.csv",
    "format": "csv",
    "frequency": "daily"
  },
  "primary_key": ["customer_id"],
  "dedup_strategy": "keep_latest",
  "dedup_order_by": "account_open_date",
  "null_handling": {
    "strategy": "quarantine",
    "critical_columns": ["customer_id", "email"]
  },
  "pii_columns": [
    {"name": "ssn", "type": "SSN", "sensitivity": "CRITICAL", "method": "hash"},
    {"name": "email", "type": "EMAIL", "sensitivity": "HIGH", "method": "hash"}
  ],
  "transformations": {
    "type_casts": [
      {"column": "date_of_birth", "from_type": "STRING", "to_type": "DATE", "format": "yyyy-MM-dd"}
    ],
    "derived_columns": [
      {"name": "age_years", "expression": "floor(datediff(current_date(), date_of_birth) / 365.25)"}
    ]
  },
  "quality": {
    "silver_threshold": 0.80,
    "gold_threshold": 0.95,
    "critical_rules": ["not_null_pk", "ssn_format"],
    "custom_rules": []
  },
  "schedule": {
    "cron": "0 2 * * *",
    "retries": 3,
    "sla_minutes": 120
  },
  "gold_format": "star_schema",
  "gold_measures": [
    {"name": "customer_count", "source_column": "customer_id", "aggregation": "count"}
  ],
  "gold_dimensions": [
    {"name": "risk_profile", "source_column": "risk_profile", "scd_type": 2}
  ],
  "ontology": {
    "enabled": true,
    "entities": ["Customer", "Address"],
    "relationships": [{"subject": "Customer", "predicate": "hasAddress", "object": "Address"}],
    "business_terms": ["Wealth Tier", "Customer Tenure"]
  }
}
```

---

## Step 5: Create Discovery Marker + Present Plan

1. Write the `.discovery_complete` marker file:
   ```
   workloads/{workload_name}/.discovery_complete
   ```

2. Present a summary table to the user:
   ```
   ┌────────────────────────────────────────────────────────────────┐
   │  WORKFLOW PLAN: {workload_name}                                │
   ├────────────────────────────────────────────────────────────────┤
   │  Regulation: {regulation}                                      │
   │  Reasoning effort: {BUILD_EFFORT} (Phase 4 agents)            │
   │  Phases: Health → Dedup → Profile → Build → Validate → Deploy │
   │  Est. agents: ~15 | Est. time: 10-20 min                      │
   └────────────────────────────────────────────────────────────────┘
   ```

3. Ask: "Ready to launch the workflow? (Yes / Let me adjust something)"

---

## Step 6: Reasoning-Effort Routing

Determine the Phase 4 build reasoning effort based on regulation:

| Regulation | Source tier | BUILD_EFFORT |
|---|---|---|
| HIPAA, SOX, PCI | `high` | Compliance-sensitive generation and review |
| GDPR, CCPA, none | `medium` | Standard generation and review |

If multiple regulations, use the highest tier (e.g., CCPA + GDPR → medium, HIPAA + SOX → high).

The adversarial reviewer (Phase 3) and verifier (Phase 4) ALWAYS use `high` regardless of regulation.

---

## Step 7: Run the Phases with Codex Sub-Agents

After the user confirms, run the phases below yourself, as the orchestrator, using
`spawn_agent`, `wait_agent`, and `close_agent`. Sub-agents cannot ask the user questions.
Every human decision was already made in Steps 2–5, and you pass those answers into each
prompt.

Before Phase 0, generate `run_id = onboard-{workload_name}-{UTC timestamp}`. Record the
start time of each phase for the Step 8 trace log.

### Orchestration rules

- **Parallel** means: call `spawn_agent` once per prompt in the group, then call
  `wait_agent` with every returned id, then `close_agent` each id once you have its result.
- **Sequential** means: spawn, wait, and close one agent before the next phase starts.
- Spawn with `agent_type: "default"` and pass the prompt as `message`. Fill every
  `{placeholder}` from the Step 4 args object, or from earlier phase results, as noted.
  Serialize objects as JSON.
- Do not set `model`. Sub-agents inherit the session model, which works on every
  provider, including Amazon Bedrock. Route capability with `reasoning_effort` instead:

  | Source tier | `reasoning_effort` |
  |---|---|
  | `low` | Lightweight validation |
  | `medium` | Standard artifact generation |
  | `high` | Complex reasoning and adversarial review |
  | `BUILD_MODEL` | `BUILD_EFFORT` from Step 6 |

- **Multi-workload batch:** if the user gave several datasets, run Phases 0–4.5
  independently for each workload. Different workloads may run concurrently. Phases
  within one workload stay in the order below.
- If a workload is marked `blocked`, skip its remaining phases.

### Phase 0: Health Check (sequential, `low`)

```
Verify MCP server connectivity for data onboarding.
REQUIRED (block if down): glue-athena, lakeformation, iam
WARN (log but continue): cloudtrail, redshift, core, s3-tables, pii-detection
OPTIONAL (skip): sagemaker-catalog, lambda, cloudwatch, cost-explorer, dynamodb
Report: status per server (UP/DOWN/SKIP). If any REQUIRED is DOWN, say BLOCKED.
```

If the result contains `BLOCKED`, mark the workload `blocked` with the result as the
reason, and report it to the user.

### Phase 2: Dedup Check (parallel, both `low`)

Agent A, dedup:

```
Scan all files matching workloads/*/config/source.yaml.
Compare against this new source: {source}
Check for: exact path duplicates, overlapping sources, subset/superset.
Report: CLEAN (no overlap) or OVERLAP with details.
```

Agent B, source check:

```
Verify source data is accessible: {source}
For S3: check if object/prefix exists. For DB: test connectivity.
Report: REACHABLE or UNREACHABLE with error details.
```

Store the results as `dedup` and `sourceCheck`.

### Phase 3: Profile (parallel)

Agent A, profiler (`medium`):

```
You are the Metadata Profiler.
Workload: {workload_name}
Source: {source}

Tasks:
1. Discover schema (column names, types, nullable)
2. Profile: row count, distinct values, null rates, min/max per column
3. Detect PII patterns (name-based + content-based)
4. Identify likely primary keys (unique + non-null columns)

Return a structured summary: schema, profiling_stats, pii_candidates, pk_candidates.
```

Agent B, adversarial reviewer (`high`):

```
You are an adversarial data quality reviewer.
Workload: {workload_name}
User-declared PK: {primary_key}
User-declared PII: {pii_columns}
User-declared transforms: {transformations}

Challenge the assumptions:
1. Could there be PII the user missed?
2. Is the declared PK truly unique?
3. Are there data quality risks not covered?
4. Any schema evolution or type-safety concerns?

Return: missed_risks, pk_concerns, quality_gaps, recommendations.
```

Store the results as `profile` and `adversarialReview`.

### Phase 4: Build (`BUILD_EFFORT`)

Set `{regNote}` as follows:

- If a regulation was given (not `NONE`): `Apply regulation controls: {regulation}. Reference runbooks/data-onboarding-agent/regulation/ for details.`
- Otherwise: `No specific regulation — standard quality gates only.`

**Stage 1 (parallel):**

Metadata:

```
You are the Metadata Agent. Generate config specs for workload: {workload_name}

Source: {source}
PK: {primary_key}
PII columns: {pii_columns}
Profile data: {profile}
{regNote}

Generate these specs as JSON:
1. source.yaml content (full schema with column roles, types, PII flags)
2. semantic.yaml content (entities, relationships, business terms)

Return JSON: { source_yaml: {...}, semantic_yaml: {...} }
```

Quality:

```
You are the Quality Agent. Generate quality rules for workload: {workload_name}

User quality config: {quality}
PII columns: {pii_columns}
Profile data: {profile}
{regNote}

Generate quality.yaml content as JSON:
- Completeness rules (not-null on critical columns)
- Uniqueness rules (PK uniqueness)
- Validity rules (enums, ranges, formats, date bounds)
- Consistency rules (cross-column logic)
- Quality gates: Silver >= {quality.silver_threshold}, Gold >= {quality.gold_threshold}
- Anomaly detection config

Return JSON: { quality_yaml: {...} }
```

**Stage 2 (sequential, after Stage 1):** Transformation

```
You are the Transformation Agent. Generate transform specs for workload: {workload_name}

Source schema (from Metadata): {stage1 metadata result}
Quality rules (from Quality): {stage1 quality result}
User transforms: {transformations}
PII masking: {pii_columns}
Dedup: strategy={dedup_strategy}, order_by={dedup_order_by}
Null handling: {null_handling}
Gold format: {gold_format}
Gold measures: {gold_measures}
Gold dimensions: {gold_dimensions}
{regNote}

Generate these specs as JSON:
1. silver_spec — matches contracts/v1/silver_spec.schema.json
2. gold_spec — matches contracts/v1/gold_spec.schema.json

Return JSON: { silver_spec: {...}, gold_spec: {...} }
```

**Stage 3 (sequential, after Stage 2):** DAG

```
You are the DAG Agent. Generate Airflow DAG spec for workload: {workload_name}

Schedule: {schedule}
Stages: bronze_ingest → silver_transform → silver_quality → gold_aggregate → gold_quality
{regNote}

Generate the DAG configuration as JSON:
- dag_id, schedule_interval, start_date, tags
- task_groups with Glue job references
- retry policy, SLA, failure callbacks
- All Variable.get() calls MUST have default_var

Return JSON: { dag_spec: {...} }
```

Store the results as `metadata`, `quality`, `transform`, and `dag`.

### Phase 4 Verify (sequential, `high`)

```
You are a senior data engineer verifying pipeline specs.
Workload: {workload_name}
Regulation: {regulation}

Review ALL generated specs for:
1. Silver spec validates against contracts/v1/silver_spec.schema.json
2. Gold spec validates against contracts/v1/gold_spec.schema.json
3. No hardcoded credentials, account IDs, or bucket names
4. PII columns all have masking methods assigned
5. Quality gates set correctly (Silver >= threshold, Gold >= threshold)
6. DAG has catchup=False, max_active_runs=1, default_var on all Variable.get()
7. Regulation-specific controls present if regulation specified

Specs to review:
- Metadata: {metadata}
- Quality: {quality}
- Transform: {transform}
- DAG: {dag}

Return JSON: { passed: true/false, issues: [{spec, field, severity, description}] }
```

Store the result as `verification`. Log `PASSED` if it contains `"passed": true`, and
`ISSUES FOUND` otherwise.

### Phase 4.5: Pre-Deploy Validation (parallel, both `low`)

Spec validation:

```
Validate the silver_spec and gold_spec JSON are well-formed and contain all required fields.
silver_spec required: dataset_name, schema_version, source_table, primary_key, dedup_strategy, quality_threshold
gold_spec required: dataset_name, schema_version, source_table, schema_type, grain, measures
Specs: {transform}
Report: VALID or list missing fields.
```

Security scan:

```
Security scan: check all generated specs for workload {workload_name}.
Scan for: hardcoded credentials, AWS account IDs, API keys, secrets.
Specs: {metadata} {quality} {transform} {dag}
Report: CLEAN or list violations.
```

Store the results as `preDeployChecks`, then continue to Step 8 with every
non-blocked workload.

---

## Step 8: After the Phases — Write Files

After Phase 4.5 finishes, you (the main conversation agent) write the actual files:

1. **Config YAML files** — write directly from the specs returned by workflow agents:
   - `workloads/{name}/config/source.yaml`
   - `workloads/{name}/config/silver.yaml`
   - `workloads/{name}/config/gold.yaml`
   - `workloads/{name}/config/quality.yaml`
   - `workloads/{name}/config/schedule.yaml`
   - `workloads/{name}/config/semantic.yaml`

2. **Python scripts** — use the codegen renderer (MANDATORY):
   ```python
   from shared.codegen.renderer import render
   render(spec=silver_spec, spec_hash=..., template_id='silver_transform', ...)
   render(spec=gold_spec, spec_hash=..., template_id='gold_aggregate', ...)
   ```
   NEVER write .py files to `scripts/`, `dags/`, or `sql/` directly.

3. **Quality script** — write `scripts/quality/glue_data_quality.py` (not template-gated)

4. **DAG file** — write `dags/{name}_pipeline.py` (not template-gated)

5. **Ontology** (if enabled) — write `config/ontology.ttl` + `config/mappings.ttl`

6. **Tests** — write unit tests to `tests/unit/`

7. **Run tests** — `python3 -m pytest workloads/{name}/tests/unit/ -v`

8. **Trace log (MANDATORY)** — write `logs/trace_events.jsonl` with one JSONL event per phase:
   - Each event: `{timestamp, run_id, surface, event_type, agent_name, workload_name, phase, status, duration_ms, payload}`
   - Surfaces: `operational` (what happened), `cognitive` (adversarial findings, decisions)
   - Include: workflow_start, phase_complete (per phase), adversarial findings, workflow_complete
   - The run_id is the one you generated at the start of Step 7

   This is NON-NEGOTIABLE. AGENTS.md requires every workload to have `logs/` with traces.

---

## Step 9: Post-Deployment Sequence

After files are written and tests pass, follow AGENTS.md Steps 5.10 and 5.11:

1. **Offer E2E pipeline test** (Step 5.10)
2. **Offer DevOps Agent** (Step 5.11)

NEVER skip asking these questions.

---

## Error Handling

| Situation | Action |
|---|---|
| Phase 0 returns "BLOCKED" | Tell user which MCP servers are down. Do not proceed. |
| Phase 2 finds exact duplicate | Show overlap. Ask user: rename, merge, or cancel. |
| Phase 4 Verifier finds issues | Present issues list. Ask user to resolve. Re-run affected phase. |
| A sub-agent fails, errors, or times out | Show the error. Offer a fallback: "Want me to run this phase sequentially in this conversation instead?" |
| User wants to abort mid-workflow | Respect immediately. Partial results are preserved. |
