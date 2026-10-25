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

`.claude/hooks/check-discovery-gate.sh` denies any `Write`/`Edit` under
`workloads/{name}/{config,scripts,dags,sql}/` for a workload that has neither
`config/source.yaml` nor a `.discovery_complete` marker.

Its deny message ends with "create `workloads/{name}/.discovery_complete` to proceed". **That
instruction is addressed to the orchestrator**, which is the only party holding
`AskUserQuestion` and therefore the only party that can have asked the five questions. Every
sub-agent is launched without `AskUserQuestion` (the harness strips it regardless of
frontmatter), so a sub-agent that creates the marker is asserting a human conversation that
never happened.

If you are a sub-agent and this hook denies your write:

- **Do NOT create `.discovery_complete`.** Creating it converts a guardrail into a no-op for
  every later write in the workload.
- Return `status: "blocked"` with the gate named in `blocking_issues`.
- Existing answers in `run/context.json` are **not** a substitute. They may be complete, but
  the marker records that the orchestrator verified them — that is the orchestrator's call.

## When the gate does NOT apply

- Fixing a bug the user described (user already stated what to change)
- Answering questions about architecture or existing workloads
- Reading/summarizing existing workload configs
- Running tests or profiling existing data (read-only operations)
- Deploying already-approved artifacts (Phase 5)
