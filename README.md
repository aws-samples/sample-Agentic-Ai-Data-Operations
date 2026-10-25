# ADOP — Agentic Data Operations Platform

ADOP turns a plain-language data request into a human-approved, tested, and
auditable Bronze → Silver → Gold data workload.

It coordinates discovery, profiling, quality, transformations, orchestration,
security, observability, deterministic code generation, and deployment
verification. The human owns business decisions; agents produce validated
artifacts and evidence.

![ADOP overview](docs/diagrams/adop-overview.png)

## One goal, four platform paths

Claude Code, Codex, Amazon Q Developer, and Kiro use different native
interfaces but follow the same contracts, phases, guardrails, tests, and audit
model.

| Platform | Start here | Dynamic workflow |
|---|---|---|
| Claude Code | `CLAUDE.md`, `.claude/` | `/onboard-workflow [REGULATION]` |
| Codex | `AGENTS.md`, `.codex/` | `$command-onboard-workflow [REGULATION]` |
| Amazon Q Developer | `AmazonQ.md`, `.amazonq/` | `q chat --agent adop-orchestrator` |
| Kiro | `.kiro/` | `python3 scripts/kiro_workflow.py init --workload <name>` |

Shared behavior:

- mandatory human discovery before artifact generation;
- versioned source and zone contracts;
- requirements capture and requirements auditing;
- Cedar authorization and MCP guardrails;
- deterministic rendering, tests, traces, and deployment evidence.

Platform-specific behavior is kept in the native root folders and portable
snapshots under [`adapters/`](adapters/). The Claude Code plugin is separately
installable for use from another repository.

## Quick start

```bash
git clone https://github.com/aws-samples/sample-Agentic-Ai-Data-Operations.git
cd sample-Agentic-Ai-Data-Operations

python3 scripts/validate_integrations.py
python3 scripts/sync_platforms.py check
```

Open the repository with one supported client:

- Claude Code: start at the repository root and run `/onboard-workflow`.
- Codex: run `python3 scripts/start_codex.py`, then use
  `$command-onboard-workflow`.
- Amazon Q: start Q at the repository root and use
  `q chat --agent adop-orchestrator`.
- Kiro: initialize with
  `python3 scripts/kiro_workflow.py init --workload <name>`.

### Claude Code plugin

Use the plugin when ADOP should operate in another repository. Install the
Claude plugin from the configured marketplace or local plugin path, run its
preflight, and invoke `/adop:onboard-workflow`.

Codex, Amazon Q, and Kiro use their native project surfaces; they do not
require the Claude plugin.

## Prompt format

Give the agent the business outcome and confirmed constraints:

```text
Onboard <source> into <target zones>.
Source: <location, type, format, cadence>
Business outcome: <what Gold must answer>
Transformations: <confirmed cleaning and derived-column rules>
PII/compliance: <columns and framework, or none>
Quality: <thresholds and critical rules, or "use defaults">
Schedule: <cron and IANA timezone>
Ontology: <opt in/out and consumers>
```

The agent may profile schema, nulls, row counts, and formats, but it must ask
the human to confirm missing business decisions. It must not guess primary
keys, deduplication, null handling, PII, schedules, or transformations.

## Workflow phases

| Phase | Purpose | Gate |
|---|---|---|
| 0. Health and discovery | Check workloads, source metadata, credentials, and tools | Source and access confirmed |
| 1. Requirements | Capture source, zone, transformation, PII, quality, schedule, and ontology decisions | All mandatory answers provided |
| 2. Deduplication and context | Detect overlap and create the run context and requirements ledger | Conflicts resolved |
| 3. Profiling | Inspect representative data and present quality/PII observations | Human confirms handling |
| 4. Build and test | Validate specs, render artifacts, and run tests | Plan and tests approved |
| Audit | Compare Q&A with context, decisions, traces, tests, artifacts, and deployment evidence | Requirements audit passes |
| 5. Deploy and verify | Deploy through approved tools and run post-deployment checks | Human approval and verification |

After deployment, the workflow offers the optional E2E pipeline test and DevOps
production-readiness workflow.

## Provider-neutral extension model

The business contracts are independent of the execution backend. A future
adapter for `aws_glue`, `emr_spark`, `dbt_snowflake`, or `databricks` should
reuse the same source/zone contracts and add only:

- versioned execution-target and `runtime.yaml` settings;
- client-specific MCP registration without credentials in Git;
- provider-aware health checks and post-deployment verification;
- requirements-auditor evidence linking requirements to models, jobs, tables,
  tests, and deployment results.

## Agent Coordination Workflow

![Agent Coordination Workflow](docs/diagrams/data-onboarding-workflow.png)

```text
User request
    ↓
Router → existing workload or new onboarding
    ↓
Human discovery + requirements ledger
    ↓
Metadata / Quality / Transformation / DAG / Ontology agents
    ↓
Renderer + tests + requirements auditor
    ↓
Human approval → deployment → verification
```

Specialist agents have narrow responsibilities and cannot bypass the human
gate. Sub-agents generate and test artifacts; they do not use AWS or MCP.

## AI Clone Decision Engine

The AI Clone Decision Engine encodes the organization’s operating philosophy
into runtime routing and guardrails. It keeps agents on the approved path even
when the platform, MCP availability, or execution backend changes.

Decision flow:

```text
User intent
  → context gate
  → server health
  → intent/tool match
  → Cedar and MCP policy check
  → approved fallback or human escalation
  → decision, trace, and requirements evidence
```

Non-negotiable principles:

- human-approved requirements outrank agent assumptions;
- required-server failures block;
- optional-server fallbacks are explicit and audited;
- MCP is preferred when the approved server is healthy;
- Bronze is immutable and quality gates cannot be bypassed;
- credentials and infrastructure secrets never enter artifacts;
- deployment, repair, retry, and fallback decisions are traced.

Routing and policy sources:

| File | Purpose |
|---|---|
| [`TOOL_ROUTING.md`](TOOL_ROUTING.md) | Intent-to-tool mappings and disqualifiers |
| [`MCP_GUARDRAILS.md`](MCP_GUARDRAILS.md) | Phase-specific MCP permissions |
| [`tool-registry/servers.yaml`](tool-registry/servers.yaml) | Server capabilities and fallbacks |
| [`tool-registry/invariants.yaml`](tool-registry/invariants.yaml) | Organization-wide BLOCK/WARN rules |
| `shared/policies/` | Cedar agent authorization and safety policies |

![ADOP architecture](docs/diagrams/Architecture-Diagram.png)

## Contracts: the source of truth

Concept contracts define what must be true. JSON Schema contracts define how
those decisions are represented and validated in
[`contracts/`](contracts/README.md).

Authority order:

```text
Human Q&A → concept contract → versioned schema → Cedar/quality gates
          → deterministic renderer → artifacts and evidence
```

### Zone contracts

| Zone | Design principle | Required decisions |
|---|---|---|
| Bronze | Preserve raw source data; immutable after ingestion | Path, format, landing, catalog, retention, replay/idempotency |
| Silver | Validated, standardized Apache Iceberg data | PK, dedup, nulls, casts, PII masking, schema evolution, quality |
| Gold | Business-purpose serving data | Outcome, grain, KPIs, schema type, consumers, retention |

Default gates are Silver ≥ 0.80 and Gold ≥ 0.95. Critical failures block
promotion.

### Source contracts

Supported source types are defined by
[`source_profile.schema.json`](contracts/v1/source_profile.schema.json).
Each workload records the source contract in
`workloads/{name}/config/source.yaml`.

| Source | Required decisions |
|---|---|
| CSV, Parquet, JSON, Avro | Location, format, partitioning, schema evolution, malformed-record, retention, replay |
| JDBC | Secret reference, table/query, PK, watermark, consistency, extraction window, failure handling |
| Kafka | Cluster/topic, event key, consumer group, offsets, schema, ordering, late events |
| Kinesis | Stream, partition key, checkpoint, retention, trigger, throughput, late events |

Contracts are created and confirmed before artifact generation. Generated
artifacts are evidence of the contract; they cannot override it.

## Dynamic workflows

| Platform | Onboarding | Production readiness |
|---|---|---|
| Claude Code | `/onboard-workflow [REGULATION]` | `/devops-workflow [WORKLOAD] [FRAMEWORK]` |
| Codex | `$command-onboard-workflow [REGULATION]` | `$command-devops-workflow [WORKLOAD] [FRAMEWORK]` |
| Amazon Q | `q chat --agent adop-orchestrator` | `q chat --agent adop-devops` |
| Kiro | `kiro_workflow.py init`, `gate`, `audit` | Kiro DevOps agent after workload gates |

The native definitions are under `.claude/commands/`,
`.codex/skills/`, `.amazonq/cli-agents/`, and `.kiro/`.

## Dynamic routing and BYO technology stack

Business intent is separated from execution technology. The same contracts can
target AWS Glue/Iceberg today and future EMR Spark, dbt/Snowflake, or
Databricks adapters.

Keep business rules in zone specifications. Keep backend settings—workers,
Spark memory, warehouses, clusters, region, retries, and tool allowlists—in
execution-target configuration.

A new backend must preserve discovery, contracts, deterministic rendering,
tests, read-only versus mutation tool separation, traces, audit evidence, and
post-deployment verification.

## Third-party MCP integrations

Snowflake, Databricks, and Teradata profiles exist but are disabled by default.
Enable them only after provider authentication, least-privilege permissions,
tool allowlists, and Phase 0 health checks are configured.

Provider-native MCP connections are for governed discovery, profiling, query
validation, or provider-specific operations. Credentials and private endpoints
must remain in the client secret store or environment—not in Git or workload
artifacts.

See [`mcp-profiles/third-party/README.md`](mcp-profiles/third-party/README.md)
for the disabled profiles and provider-specific setup references.

## Repository structure

```text
.claude/ .codex/ .amazonq/ .kiro/   Native client surfaces
adapters/                           Portable platform snapshots
contracts/                          Versioned workload schemas
shared/                             Renderer, audit, logging, policies, utilities
mcp-profiles/                       Default, demo, and disabled provider profiles
mcp-servers/                        Repository-owned FastMCP servers
tool-registry/                      MCP capabilities and invariants
workloads/                          Dataset-specific configs and artifacts
scripts/                            Validation, demo, workflow, and startup tools
plugins/claude-code/                Installable Claude Code plugin
docs/                               Detailed guides and diagrams
```

## Tests and readiness

```bash
python3 scripts/run_tests.py
python3 scripts/validate_integrations.py
python3 scripts/sync_platforms.py check
python3 scripts/mcp_demo.py check --profile demo
```

The demo check is read-only. AWS deployment requires the discovery gate,
human approval, Cedar authorization, requirements audit, and mandatory
post-deployment verification.

## Further documentation

- [Getting started](docs/getting-started.md)
- [Platform integration](docs/platform-integration.md)
- [MCP setup](docs/mcp-setup.md)
- [Contracts](contracts/README.md)
- [Tool routing](TOOL_ROUTING.md)
- [MCP guardrails](MCP_GUARDRAILS.md)
- [Running tests](docs/running-tests.md)
- [Security](docs/security.md)
- [Workflow diagrams](docs/workflow-diagrams.md)
- [AWS setup](docs/aws-account-setup.md)

## Status

The current implementation is optimized for AWS Glue PySpark, Apache Iceberg,
Athena, and Airflow/MWAA. Snowflake, Databricks, Teradata, EMR, and dbt are
integration extension points with disabled provider profiles unless explicitly
enabled.

## License

See the source repository for the applicable license terms.

