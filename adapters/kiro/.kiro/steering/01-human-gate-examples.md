# Human-in-the-Loop Gate — Reinforcement & Examples

The Phase 1 discovery gate is the most important rule in this project. The HUMAN provides transformation rules, quality thresholds, and scheduling. The agent NEVER guesses.

## Correct Behavior

- User: "onboard sales data from S3" → Agent asks about dedup, nulls, quality thresholds, schedule
- Agent sees column "email" → asks "Would you like to dedup by email?" — does NOT auto-generate `dedup_by='email'`
- Agent sees 5% null rate → says "Column X has 5% nulls. How would you like to handle nulls?" — does NOT generate `drop_nulls=True`
- Agent observes daily source updates → asks "What schedule do you want?" — does NOT assume `@daily`
- Agent profiles data and finds outliers → presents findings, asks "What thresholds should I set?"

## Violations (NEVER do these)

- Generating `transformations.yaml` before asking cleaning rules
- Assuming `quality_threshold: 0.95` without user stating it
- Generating a `@daily` schedule because source updates daily
- Writing `dedup_by: email` because a column is named "email"
- Setting `null_handling: drop` because nulls were observed in profiling
- Creating quality rules based on observed data distribution without user input

## When the gate applies

- ANY new workload onboarding
- ANY modification to transformation logic
- ANY change to quality thresholds
- ANY change to scheduling

## The gate is also a hook — and sub-agents cannot satisfy it

Two separate PreToolUse gates enforce this, and they deny on different grounds. Knowing which
one stopped you tells you what to do next.

`phase_gate.py` denies the `subagent` tool until `workloads/{name}/run/context.json` carries
every required `human_answers` field **and** `run/discovery_complete.json` exists. This is the
discovery gate proper. It is addressed to the **orchestrator**, which is the only party that
talks to the human and therefore the only party that can have asked the questions. A
sub-agent cannot satisfy it, because a sub-agent cannot hold the conversation it attests to.

`enforce_template_codegen.py` denies any write under `workloads/{name}/{scripts,dags,sql}/`
**unconditionally** — there is no marker and no escape hatch, because those three directories
are the renderer's exclusive output. `config/` is deliberately *not* covered: specs live there
and have to be writable. Its deny message names the `render.sh` invocation to use instead.

If a gate denies your write:

- **Never fabricate the gate's precondition.** Do not write `run/discovery_complete.json`
  yourself, and do not hand-write a file under `scripts/`, `dags/` or `sql/` by another route.
  Either move converts a guardrail into a no-op for every later write in the workload.
- Return `status: "blocked"` with the gate named in `blocking_issues`.
- Existing answers in `run/context.json` are **not** a substitute for the completion marker.
  They may be complete, but the marker records that the orchestrator verified them — that is
  the orchestrator's call, not yours.
- If you were denied by `enforce_template_codegen.py`, the fix is a spec in `config/` plus a
  render, never an edit to the output.

## When the gate does NOT apply

- Fixing a bug the user described (user already stated what to change)
- Answering questions about architecture or existing workloads
- Reading/summarizing existing workload configs
- Running tests or profiling existing data (read-only operations)
- Deploying already-approved artifacts (Phase 5)
