# Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MCP SERVERS (set up FIRST — before any phase)                              │
│                                                                             │
│  Default: aws-mcp (.mcp.json)       Demo: aws-mcp + 4 specialized servers    │
│  Optional: specialized profiles     Gateway: full inventory when deployed   │
│                                                                             │
│  Block only when a capability required by the current phase is unavailable.  │
│  Use scripts/mcp_demo.py for the live demo readiness check.                 │
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
  access — enforced by the `tools` frontmatter in `.claude/agents/*.md`, not by convention.
  One exception: `ontology-agent` holds `mcp__glue-athena__get_table` (read-only) to fetch the
  Gold-zone schema.
- **Agent model**: Data Onboarding Agent = main conversation. Metadata, Transformation,
  Quality, DAG, Ontology = sub-agents defined in `.claude/agents/` and spawned by name via the
  `Agent` tool. Sub-agents cannot spawn peers (no `Agent`/`SendMessage` in their toolset).
- **Shared state**: sub-agents get a fresh context window; the run's shared state lives on
  disk in `workloads/{name}/run/`. See `.claude/rules/11-shared-run-context.md`.
- **Test gates**: Every sub-agent writes + passes tests before proceeding.
- **Deployment topology**: Default single-account. Multi-account opt-in via `docs/multi-account-deployment.md`.

## Phase Flow

0. Health Check → 1. Discovery (ASK USER) → 2. Dedup/Validate → 3. Profile → 4. Build (sub-agents + test gates) → 5. Deploy (MCP)

## Semantic Layer

- SageMaker Catalog for business metadata (custom columns on Glue entries)
- `config/semantic.yaml` → local source of truth
- `config/ontology.ttl` + `config/mappings.ttl` → OWL + R2RML for AWS Semantic Layer handoff
- ADOP emits ontology artifacts only. NL→SQL, SHACL, VKG = AWS Semantic Layer's responsibilities.
