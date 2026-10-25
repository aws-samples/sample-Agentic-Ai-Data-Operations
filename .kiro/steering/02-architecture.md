# Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MCP SERVERS (set up FIRST — before any phase)                              │
│                                                                             │
│  aws-mcp by default                       full inventory on Gateway          │
│                                                                             │
│  DEFAULT:  aws-mcp                                                         │
│  DEMO:     glue-athena, lakeformation, iam, pii-detection, cloudtrail       │
│  OPTIONAL: remaining specialized servers                                   │
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
  access — enforced by the `tools` list in `.kiro/agents/*.json`, not by convention.
  The ontology agent is file-only and has no MCP/AWS access; the orchestrator must profile or
  otherwise stage the confirmed Gold schema before invoking it.
- **Demo profile**: Run `python3 scripts/mcp_demo.py check --profile demo` before
  a live demonstration. Do not block on the unused 13-server inventory.
- **Agent model**: Data Onboarding Agent = main conversation. Metadata, Transformation,
  Quality, DAG, Ontology = sub-agents defined in `.kiro/agents/` and spawned by name via the
  `Agent` tool. Sub-agents cannot spawn peers (no `Agent`/`SendMessage` in their toolset).
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
