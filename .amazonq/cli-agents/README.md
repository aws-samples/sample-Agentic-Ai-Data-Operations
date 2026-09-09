# .amazonq/cli-agents — ADOP agent profiles for Amazon Q Developer CLI

Phase 3 of the ADOP → Amazon Q Developer CLI migration (see
`ADOP-to-AmazonQ-Migration-Design.md`, Sections 5.1 and 5.3). Nine agent
profiles replace Claude Code's `Agent`-tool sub-agents and the `Workflow`-DSL
roles. Each file's name (minus `.json`) is the agent name; invoke with
`q chat --agent <name>`.

## Roster

| Agent | Role | Tools | MCP | Writes files | Hooks |
|---|---|---|---|---|---|
| `adop-orchestrator` | Human-facing orchestrator; runs discovery gate, spawns build agents, gates on tests, renders, deploys | fs_read, fs_write, execute_bash | all 13 | yes | full |
| `adop-router` | First responder; read-only check of `workloads/` to route | fs_read | none | no | none |
| `adop-build-metadata` | schema/PII catalog → `config/source.yaml`, `semantic.yaml` | fs_read, fs_write, execute_bash | none | yes | full |
| `adop-build-transform` | silver/gold specs → rendered Glue ETL scripts | fs_read, fs_write, execute_bash | none | yes | full |
| `adop-build-quality` | `config/quality.yaml` + checks | fs_read, fs_write, execute_bash | none | yes | full |
| `adop-build-dag` | Airflow DAG | fs_read, fs_write, execute_bash | none | yes | full |
| `adop-build-ontology` | OWL2 + R2RML staging | fs_read, fs_write, execute_bash | **`@glue-athena/get_table` only** | yes | full |
| `adop-devops` | IaC, monitoring, cost, runbook + IaC security review | fs_read, fs_write, execute_bash | 6 (cloudwatch, cost-explorer, cloudtrail, core, iam, lambda) | yes | logging + log |
| `adop-reviewer` | Adversarial PR security review → findings file | fs_read, fs_write, execute_bash (git only) | none | findings only | none |

## How the two BLOCK invariants are enforced (design intent)

**`mcp-first`** — no agent lists `use_aws` in its `tools` array. Q Developer CLI's
generic `use_aws` tool is simply never offered, so the model cannot bypass the
purpose-built MCP tools. This is the confirmed correct mitigation from the
migration design 5.3 (an empty `allowedServices` would NOT suffice — the tool
schema would still be visible). Genuine CLI fallback runs through `execute_bash`
with an allowlist (`aws ...` is allowed on the orchestrator/devops, denied on
build agents), so it stays visible and auditable.

**`sub-agent-no-mcp`** — the five build sub-agents set `useLegacyMcpJson: false`
and declare no `mcpServers`, so they load zero MCP servers. The one exception is
`adop-build-ontology`, which the design explicitly permits a single read tool
(`glue-athena get_table`); it declares only that server and grants only that one
tool.

## Correction applied vs. the design doc (Major finding)

Migration design 5.3 says build sub-agents should have "only `fs_read` and a
path-scoped `fs_write` — no `execute_bash`." Taken literally that **deadlocks**
them: SKILLS.md requires every sub-agent to run its own tests
(`pytest ... fix and re-run`) and CLAUDE.md requires artifacts to be produced by
`shared.codegen.renderer.render()` — both need local code execution, and a direct
`fs_write` to `scripts/dags/sql` is blocked by the `enforce_template_codegen`
hook without the renderer token. `sub-agent-no-mcp` forbids **MCP/AWS execution**,
not **local code execution**.

So each build agent keeps `execute_bash` but constrains it with
`toolsSettings.execute_bash`: `denyByDefault: true`, `allowedCommands` limited to
`pytest` and `python3 -m/-c shared.codegen…` (ontology also `shared…`), and
`deniedCommands` blocking `aws`, `q chat`, `rm -rf`, `curl`, `wget`. Result:
sub-agents can render and test, but cannot touch AWS or spawn further agents.

## allowedTools / --trust-tools vs. toolsSettings

Constrained tools (`fs_write`, `execute_bash`) are deliberately **kept out of**
`allowedTools`, and the driver trusts **only `fs_read`** via `--trust-tools`.
Verified against q CLI v1.19.7: putting a tool in `allowedTools` **or** passing it
to `--trust-tools` OVERRIDES its `toolsSettings` patterns (full trust) — the CLI
even prints `WARNING: You have trusted fs_write tool, which overrides the
toolsSettings: allowedPaths`. We rely instead on `toolsSettings` allow/deny lists
with `denyByDefault`, which auto-approve only the listed commands/paths (no prompt)
and fail closed on anything else under `--no-interactive`. Only `fs_read` (trusted
by default) and the single ontology MCP read tool appear in `allowedTools`.

Hooks are independent of trust: a `preToolUse` gate blocked a write on live `q`
even when `fs_write` was trusted, so the discovery/codegen/logging gates hold
regardless of the trust list.

## Hook wiring

Every write-capable workload agent (orchestrator + 5 build agents) carries the
full Phase 2 hook block (3 `preToolUse` gates + 1 `postToolUse` logger); see
`.amazonq/hooks/README.md`. `adop-devops` carries the logging hook + conversation
logger (it writes IaC/monitoring/runbooks, not template-gated ETL, so the
discovery-gate and codegen hooks would be no-ops). `adop-router` (read-only) and
`adop-reviewer` (writes only a findings file) carry no hooks.

## Open items (not resolved here)

1. **Model routing / the `model` field is intentionally omitted from every
   profile.** Q Developer CLI model IDs look like `claude-sonnet-4` (not the
   `haiku`/`sonnet`/`opus` tiers the old `Workflow` DSL used), and the
   per-invocation `--model` flag is unverified against Q CLI source (migration
   design Appendix 7.2 lists the flags it *did* verify; `--model` is not among
   them). Recommended tiers to apply once IDs are confirmed via `/model`:
   router/health/validation = cheapest; build agents = mid-tier, or strongest for
   HIPAA/SOX/PCI; `adop-reviewer` and the verify step = strongest. Set either the
   static `model` field per agent or pass per-invocation if the CLI supports it.
2. **`fs_write` tool_input shape** is assumed by the hooks (see
   `.amazonq/hooks/README.md`); confirm against the running CLI.
3. **The SKILLS.md ↔ CLAUDE.md contradiction** ("sub-agents write artifacts" vs.
   "sub-agents produce specs and call the renderer") is carried into the prompts
   as: build agents render via the renderer and write only non-gated artifacts
   (configs, tests) directly. Reconcile the source SKILLS.md prompt wording when
   convenient.

## Orchestration (Phase 4, not built here)

`adop-orchestrator` spawns each build agent as a non-interactive subprocess, e.g.
`q chat --agent adop-build-metadata --no-interactive --trust-tools=fs_read,fs_write,execute_bash "<task+context>"`.
Sequential phases are sequential calls; parallel phases are backgrounded shell
jobs joined with `wait`. Success is judged only by the schema-validated
`AgentOutput` handoff or the written files — never by parsing chat stdout. The
external driver that sequences these is Phase 4 follow-on work.
