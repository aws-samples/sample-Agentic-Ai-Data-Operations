---
name: command-onboard-workflow
description: "End-to-end data pipeline onboarding (Bronze → Silver → Gold) with Codex sub-agents. Use when the user invokes $command-onboard-workflow or asks to onboard a dataset or pipeline end to end, optionally with a regulation (HIPAA, SOX, PCI, GDPR, CCPA)."
---

<!-- Codex-native ADOP workflow skill. The phases use the Codex agent runtime and normal user
     turns; the sub-agent prompts and human-gate rules are maintained here. -->

# $command-onboard-workflow — Dynamic Workflow Onboarding

You are the Data Onboarding Agent orchestrating a full Bronze→Silver→Gold pipeline with
Codex sub-agents (`spawn_agent` / `wait_agent`). They give you parallel sub-agents,
reasoning-effort routing, and per-phase results that you persist in the trace log.

**CRITICAL: Phase 1 discovery runs FIRST in this conversation. You do NOT generate or
spawn any sub-agent until ALL discovery questions have explicit human answers.**

---

## Step 1: Read the Request and Detect Regulations

The user explicitly invokes this skill as `$command-onboard-workflow`, or asks in natural
language to onboard a dataset. Read the regulation and workload details from the surrounding
request.

Before applying the `NONE` default, run the deterministic detector:

```python
from shared.compliance.regulation_detector import detect_regulations

detection = detect_regulations(user_request_text)
regulation = list(detection.active)
```

Any explicit positive mention activates the matching framework immediately, including
plain-language phrases such as "we follow GDPR" or "General Data Protection Regulation".
Persist `detection.as_human_answer()` as `human_answers.compliance` when the new run context
is created, and load every matching pack before asking the remaining discovery questions.
Negated mentions (for example, "GDPR is not required") remain excluded. Do not infer a
regulation from column names, observed values, or the presence of payment data.

If an authoritative persisted `human_answers.compliance` already exists, it wins over a
newly paraphrased request; report any conflict instead of silently replacing it.

Examples:
```
$command-onboard-workflow
Onboard claims data. Regulation: HIPAA.

$command-onboard-workflow
Onboard customer and order data. Regulations: CCPA and GDPR.
```

Valid regulation values:
- `HIPAA`, `SOX`, `PCI`, `GDPR`, `CCPA`
- Multiple can be combined (e.g., `CCPA GDPR`)
- If no explicit regulation is detected, regulation = "NONE"

Store the normalized regulation(s) — they control compliance controls and review depth in
Phase 4. Never ask the user to repeat a regulation that was explicitly detected; confirm the
detection and continue with only the unanswered compliance details.

---

## Step 2: Phase 1 Discovery (MANDATORY — runs in THIS conversation)

You MUST ask ALL six question groups below. Ask one group at a time as a normal message
to the user (in Plan mode, use `request_user_input`). End your turn and wait for answers
before proceeding to the next group. Do NOT skip any group.

If the user's initial prompt already contains answers (e.g., "dedup on customer_id, daily at 02:00 UTC"),
acknowledge those answers and CONFIRM them — do not re-ask what's already stated. But still ask
anything NOT covered in the prompt.

For every user prompt and response, append a `user_turn` record to
`workloads/{workload_name}/run/requirements.jsonl`, then append explicit
`requirement` records with stable IDs and target artifacts. Do not mark a turn
as satisfied merely because it was answered; the requirements auditor must
later verify artifact evidence.

### Group 1 — Source
```
[ ] Data source type (S3 / PostgreSQL / RDS / API / other)
[ ] Exact path, table, or endpoint
[ ] Data format (CSV / Parquet / JSON / Avro / ORC / XML / log text / JDBC / other)
[ ] XML row tag or log type (nginx / Apache / Syslog / CloudTrail / application / custom)
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
REQUIRED (block if down): aws-mcp (serves Glue + Athena; the custom glue-athena MCP is excluded for now), lakeformation, iam
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

Store the results as `preDeployChecks`.

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

### Step 8.5: Requirements Conformance Audit (sequential, `high`)

After the actual files and tests exist, spawn the `requirements-auditor`:

```
Audit workload {workload_name} against every captured user turn and explicit
requirement in workloads/{workload_name}/run/requirements.jsonl.

Read the authoritative run/context.json, decisions.jsonl, trace_events.jsonl,
all configs/generated artifacts/tests, and deployment evidence available on disk.
Verify that every user turn is linked to a requirement ID and every mandatory
requirement has concrete artifact evidence. Do not infer or waive requirements.

Persist run/requirements_audit.json, append the decision and trace event, and
return BLOCKED if any mandatory requirement is missing, ambiguous, conflicting,
or unverified.
```

Only a `PASS` audit may continue to deployment. A blocked audit must be reported
to the human with its requirement IDs and evidence gaps.

---

## Step 8.6: Deploy (Phase 5 — main conversation, MANDATORY)

Phase 4.5 Pre-Deploy only validates specs; deployment runs here, in the main
conversation (the only party with MCP tools), after the audit passes. Follow `MCP_GUARDRAILS.md`
Phase 5 step by step. Every gate below exits 2 on failure — stop, show the JSON
output to the user, and do not continue until it passes.

1. **Health check** (Step 5.0) — re-run or confirm reuse of Phase 0 results.
2. **Audit + local preflight** (Step 5.3, no AWS calls):
   `python3 -m shared.utils.deployment_checks preflight --context workloads/{name}/run/context.json --glue-role {workload}-glue-service-role`
   This refuses to run unless `run/requirements_audit.json` has `status: pass`, matches the
   current `run_id`, and is newer than `context.json` and everything under
   `config/`, `scripts/`, `dags/` and `sql/`. On pass it writes `run/deploy_gate.json`.
   **The `deploy_gate.py` PreToolUse hook denies every deploy mutation until that file
   exists**, so this step cannot be skipped — not by you, and not by a sub-agent.
   If the audit is missing, stale or blocked, re-run the `requirements-auditor` and fix
   what it reports. Never hand-write `deploy_gate.json`.
3. **S3 upload, Glue catalog, IAM** (Steps 5.1–5.3) via MCP.
4. **Role simulation gate** (Step 5.3a, read-only) — before any job or DAG exists:
   `python3 -m shared.utils.deployment_checks simulate --workload-dir workloads/{name} --region {region} --mwaa-role-arn {mwaa_role_arn} --glue-role-arn {glue_role_arn} --jobs {jobs...} --databases {dbs...} --kms-key-arn {kms_key_arn}`
   Covers MWAA `glue:GetJob`/`StartJobRun`/`GetJobRun` + `iam:PassRole`, and the Glue
   role's catalog (including `default`) and KMS calls.
5. **Lake Formation, KMS, query verify, audit trail** (Steps 5.4–5.7).
6. **Glue jobs** (Step 5.8a) — upload `scripts/**`, `create_job`/`update_job` via MCP.
7. **MWAA DAG** (Step 5.8b) — upload `dags/{name}_dag.py` to the environment's DAG prefix.
8. **Verify** (Step 5.9) — `python3 shared/utils/post_deployment_verifier.py --workload {name} --database {db} --tables {tables...}
   --query-principal-arn {arn} --mwaa-env {env} --dag-id {dag_id} --mwaa-role-arn {arn}
   --glue-role-arn {arn} --glue-jobs {jobs...} --kms-key-arn {arn}`. All checks must PASS,
   including 5.9f (no `dags list-import-errors` for the workload) and 5.9i/5.9j (role simulation).
9. **Before any manual job start** (Step 5.8c) — `python3 -m shared.utils.deployment_checks active-runs --region {region} --jobs {jobs...}`.
   A run already in flight blocks the start; wait for it.

Record each gate result as a `deployment_step` event in `logs/trace_events.jsonl`.

---

## Step 9: Post-Deployment Sequence

After Step 8.6 deploys and Step 5.9 verification passes, follow AGENTS.md Steps 5.10 and 5.11:

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
| Step 8.6 gate exits 2 (preflight / simulate / active-runs / 5.9) | Show the JSON. Fix the cause (policy, DAG import, wait for run). Re-run the gate. Never skip it. |
| A sub-agent fails, errors, or times out | Show the error. Offer a fallback: "Want me to run this phase sequentially in this conversation instead?" |
| User wants to abort mid-workflow | Respect immediately. Partial results are preserved. |
