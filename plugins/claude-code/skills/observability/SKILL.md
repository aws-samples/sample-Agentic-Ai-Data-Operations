---
name: observability
description: ADOP's shared run context, tracing contract and error taxonomy. Load this before generating any pipeline artifact, before returning from a sub-agent, and when deciding whether a failure should be retried, escalated to the human, or halt the run. Defines run/context.json and run/decisions.jsonl, the three trace layers linked by run_id, the prose-to-spec translation rules that stop a sub-agent silently overwriting a human decision, and the decisions record every sub-agent owes the orchestrator. A pipeline with no trace is not finished.
---

# Observability — shared run context, tracing, and error handling

Derived from `.claude/rules/07-error-logging.md` and `.claude/rules/11-shared-run-context.md`
in the ADOP repository. Those are always in context in a checkout; here they load on demand, so
read this before generating artifacts rather than after.

## Shared run context — sub-agents get a fresh context window

The run's shared state lives on disk under `workloads/{name}/run/`, not in a prompt. **Before
generating anything**, read both:

- `run/context.json` — validated against `lib/contracts/v1/run_context.schema.json`
- `run/decisions.jsonl` — append-only reasoning from agents that ran before you

Load and validate it through the renderer CLI's library, unpacking the tuple:

```python
from shared.codegen.spec_loader import load_spec       # lib/ is on sys.path via the CLI
spec, spec_hash = load_spec(path, "run_context")
```

`human_answers` in `context.json` is **authoritative**. If it disagrees with a value
interpolated into your prompt, the file wins — the prompt may be a paraphrase.

**Before returning**, append each of your decisions as one JSON line to
`run/decisions.jsonl`, in the same shape as `AgentOutput.decisions[]`. Append only; never
rewrite the file — agents can run in parallel.

The orchestrator writes `context.json` once at the end of Phase 2 and treats it as read-only
afterwards.

## Translating `human_answers` into a spec — the one place a human decision can be lost

`human_answers` holds the human's own words. The spec schemas are structured, so a translation
step is unavoidable:

| `human_answers` (free-form) | spec field (structured) |
|---|---|
| `dedup_strategy` — a sentence | `silver_spec.dedup_strategy` — enum `keep_latest` / `keep_first` / `none` |
| `null_handling` — a sentence | `silver_spec.null_handling` — `{strategy, critical_columns, fill_values}` |
| `schedule` + `schedule_timezone` | `dag_spec.schedule` — `{cron, timezone, ...}`, both required |

That translation is the one place a sub-agent can silently overwrite a human decision, so:

1. **Record it.** Append a decision to `run/decisions.jsonl` naming the source sentence and the
   enum or object you mapped it to. The mapping must be auditable.
2. **Never widen it.** "quarantine rows missing member_id" means
   `{strategy: "quarantine", critical_columns: ["member_id"]}` — not `critical_columns` for
   every column that happens to have nulls.
3. **Escalate rather than guess.** If the sentence does not map cleanly onto an allowed value,
   or the answer you need is absent (`schedule_timezone` is a common one — `timezone` is
   required by `dag_spec`), stop and return `status: "blocked"` with the question in
   `blocking_issues`. Do not pick a plausible default; that is a Phase 1 gate violation.

## Three trace layers, linked by `run_id`

| Layer | What it records | Produced by |
|-------|-----------------|-------------|
| 1. Orchestrator | phase transitions, test gates, retries | `OrchestratorLogger` + `AgentTracer` |
| 2. Generated scripts | row counts, transforms, quality scores | `StructuredLogger` inside the ETL |
| 3. LLM self-reporting | reasoning, alternatives, confidence | the `decisions` array in `AgentOutput` |

Rules:

- Every pipeline run MUST produce a `trace_events.jsonl` via `AgentTracer`.
- Every sub-agent MUST include a `decisions` array in its `AgentOutput`.
- Every generated ETL script MUST use `StructuredLogger` for its structured output.
- Every trace event carries three surfaces: **operational** (what), **cognitive** (why),
  **contextual** (where).
- CloudTrail stays enabled for Lake Formation operations — the audit trail for data access and
  PII tag changes.

The modules are vendored with this plugin and importable once `lib/` is on `sys.path`, which
`scripts/adop_render.py` does:

```
lib/shared/logging/agent_tracer.py        lib/shared/utils/structured_logger.py
lib/shared/logging/trace_viewer.py        lib/shared/utils/orchestrator_logger.py
                                          lib/shared/utils/script_tracer.py
```

If your organisation has a house logger, wire it in at layer 2 rather than adopting ADOP's —
the contract is the three layers and the `run_id` linkage, not these specific classes.

## Error taxonomy — what a failure means

| Category | Examples | Action |
|---|---|---|
| **Retryable** | network timeout, API throttling, transient S3 error | retry with exponential backoff, max 3 attempts |
| **Fixable** | schema mismatch, missing config, quality below threshold | ask the human for a correction |
| **Fatal** | invalid credentials, source permanently offline, data corruption | halt the pipeline, alert the human immediately |

Never silently swallow an error. Log the full context — agent, operation, input summary, error
type — and escalate to the matching category. A sub-agent that cannot proceed returns
`status: "blocked"` with the reason in `blocking_issues`; it does not improvise a way forward.

## Stage output

Every phase and numbered step announces itself with an ASCII block built by
`shared.utils.ascii_display`, never hand-drawn, so terminal output and `trace_events.jsonl` stay
identical at width 70.

- default banner + summary → `stage_block(title, lines)`
- auto-discovered findings → `discovery_block(title, findings)`
- gates and checklists → `checklist_block(title, [(passed, name)])`
- ontology entities → `entity_block(entities)`
- Q&A → `exchange_block(...)`, already emitted by `AgentTracer.log_exchange`

Title format is `PHASE {n} - {NAME}` or `STEP {n.n} - {NAME}`, uppercase, pure ASCII
(`+ - | *`) only:

```text
+--------------------------------------------------------------------+
|  STEP 2.1 - DUPLICATE DETECTION                                    |
+--------------------------------------------------------------------+
|  * Scanned 3 workloads under workloads/                            |
|  * No source overlap found                                         |
|  * Proceeding to Step 2.2 connectivity check                       |
+--------------------------------------------------------------------+
```

Unicode box diagrams that appear in prompts are reference material to read, not output to emit.
