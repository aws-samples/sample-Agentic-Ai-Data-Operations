# Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MCP SERVERS (set up FIRST — before any phase)                              │
│                                                                             │
│  Local mode (.amazonq/mcp.json, stdio)  OR  Gateway mode (Agentcore)        │
│  13 servers on laptop                        13 servers on Agentcore Gateway │
│                                                                             │
│  REQUIRED: glue-athena, lakeformation, iam  (block if down)                 │
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

- **MCP-First**: All AWS operations use MCP server tools first. Sub-agents do NOT have MCP access.
- **Agent model**: Data Onboarding Agent = main conversation. Metadata, Transformation, Quality, DAG = sub-agents. On Amazon Q Developer CLI, sub-agents are separate `cli-agents/*.json` profiles invoked as non-interactive subprocesses (`q chat --agent <name> --no-interactive`) rather than via an in-model `Agent` tool.
- **Test gates**: Every sub-agent writes + passes tests before proceeding.
- **Deployment topology**: Default single-account. Multi-account opt-in via `docs/multi-account-deployment.md`.

## Phase Flow

0. Health Check → 1. Discovery (ASK USER) → 2. Dedup/Validate → 3. Profile → 4. Build (sub-agents + test gates) → 5. Deploy (MCP)

## Semantic Layer

- SageMaker Catalog for business metadata (custom columns on Glue entries)
- `config/semantic.yaml` → local source of truth
- `config/ontology.ttl` + `config/mappings.ttl` → OWL + R2RML for AWS Semantic Layer handoff
- ADOP emits ontology artifacts only. NL→SQL, SHACL, VKG = AWS Semantic Layer's responsibilities.
