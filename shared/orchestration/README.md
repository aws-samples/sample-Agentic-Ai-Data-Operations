# shared/orchestration — ADOP driver for Amazon Q Developer CLI

Phase 4 of the ADOP → Amazon Q Developer CLI migration (see
`ADOP-to-AmazonQ-Migration-Design.md` Section 5.1). This is the external driver
that replaces Claude Code's `Workflow`-tool DSL (`phase()`, `agent()`,
`parallel()`, `pipeline()`), which has no equivalent on Q Developer CLI.

## What it does

`WorkflowDriver` (in `workflow_driver.py`) sequences the build sub-agents by
shelling out to `q chat --agent <name> --no-interactive` per phase:

- **Sequential phases** → sequential `run_gated()` calls.
- **Parallel phases** (old `parallel([...])`) → `run_parallel()` (threaded
  subprocess fan-out + join).
- **Test gates** → `run_tests()` runs pytest; the gate is pytest's **exit code**.
- **Retries/escalation** → `run_gated()` retries up to `max_attempts`, appending
  the prior failure reason to the task, then escalates via `OrchestratorLogger`.
- **Tracing** → reuses the repo's `OrchestratorLogger`/`AgentTracer`, so runs
  land in `workloads/{name}/logs/{datetime}_{name}.jsonl` exactly as before.

The default `run_build()` sequence mirrors `onboard-workflow.md`: metadata +
quality in parallel (shared gate), then transform, then DAG, then optional
ontology, then the adversarial reviewer.

## The control-flow contract (why this is safe)

Headless `q chat` emits plain conversational text with no structured output.
The driver therefore **never parses agent stdout to decide control flow**.
Success is judged only by artifacts the agent wrote:

- **Build agents** write their `AgentOutput` JSON to
  `workloads/{wl}/.handoffs/{agent}.json`. The driver deletes any stale handoff
  first, then after the subprocess exits reads and validates it via
  `AgentOutput.from_json` and checks `status`/`blocking_issues`. Missing or
  invalid handoff = failure.
- **The reviewer** can't write to `.handoffs/` (its `fs_write` is scoped to
  `reviews/`), so it is *file-judged*: success = `reviews/security-findings.md`
  exists and contains no `Severity: High` marker.

stdout is captured only as `AgentResult.stdout_tail` for logging/debugging.

## Safety

- Sub-agents are launched with an **argv list, not a shell string** (no
  `shell=True`), so the task prompt cannot inject shell commands.
- The driver adds no AWS capability; each agent's own `cli-agents/*.json` remains
  the source of truth for tools, and `--trust-tools` only ever names a subset of
  what that agent already allows.

## Usage

```bash
# Real run (requires q CLI on PATH, MCP servers configured, tests present):
python3 -m shared.orchestration.workflow_driver \
  --args path/to/args.json --repo-root . --ontology

# Offline dry-run (fakes q + pytest; exercises the full sequence/gates):
python3 -m shared.orchestration.workflow_driver \
  --args path/to/args.json --repo-root . --dry-run \
  --model-top claude-opus-4 --model-standard claude-sonnet-4
```

`args.json` is the onboard-workflow args object (see `onboard-workflow.md`
Step 4): `workload_name`, `regulation`, `source`, `primary_key`, `pii_columns`,
`transformations`, `quality`, `schedule`, `gold_format`, `ontology`, …

As a library:

```python
from shared.orchestration import WorkflowDriver, build_default_tasks
driver = WorkflowDriver("customer_master", run_id, model_map={"top": "claude-opus-4"})
results = driver.run_build(build_default_tasks(args_obj), ontology=True)
driver.logger.pipeline_summary()
```

## Model routing

`build_model_for_regulation()` maps HIPAA/SOX/PCI → the `"top"` tier and
everything else → `"standard"`. Both tiers resolve through a `model_map` of
concrete Q CLI model IDs (e.g. `claude-opus-4`, `claude-sonnet-4`). When
`model_map` is empty (default), **no `--model` flag is passed** and each agent
uses the CLI default — because the per-invocation `--model` flag is unverified
against Q CLI source (migration design Appendix 7.2). Confirm available IDs with
`/model` and populate `--model-top` / `--model-standard` before relying on
per-phase routing.

## Trust model (verified against q CLI v1.19.7)

The driver trusts **only `fs_read`** via `--trust-tools`. Confirmed live:
trusting `fs_write`/`execute_bash` OVERRIDES their `toolsSettings` sandbox
(`allowedPaths` / `allowedCommands`). Trusting only `fs_read` lets each agent's
`toolsSettings` auto-approve its scoped writes and pytest/renderer commands
without a prompt, while anything outside those allowlists gets no auto-approval
and fails closed under `--no-interactive`. Hooks fire regardless of trust, so the
discovery/codegen/logging gates enforce either way (verified: a `preToolUse` gate
blocked a write even with `fs_write` trusted).

## Verified against a live q CLI (v1.19.7)

- `--agent`, `--no-interactive`, `--trust-tools`, and `--model` all exist (the
  `--model` flag resolves the design-doc Appendix 7.2 "unverified" note — per-
  invocation model routing is supported).
- All 9 `cli-agents/*.json` pass `q agent validate`.
- The `fs_write` `tool_input` shape is `{command, path (absolute), file_text}`;
  the hooks' `.tool_input.path` / `.tool_input.file_text` extraction is correct.

## Not included

- Phases 0–2 (health check, dedup, discovery) stay in the human-facing
  `adop-orchestrator` conversation — the discovery gate is interactive by design.
- Phase 5 (Deploy) and the post-deploy 5.9–5.11 sequence remain MCP operations
  the orchestrator performs directly.
- End-to-end run of the driver against real `q` subprocesses (Phase 5 parity)
  still needs AWS credentials for the MCP-backed phases.
```
