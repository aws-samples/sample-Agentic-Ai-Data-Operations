---
name: decision-engine
description: The ADOP "AI clone" Decision Engine and guardrails. Load this whenever generating or promoting a data pipeline to encode the organization's architecture standards, tool-routing preferences, Cedar authorization policies, and the mandatory invariants. It governs HOW agents pick tools and what they are never allowed to do — so every builder produces a consistent architecture instead of a different one per engineer.
---

# Decision Engine + Guardrails

The Decision Engine is an **AI-encoded version of your enterprise architect**: it embeds the
org's guidelines, tech standards, and design philosophy into the build so the model *fills in
the blueprint, it doesn't draw it*. Fill in `config/` below with your org's real values; the
defaults are sane starting points.

## Configuration layers

| File (in `config/`) | Role |
|---------------------|------|
| `TOOL_ROUTING.md` | Intent-to-tool mapping — matches NL intent to a tool, with `not_when` disqualifiers |
| `servers.yaml` | Single source of truth for MCP servers — category, tools, fallbacks |
| `invariants.yaml` | Mandatory rules (BLOCK/WARN) enforced regardless of phase |
| `standards.md` | Architecture constraints — org tech choices, sub-agent limits, MCP-first rule |

## 5-step tool selection hierarchy

```
User Intent → 1: Context Gate → 2: Server Health → 3: Intent Match → 4: Fallback → 5: Invariants
```

1. **Context Gate** — *Am I a sub-agent?* If YES → STOP: generate files only, no MCP/AWS/CLI.
   If NO (orchestrator) → proceed. Enforced by Cedar policy + the `sub-agent-no-mcp` invariant.
2. **Server Health** — classify tools REQUIRED / WARN / OPTIONAL. REQUIRED failure = block;
   WARN = CLI fallback + log; OPTIONAL = skip gracefully.
3. **Intent Match** — match the operation to an intent entry in `TOOL_ROUTING.md`; honor the
   `not_when` negative filter.
4. **Fallback** — MCP first, always. If unavailable and REQUIRED → block + escalate to human;
   else CLI fallback + logged warning.
5. **Invariant Enforcement** — the rules below apply to *every* operation no matter what tool
   was chosen.

## Mandatory invariants (starter set)

| ID | Rule | Severity |
|----|------|----------|
| `lineage-always` | `--enable-data-lineage: true` on every Glue ETL job | BLOCK |
| `no-credentials-in-code` | Credentials via Secrets Manager / Airflow Connections only | BLOCK |
| `bronze-immutable` | Bronze data never modified after ingestion | BLOCK |
| `quality-gates` | Silver ≥ 80%, Gold ≥ 95%; critical failures block promotion | BLOCK |
| `sub-agent-no-mcp` | Sub-agents generate artifacts only; no MCP/AWS execution | BLOCK |
| `verify-deployment` | Confirm tables queryable after deploy | BLOCK |
| `audit-after-deploy` | Confirm audit logging active after deploy | BLOCK |
| `zone-scoped-kms` | Separate CMK for Bronze, Silver, Gold per workload | BLOCK |
| `mcp-first` | Use MCP tools first; CLI only when unavailable/errored | BLOCK |
| `log-cli-fallback` | Print a warning on every CLI fallback | WARN |

## How to use during a build
- **Sub-agents**: obey the Context Gate — you are always in the "generate files only" branch.
- **Orchestrator**: before any infra action, walk steps 2–5 and confirm no BLOCK invariant is
  violated. If one is, stop and surface it to the human.
- Keep the org's real preferences in `config/` (e.g. "prefer Athena over Redshift for ad-hoc",
  "PII operations must use designated KMS keys", cost thresholds, failover order). The clone
  applies them consistently so the same pipeline behaves the same across environments.

See `config/` for editable starter files.
