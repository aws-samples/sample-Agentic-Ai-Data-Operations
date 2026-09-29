# ADOP — Claude Code plugin

Describe a data source in natural language and get a tested Bronze→Silver→Gold pipeline —
PySpark ETL, data-quality checks, an Airflow DAG or Step Functions machine, an OWL semantic
layer — with compliance controls applied while it is built rather than reviewed afterwards.

This packages the [Agentic Data Operations Platform](https://github.com/aws-samples/sample-Agentic-Ai-Data-Operations)
so it works **in your own repository**. Without it you would clone ADOP and work inside the
clone; with it, `/adop:onboard-workflow` generates pipelines into whatever repo you are already
in.

## Install

```
/plugin marketplace add aws-samples/sample-Agentic-Ai-Data-Operations
/plugin install adop@adop-marketplace
```

From a local clone instead, run this at the repository root:

```
/plugin marketplace add ./
/plugin install adop@adop-marketplace
```

Then check it loaded. `claude plugin list` is the only command that reports load status —
`validate` checks the manifest schema and `details` lists components read from disk, and both
will happily describe a plugin that failed to load:

```
claude plugin list        # adop@adop-marketplace   ✔ enabled
```

### Requirements

Python 3.10+ with `jinja2`, `jsonschema` and `pyyaml` for the renderer. Add `boto3` for the four
modules that call AWS — source profiling, PII tagging and post-deployment verification. AWS
credentials via the standard chain; the plugin does not set `AWS_PROFILE`, so your own selection
applies.

## Design principle: agents in dev, artifacts in prod

ADOP is a build-time accelerator, not a runtime dependency. Agents reason and generate during
development; what ships to production is deterministic artifacts — PySpark, SQL, DAGs, IAM and
Cedar policies. **Production runs the artifacts without calling a model**, so pipelines stay
auditable and cost-predictable.

That is enforced, not asserted. Every artifact under `workloads/*/{scripts,dags,sql}/` comes from
the vendored renderer and carries a five-line provenance header:

```python
# spec_hash: 85817c6b69bb6397...
# template_id: silver_transform
# template_hash: 270b6c620017cf1f...
# schema_version: v1
# rendered_at: 2026-09-29T00:00:00Z
```

A `PreToolUse` hook refuses direct writes to those directories, and the same spec plus the same
`--rendered-at` reproduces byte-identical output, so a hand edit is detectable.

## Commands

**`/adop:onboard-workflow [REGULATION] <description>`** — the full flow. Phase 1 discovery runs in
conversation and asks about source, primary key, PII, cleaning rules, quality thresholds and
schedule; nothing is generated until those are answered. Then a Dynamic Workflow profiles the
source, fans out to sub-agents, gates on quality, and lands a tested pipeline under
`workloads/<name>/`. A regulation prefix (`GDPR`, `CCPA`, `HIPAA`, `SOX`, `PCI`) applies that
framework's controls during the build.

**`/adop:devops-workflow <workload> [cloudformation|terraform|cdk]`** — IaC, CloudWatch dashboards
and alarms, cost tags and a runbook to promote an existing workload.

## Sub-agents

Six, each usable on its own as well as through the workflow. They generate files only — no MCP,
no AWS, no peer spawning.

| Agent | Produces |
|-------|----------|
| `adop:metadata-agent` | column metadata, roles, PII/PHI/PAN flags → `config/semantic.yaml` |
| `adop:quality-agent` | rules and gates across the five dimensions → `config/quality.yaml`, checks |
| `adop:transformation-agent` | Bronze/Silver/Gold specs → rendered Glue PySpark |
| `adop:dag-agent` | the orchestration spec → rendered Airflow DAG or Step Functions machine |
| `adop:ontology-agent` | OWL2 `ontology.ttl` + R2RML `mappings.ttl` + manifest |
| `adop:iac-agent` | Terraform / CDK / CloudFormation plus an apply guide |

Invoking one directly suits re-running a stage — a transform spec after a rule change, a DAG after
a schedule change. Each expects `workloads/{name}/run/context.json`, where the human's Phase 1
answers live, so direct invocation is for extending a workload that has been through discovery,
not for starting one.

## Skills

Loaded on demand; only their descriptions cost context.

| Skill | Carries |
|-------|---------|
| `adop:discovery-protocol` | the Phase 1 gate — zone-targeted questions, ontology follow-ups, the NEVER list |
| `adop:pipeline-conventions` | zone gates, the five quality dimensions, Airflow/SQL/YAML rules, glossary |
| `adop:observability` | shared run context, the three trace layers, the error taxonomy |
| `adop:decision-engine` | tool routing, the MCP inventory, the 11 mandatory invariants |
| `adop:data-compliance` | which regulation pack applies and how it is injected |

## Compliance

One prompt file per framework, in `runbooks/data-onboarding-agent/regulation/`. These are the
control sets themselves — 235 to 293 lines each — not summaries: they name the specific columns,
masking methods, retention windows and audit records a framework requires.

`GDPR` · `CCPA` · `HIPAA` · `SOX` · `PCI DSS`

Controls are injected at build time into the Silver rules (masking, pseudonymisation,
tokenisation), the Gold rules (suppression, aggregation-only exposure), the quality rules (a Luhn
check for PCI, for instance), and retention and audit. **Your legal reviewer reads a prompt file,
not generated PySpark.**

Not legal advice. These encode common control patterns to support your compliance work; you remain
responsible for validating they meet your actual obligations. Agents may process regulated data
during development — review your data-handling practices before promoting anything.

## Hooks

| Hook | Event | Does |
|------|-------|------|
| `check_discovery_gate.py` | PreToolUse | refuses pipeline writes until discovery is complete |
| `enforce_template_codegen.py` | PreToolUse | refuses direct writes to `scripts/`, `dags/`, `sql/` |
| `validate_artifacts.py` | PostToolUse | Python must parse; blocks credential patterns; warns on missing DAG retries and Glue lineage |

The two PreToolUse hooks **stand down automatically inside an ADOP checkout**, where the
repository ships its own equivalents. Hooks are the one plugin component without namespacing, so
without that guard they would fire alongside the project's and deny the same write twice.

## MCP servers

Thirteen declared. Four are vendored with the plugin — `glue-athena`, `lakeformation`,
`pii-detection`, `sagemaker-catalog` — and nine install via `uvx`.

**Three of the nine cannot currently start:** `awslabs-core-mcp-server`,
`awslabs-lambda-mcp-server` and `awslabs-cost-explorer-mcp-server` are yanked from PyPI. Live
successors exist (`awslabs-aws-api-mcp-server`, `awslabs-lambda-tool-mcp-server`,
`awslabs-billing-cost-management-mcp-server`) but are not substituted here, because tool routing
maps intents to specific tool names and a package that starts while exposing a different tool
surface fails silently — worse than one that visibly does not connect. Tracked upstream.

## Two ways this is weaker than working in the ADOP repository

Stated plainly, because both are structural rather than oversights.

**Always-on guidance becomes on-demand.** In a checkout, `CLAUDE.md` and `.claude/rules/` are in
context on every turn, and path-scoped rules load automatically when you edit a matching file. A
plugin has no equivalent: skill *bodies* load only when invoked. The load-bearing part — the Phase
1 STOP gate — is therefore repeated in the command body, which is always read when the command
runs. The rest is one invocation away rather than already present.

**Commit-time gating is opt-in.** The repository's `.pre-commit-config.yaml` runs 18 hooks that can
reject a commit, including secret detection and artifact drift. A plugin cannot install git hooks
into your repository, and plugin hooks intercept a different thing — the agent's tool calls, not
commits. So `validate_artifacts.py` covers what an agent writes, but nothing here stops *you*
committing a secret. To get the commit gate, copy the repository's `.pre-commit-config.yaml` and
run `pre-commit install`.

## How this relates to the repository

Everything here is derived from the ADOP repository, which is normative. `TRANSLATION.yaml`
records, for every file, its source and how faithfully it could be carried — byte-identical copy,
a rewrite with retargeted paths, or a transform into a different primitive — and
`tests/unit/test_plugin_translation.py` fails the build when a copy drifts from its source, when a
rewrite loses a mechanism it declared, or when a new rule is added upstream without being carried
here.

So report bugs and propose changes **upstream**, not against the plugin's copies: an edit to a
vendored file here is reverted by the next re-vendoring and fails the drift check meanwhile.

## License

MIT-0, as the upstream repository.
