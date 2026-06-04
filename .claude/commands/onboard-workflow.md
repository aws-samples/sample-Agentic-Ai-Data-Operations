---
allowed-tools: Bash(python3:*), Bash(ls:*), Bash(find:*), Bash(aws:*), Bash(grep:*), Read, Write, Workflow, AskUserQuestion, Agent
description: End-to-end data pipeline onboarding via Dynamic Workflow (Bronze → Silver → Gold)
---

# /onboard-workflow — Dynamic Workflow Onboarding

You are the Data Onboarding Agent orchestrating a full Bronze→Silver→Gold pipeline via a
Claude Code Dynamic Workflow. This gives you parallel sub-agents, model routing, and
structured progress persistence.

**CRITICAL: Phase 1 discovery runs FIRST in this conversation. You do NOT generate or
invoke the Workflow tool until ALL discovery questions have explicit human answers.**

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

Store the regulation(s) — they control model routing in Phase 4.

---

## Step 2: Phase 1 Discovery (MANDATORY — runs in THIS conversation)

You MUST ask ALL six question groups below. Ask one group at a time using `AskUserQuestion`.
Wait for answers before proceeding to the next group. Do NOT skip any group.

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
   │  Model tier: {BUILD_MODEL} (Phase 4 agents)                   │
   │  Phases: Health → Dedup → Profile → Build → Validate → Deploy │
   │  Est. agents: ~15 | Est. time: 10-20 min                      │
   └────────────────────────────────────────────────────────────────┘
   ```

3. Ask: "Ready to launch the workflow? (Yes / Let me adjust something)"

---

## Step 6: Model Routing

Determine the Phase 4 build model based on regulation:

| Regulation | BUILD_MODEL |
|---|---|
| HIPAA, SOX, PCI | `opus` |
| GDPR, CCPA, none | `sonnet` |

If multiple regulations, use the highest tier (e.g., CCPA + GDPR → sonnet, HIPAA + SOX → opus).

The adversarial reviewer (Phase 3) and verifier (Phase 4) ALWAYS use `opus` regardless of regulation.

---

## Step 7: Invoke Dynamic Workflow

After user confirms, invoke the `Workflow` tool with the script below.
Replace all `${...}` placeholders with values from the args object.

For **multi-workload batch**: if the user provided multiple datasets, `args.workloads` is an array
and the workflow uses `pipeline(args.workloads, ...)` to process each independently.

### Workflow Script Template

```javascript
export const meta = {
  name: 'onboard-pipeline',
  description: 'Full Bronze→Silver→Gold pipeline onboarding with parallel sub-agents',
  phases: [
    { title: 'Health Check', detail: 'Verify MCP server connectivity' },
    { title: 'Dedup Check', detail: 'Scan existing workloads for overlap' },
    { title: 'Profile', detail: 'Schema discovery + PII detection + adversarial review' },
    { title: 'Build', detail: 'Generate specs: metadata, quality, transform, DAG' },
    { title: 'Verify', detail: 'Adversarial review of all generated specs' },
    { title: 'Pre-Deploy', detail: 'Syntax validation + security scan' },
    { title: 'Deploy', detail: 'Write configs, render scripts, register catalog' }
  ]
}

const WORKLOADS = Array.isArray(args.workloads) ? args.workloads : [args]
const REGULATIONS_REQUIRING_OPUS = ['HIPAA', 'SOX', 'PCI']

function getBuildModel(regulation) {
  const regs = Array.isArray(regulation) ? regulation : [regulation]
  return regs.some(r => REGULATIONS_REQUIRING_OPUS.includes(r)) ? 'opus' : 'sonnet'
}

const results = await pipeline(
  WORKLOADS,

  // ─── Phase 0: Health Check ───────────────────────────────────────
  async (wl) => {
    phase('Health Check')
    const health = await agent(
      `Verify MCP server connectivity for data onboarding.\n` +
      `REQUIRED (block if down): glue-athena, lakeformation, iam\n` +
      `WARN (log but continue): cloudtrail, redshift, core, s3-tables, pii-detection\n` +
      `OPTIONAL (skip): sagemaker-catalog, lambda, cloudwatch, cost-explorer, dynamodb\n` +
      `Report: status per server (UP/DOWN/SKIP). If any REQUIRED is DOWN, say BLOCKED.`,
      { model: 'haiku', label: `health:${wl.workload_name}`, phase: 'Health Check' }
    )
    if (health && health.includes('BLOCKED')) {
      log(`BLOCKED: ${wl.workload_name} — required MCP servers unavailable`)
      return { ...wl, blocked: true, reason: health }
    }
    return { ...wl, health }
  },

  // ─── Phase 2: Dedup Check ────────────────────────────────────────
  async (wl) => {
    if (wl.blocked) return wl
    phase('Dedup Check')
    const results = await parallel([
      () => agent(
        `Scan all files matching workloads/*/config/source.yaml.\n` +
        `Compare against this new source: ${JSON.stringify(wl.source)}\n` +
        `Check for: exact path duplicates, overlapping sources, subset/superset.\n` +
        `Report: CLEAN (no overlap) or OVERLAP with details.`,
        { model: 'haiku', label: `dedup:${wl.workload_name}`, phase: 'Dedup Check' }
      ),
      () => agent(
        `Verify source data is accessible: ${JSON.stringify(wl.source)}\n` +
        `For S3: check if object/prefix exists. For DB: test connectivity.\n` +
        `Report: REACHABLE or UNREACHABLE with error details.`,
        { model: 'haiku', label: `source-check:${wl.workload_name}`, phase: 'Dedup Check' }
      )
    ])
    log(`${wl.workload_name}: dedup=${results[0] ? 'done' : 'null'}, source=${results[1] ? 'done' : 'null'}`)
    return { ...wl, dedup: results[0], sourceCheck: results[1] }
  },

  // ─── Phase 3: Profile ────────────────────────────────────────────
  async (wl) => {
    if (wl.blocked) return wl
    phase('Profile')
    const BUILD_MODEL = getBuildModel(wl.regulation)
    const results = await parallel([
      () => agent(
        `You are the Metadata Profiler.\n` +
        `Workload: ${wl.workload_name}\n` +
        `Source: ${JSON.stringify(wl.source)}\n\n` +
        `Tasks:\n` +
        `1. Discover schema (column names, types, nullable)\n` +
        `2. Profile: row count, distinct values, null rates, min/max per column\n` +
        `3. Detect PII patterns (name-based + content-based)\n` +
        `4. Identify likely primary keys (unique + non-null columns)\n\n` +
        `Return a structured summary: schema, profiling_stats, pii_candidates, pk_candidates.`,
        { model: 'sonnet', label: `profile:${wl.workload_name}`, phase: 'Profile' }
      ),
      () => agent(
        `You are an adversarial data quality reviewer.\n` +
        `Workload: ${wl.workload_name}\n` +
        `User-declared PK: ${JSON.stringify(wl.primary_key)}\n` +
        `User-declared PII: ${JSON.stringify(wl.pii_columns)}\n` +
        `User-declared transforms: ${JSON.stringify(wl.transformations)}\n\n` +
        `Challenge the assumptions:\n` +
        `1. Could there be PII the user missed?\n` +
        `2. Is the declared PK truly unique?\n` +
        `3. Are there data quality risks not covered?\n` +
        `4. Any schema evolution or type-safety concerns?\n\n` +
        `Return: missed_risks, pk_concerns, quality_gaps, recommendations.`,
        { model: 'opus', label: `adversarial:${wl.workload_name}`, phase: 'Profile' }
      )
    ])
    log(`${wl.workload_name}: profiling complete`)
    return { ...wl, profile: results[0], adversarialReview: results[1] }
  },

  // ─── Phase 4: Build ──────────────────────────────────────────────
  async (wl) => {
    if (wl.blocked) return wl
    phase('Build')
    const BUILD_MODEL = getBuildModel(wl.regulation)
    const regNote = wl.regulation && wl.regulation.length > 0 && wl.regulation[0] !== 'NONE'
      ? `Apply regulation controls: ${JSON.stringify(wl.regulation)}. Reference prompts/data-onboarding-agent/regulation/ for details.`
      : 'No specific regulation — standard quality gates only.'

    // Stage 1: Metadata + Quality in parallel
    const stage1 = await parallel([
      () => agent(
        `You are the Metadata Agent. Generate config specs for workload: ${wl.workload_name}\n\n` +
        `Source: ${JSON.stringify(wl.source)}\n` +
        `PK: ${JSON.stringify(wl.primary_key)}\n` +
        `PII columns: ${JSON.stringify(wl.pii_columns)}\n` +
        `Profile data: ${wl.profile}\n` +
        `${regNote}\n\n` +
        `Generate these specs as JSON:\n` +
        `1. source.yaml content (full schema with column roles, types, PII flags)\n` +
        `2. semantic.yaml content (entities, relationships, business terms)\n\n` +
        `Return JSON: { source_yaml: {...}, semantic_yaml: {...} }`,
        { model: BUILD_MODEL, label: `metadata:${wl.workload_name}`, phase: 'Build' }
      ),
      () => agent(
        `You are the Quality Agent. Generate quality rules for workload: ${wl.workload_name}\n\n` +
        `User quality config: ${JSON.stringify(wl.quality)}\n` +
        `PII columns: ${JSON.stringify(wl.pii_columns)}\n` +
        `Profile data: ${wl.profile}\n` +
        `${regNote}\n\n` +
        `Generate quality.yaml content as JSON:\n` +
        `- Completeness rules (not-null on critical columns)\n` +
        `- Uniqueness rules (PK uniqueness)\n` +
        `- Validity rules (enums, ranges, formats, date bounds)\n` +
        `- Consistency rules (cross-column logic)\n` +
        `- Quality gates: Silver >= ${wl.quality.silver_threshold}, Gold >= ${wl.quality.gold_threshold}\n` +
        `- Anomaly detection config\n\n` +
        `Return JSON: { quality_yaml: {...} }`,
        { model: BUILD_MODEL, label: `quality:${wl.workload_name}`, phase: 'Build' }
      )
    ])
    log(`${wl.workload_name}: metadata + quality specs done`)

    // Stage 2: Transformation (depends on metadata + quality)
    const transformSpec = await agent(
      `You are the Transformation Agent. Generate transform specs for workload: ${wl.workload_name}\n\n` +
      `Source schema (from Metadata): ${stage1[0]}\n` +
      `Quality rules (from Quality): ${stage1[1]}\n` +
      `User transforms: ${JSON.stringify(wl.transformations)}\n` +
      `PII masking: ${JSON.stringify(wl.pii_columns)}\n` +
      `Dedup: strategy=${wl.dedup_strategy}, order_by=${wl.dedup_order_by}\n` +
      `Null handling: ${JSON.stringify(wl.null_handling)}\n` +
      `Gold format: ${wl.gold_format}\n` +
      `Gold measures: ${JSON.stringify(wl.gold_measures)}\n` +
      `Gold dimensions: ${JSON.stringify(wl.gold_dimensions)}\n` +
      `${regNote}\n\n` +
      `Generate these specs as JSON:\n` +
      `1. silver_spec — matches contracts/v1/silver_spec.schema.json\n` +
      `2. gold_spec — matches contracts/v1/gold_spec.schema.json\n\n` +
      `Return JSON: { silver_spec: {...}, gold_spec: {...} }`,
      { model: BUILD_MODEL, label: `transform:${wl.workload_name}`, phase: 'Build' }
    )
    log(`${wl.workload_name}: transform specs done`)

    // Stage 3: DAG (depends on all above)
    const dagSpec = await agent(
      `You are the DAG Agent. Generate Airflow DAG spec for workload: ${wl.workload_name}\n\n` +
      `Schedule: ${JSON.stringify(wl.schedule)}\n` +
      `Stages: bronze_ingest → silver_transform → silver_quality → gold_aggregate → gold_quality\n` +
      `${regNote}\n\n` +
      `Generate the DAG configuration as JSON:\n` +
      `- dag_id, schedule_interval, start_date, tags\n` +
      `- task_groups with Glue job references\n` +
      `- retry policy, SLA, failure callbacks\n` +
      `- All Variable.get() calls MUST have default_var\n\n` +
      `Return JSON: { dag_spec: {...} }`,
      { model: BUILD_MODEL, label: `dag:${wl.workload_name}`, phase: 'Build' }
    )
    log(`${wl.workload_name}: DAG spec done`)

    return { ...wl, metadata: stage1[0], quality: stage1[1], transform: transformSpec, dag: dagSpec }
  },

  // ─── Phase 4 Verify ──────────────────────────────────────────────
  async (wl) => {
    if (wl.blocked) return wl
    phase('Verify')
    const verification = await agent(
      `You are a senior data engineer verifying pipeline specs.\n` +
      `Workload: ${wl.workload_name}\n` +
      `Regulation: ${JSON.stringify(wl.regulation)}\n\n` +
      `Review ALL generated specs for:\n` +
      `1. Silver spec validates against contracts/v1/silver_spec.schema.json\n` +
      `2. Gold spec validates against contracts/v1/gold_spec.schema.json\n` +
      `3. No hardcoded credentials, account IDs, or bucket names\n` +
      `4. PII columns all have masking methods assigned\n` +
      `5. Quality gates set correctly (Silver >= threshold, Gold >= threshold)\n` +
      `6. DAG has catchup=False, max_active_runs=1, default_var on all Variable.get()\n` +
      `7. Regulation-specific controls present if regulation specified\n\n` +
      `Specs to review:\n` +
      `- Metadata: ${wl.metadata}\n` +
      `- Quality: ${wl.quality}\n` +
      `- Transform: ${wl.transform}\n` +
      `- DAG: ${wl.dag}\n\n` +
      `Return JSON: { passed: true/false, issues: [{spec, field, severity, description}] }`,
      { model: 'opus', label: `verify:${wl.workload_name}`, phase: 'Verify' }
    )
    log(`${wl.workload_name}: verification ${verification && verification.includes('"passed": true') ? 'PASSED' : 'ISSUES FOUND'}`)
    return { ...wl, verification }
  },

  // ─── Phase 4.5: Pre-Deploy Validation ────────────────────────────
  async (wl) => {
    if (wl.blocked) return wl
    phase('Pre-Deploy')
    const checks = await parallel([
      () => agent(
        `Validate the silver_spec and gold_spec JSON are well-formed and contain all required fields.\n` +
        `silver_spec required: dataset_name, schema_version, source_table, primary_key, dedup_strategy, quality_threshold\n` +
        `gold_spec required: dataset_name, schema_version, source_table, schema_type, grain, measures\n` +
        `Specs: ${wl.transform}\n` +
        `Report: VALID or list missing fields.`,
        { model: 'haiku', label: `validate-specs:${wl.workload_name}`, phase: 'Pre-Deploy' }
      ),
      () => agent(
        `Security scan: check all generated specs for workload ${wl.workload_name}.\n` +
        `Scan for: hardcoded credentials, AWS account IDs, API keys, secrets.\n` +
        `Specs: ${wl.metadata} ${wl.quality} ${wl.transform} ${wl.dag}\n` +
        `Report: CLEAN or list violations.`,
        { model: 'haiku', label: `security:${wl.workload_name}`, phase: 'Pre-Deploy' }
      )
    ])
    log(`${wl.workload_name}: pre-deploy validation done`)
    return { ...wl, preDeployChecks: checks }
  }
)

return { workloads: results.filter(Boolean) }
```

---

## Step 8: Post-Workflow — Write Files

After the workflow returns, you (the main conversation agent) write the actual files:

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
   - The run_id comes from the Workflow tool result

   This is NON-NEGOTIABLE. CLAUDE.md requires every workload to have `logs/` with traces.

---

## Step 9: Post-Deployment Sequence

After files are written and tests pass, follow CLAUDE.md Steps 5.10 and 5.11:

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
| Workflow tool itself fails | Show error. Offer fallback: "Want me to run this sequentially instead?" |
| User wants to abort mid-workflow | Respect immediately. Partial results are preserved. |
