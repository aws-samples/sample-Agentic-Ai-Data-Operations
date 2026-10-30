# Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MCP SERVERS (set up FIRST — before any phase)                              │
│                                                                             │
│  aws-mcp by default                       full inventory on Gateway          │
│                                                                             │
│  REQUIRED: aws-mcp, lakeformation, iam  (block if down)                     │
│  WARN:     cloudtrail, redshift, core, s3-tables, pii-detection             │
│  OPTIONAL: sagemaker-catalog, lambda, cloudwatch, cost-explorer, dynamodb   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ all phases use MCP tools
                                 ▼
MAIN CONVERSATION
├── Router (inline) — check workloads/, found or not found
└── Data Onboarding Agent (orchestrator, human-facing)
    │
    │  Phase 0: Health Check & Auto-Detect (read-only, always first)
    │  Phase 1-2: inline (questions, dedup, validation) — HUMAN-IN-THE-LOOP
    │  Phase 3-4: spawns sub-agents → TEST GATE after each
    │  Phase 5: Deploy artifacts to AWS (uses MCP tools)
```

## Key Rules

- **MCP-First**: All AWS operations use MCP server tools first. Sub-agents do NOT have MCP
  access — enforced by `includeMcpJson: false` plus a `permissions.rules` deny on the `mcp`
  capability in `.kiro/agents/*.json`, not by convention. A `deny` rule wins over any `allow`,
  so this holds even if the `tools` list is later widened.
  The ontology agent is file-only and has no MCP/AWS/shell access; the orchestrator must
  profile or otherwise stage the confirmed Gold schema before invoking it.
- **Demo profile**: Run `python3 scripts/mcp_demo.py check --profile demo` before
  a live demonstration. Do not block on the unused 13-server inventory.
- **Enabling a specialized server**: Kiro reads `.kiro/settings/mcp.json` only. The entries in
  `.kiro/settings/mcp.optional.json` are inert until you copy the one you need into
  `mcp.json`; there is no merge step and no profile switch. Third-party providers
  (Snowflake, Databricks, Teradata) carry `"disabled": true` and require provider
  authentication, a tool allowlist, and a Phase 0 health check before use.
- **Agent model**: Data Onboarding Agent = main conversation. Metadata, Transformation,
  Quality, DAG, Ontology = sub-agents defined in `.kiro/agents/` and spawned by name via
  Kiro's built-in `subagent` tool. Sub-agents cannot spawn peers — a `permissions.rules` deny
  on the `subagent` capability enforces that, so peer spawning fails at the harness rather
  than relying on the prompt.
- **Shared state**: sub-agents get a fresh context window; the run's shared state lives on
  disk in `workloads/{name}/run/`. See `.kiro/steering/11-shared-run-context.md`.
- **Test gates**: Every sub-agent writes + passes tests before proceeding.
- **Deployment topology**: Default single-account. Multi-account opt-in via `docs/multi-account-deployment.md`.

## Phase Flow

0. Health Check → 1. Discovery (ASK USER) → 2. Dedup/Validate → 3. Profile → 4. Build (sub-agents + test gates) → 5. Deploy (MCP)

## Semantic Layer

- SageMaker Catalog for business metadata (custom columns on Glue entries)
- `config/semantic.yaml` → local source of truth
- `config/ontology.ttl` + `config/mappings.ttl` → OWL + R2RML for AWS Semantic Layer handoff
- ADOP emits ontology artifacts only. NL→SQL, SHACL, VKG = AWS Semantic Layer's responsibilities.

## Cedar Policy Enforcement

Every tool call on Claude Code, Codex and Kiro is evaluated against the Cedar
policies in `shared/policies/` by the `cedar_gate.py` PreToolUse hook
(engine: `shared/utils/cedar_gate.py`, real cedarpy, fails closed).

- **Principal:** the subagent's `agent_type` (Claude Code, Codex) or the
  agent's own `--principal` hook argument (Kiro). Main conversation =
  `onboarding`. Any non-ADOP agent = `general`.
- **Agents** may write only their documented outputs
  (`shared/policies/agent_authorization/*.cedar`). Sub-agents cannot call
  MCP/AWS tools or the `aws` CLI (the ontology agent keeps `get_table`).
- **No agent, including the main conversation, may write `shared/policies/**`
  or `run/deploy_gate.json`.** Policy changes are made by a human.
- **SEC-001:** writing a hardcoded secret is denied for everyone.
- **Mode:** `shared/policies/enforcement.json` — `audit` logs to
  `logs/cedar_decisions.jsonl` and blocks nothing; `enforce` blocks. Only a
  human switches it.
- Pipeline guardrails (DQ/INT/OPS, SEC-002..004) are evaluated by the pipeline
  at run time, not at tool-call time.
