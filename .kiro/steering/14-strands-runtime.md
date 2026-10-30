---
inclusion: auto
name: adop-strands-runtime
description: >-
  The optional headless AWS Strands runtime for ADOP: scripts/run_strands.py, --dry-run, and the AgentCore deployment target. Load only when asked about running ADOP headlessly, in CI, or on Strands/AgentCore.
---
# Optional ADOP Strands runtime

Kiro can run the headless ADOP workflow through the shared AWS Strands runtime.
This is opt-in and does not replace Kiro's human discovery gate.

```text
python3 scripts/run_strands.py status
python3 scripts/run_strands.py run \
  --args <path-to-onboarding-args.json> \
  --region <aws-region> \
  --model <bedrock-model-id>
```

Use `--dry-run` to verify the orchestration contract without calling Bedrock.
AgentCore is optional and is not required for local or CI execution.

The runtime still requires explicit human discovery answers before any workload
artifact is generated. It uses the existing contracts, renderer, tests,
requirements audit, and trace surfaces.

## Scope and policy enforcement

- **Phase 3 (profile) and Phase 4 (build).** Discovery questions and deploy
  stay in the client.
- **Phase 3** — `python3 scripts/run_strands.py profile --args <args.json>
  --region <region> --model <model-id> --athena-output <s3://human-provided/>`.
  Read-only by construction: fixed `aws_ro_*` tools (Glue `get_*`, S3 list and
  ≤256 KiB sample, Athena single row-capped `SELECT`). Writes candidates only to
  `workloads/<name>/run/source_profile.json`; present them to the human, who
  confirms PK, PII, dedup and thresholds. Only the metadata principal may call
  these tools (Cedar).
- **Phase 4** — `run_strands.py run` (metadata + quality, transform, DAG,
  optional ontology, reviewer) after discovery is complete.
- **Same Cedar policies as Claude Code, Codex and Kiro.** Every Strands agent
  gets a `BeforeToolCallEvent` hook (`runtimes/strands/adop_strands/cedar_hook.py`)
  that calls the shared engine `shared/utils/cedar_gate.py` and cancels any
  tool call `shared/policies/` denies, including `render_artifact` outputs.
  Agents are mapped to principals by name (`adop-build-metadata` -> `metadata`).
- **Mode** follows `shared/policies/enforcement.json` (`audit` logs to
  `logs/cedar_decisions.jsonl`; `enforce` blocks). A gate failure cancels the
  call instead of allowing it.
- The runtime's own tool guards in `tools.py` remain as a second layer.
