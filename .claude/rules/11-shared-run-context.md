# Shared Run Context

Sub-agents get a fresh context window, so the run's shared state lives on disk under
`workloads/{name}/run/`, not in a prompt.

**Before generating anything**, read both:

- `run/context.json` — validated against `contracts/v1/run_context.schema.json`
- `run/decisions.jsonl` — append-only reasoning from agents that ran before you

`human_answers` in `context.json` is **authoritative**. If it disagrees with a value
interpolated into your prompt, the file wins — the prompt may be a paraphrase.

**Before returning**, append each of your decisions as one JSON line to
`run/decisions.jsonl` (same shape as `AgentOutput.decisions[]`). Append only; never
rewrite the file — agents can run in parallel.

The orchestrator writes `context.json` once at the end of Phase 2 and treats it as
read-only afterwards. Load and validate with
`shared.codegen.spec_loader.load_spec(path, "run_context")`, which returns
`(spec, spec_hash)` — unpack the tuple.

## Translating `human_answers` into a spec

`human_answers` holds the human's own words. The spec schemas are structured, so a
translation step is unavoidable:

| `human_answers` (free-form) | spec field (structured) |
|---|---|
| `dedup_strategy` — a sentence | `silver_spec.dedup_strategy` — enum `keep_latest` / `keep_first` / `none` |
| `null_handling` — a sentence | `silver_spec.null_handling` — `{strategy, critical_columns, fill_values}` |
| `schedule` + `schedule_timezone` | `dag_spec.schedule` — `{cron, timezone, ...}` (both required) |

That translation is the one place a sub-agent can silently overwrite a human decision, so:

1. **Record it.** Append a decision to `run/decisions.jsonl` naming the source sentence and
   the enum/object you mapped it to. The mapping must be auditable.
2. **Never widen it.** "quarantine rows missing member_id" means
   `{strategy: "quarantine", critical_columns: ["member_id"]}` — not `critical_columns` for
   every column that happens to have nulls.
3. **Escalate rather than guess.** If the sentence does not map cleanly onto an allowed value,
   or the answer you need is absent (`schedule_timezone` is a common one — `timezone` is
   required by `dag_spec`), stop and return `status: "blocked"` with the question in
   `blocking_issues`. Do not pick a plausible default; that is a Phase 1 gate violation.
