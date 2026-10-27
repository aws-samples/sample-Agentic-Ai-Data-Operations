# ADOP — Agentic Data Operations Platform

ADOP turns a plain-language data request into a human-approved, tested, and
auditable Bronze → Silver → Gold data workload.

It coordinates discovery, profiling, quality, transformations, orchestration,
security, observability, deterministic code generation, and deployment
verification. The human owns business decisions; agents produce validated
artifacts and evidence.

![ADOP overview](docs/diagrams/adop-overview.png)

## One goal, four client paths plus optional Strands

Claude Code, Codex, Amazon Q Developer, and Kiro use different native
interfaces but follow the same contracts, phases, guardrails, tests, and audit
model.

| Platform | Start here | Dynamic workflow |
|---|---|---|
| Claude Code | `CLAUDE.md`, `.claude/` | `/onboard-workflow [REGULATION]` |
| Codex | `AGENTS.md`, `.codex/` | `$command-onboard-workflow [REGULATION]` |
| Amazon Q Developer | `AmazonQ.md`, `.amazonq/` | `q chat --agent adop-orchestrator` |
| Kiro | `.kiro/` | `python3 scripts/kiro_workflow.py init --workload <name>` |
| Headless AWS Strands | `scripts/run_strands.py` | `python3 scripts/run_strands.py run --args <args.json> --region <region> --model <model-id>` |

Shared behavior:

- mandatory human discovery before artifact generation;
- versioned source and zone contracts;
- requirements capture and requirements auditing;
- Cedar authorization and MCP guardrails;
- deterministic rendering, tests, traces, and deployment evidence.

Platform-specific behavior is kept in the native root folders and portable
snapshots under [`adapters/`](adapters/). The Claude Code plugin is separately
installable for use from another repository.

The platforms coexist in one checkout. Each has its own hook wiring
(`.claude/settings.json`, `.codex/hooks.json`, `.kiro/hooks/adop-gates.json`,
`.amazonq/cli-agents/`), and all of them call the same `shared/` renderer,
contracts, and auditor. When you change a root surface such as `.kiro/hooks/`,
copy the change to its `adapters/` snapshot. `sync_platforms.py check` verifies
that required files exist, not that their contents match.

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
  `$command-onboard-workflow`. For a clean customer project, install the
  named specialist contracts using
  [`docs/codex-specialist-setup.md`](docs/codex-specialist-setup.md).
- Amazon Q: start Q at the repository root and use
  `q chat --agent adop-orchestrator`.
- Kiro: initialize with
  `python3 scripts/kiro_workflow.py init --workload <name>`.
- Headless Strands: install the optional dependency with
  `pip install -e '.[strands]'`, then run
  `python3 scripts/run_strands.py status` followed by the `run` command above.
  See [Headless AWS Strands runtime](#headless-aws-strands-runtime).

### Claude Code plugin

Use the plugin when ADOP should operate in another repository. Install the
Claude plugin from the configured marketplace or local plugin path, run its
preflight, and invoke `/adop:onboard-workflow`.

Codex, Amazon Q, and Kiro use their native project surfaces; they do not
require the Claude plugin.

### Headless AWS Strands runtime

[`runtimes/strands/`](runtimes/strands/) runs the Phase 4 build sub-agents
in-process with the [AWS Strands Agents SDK](https://strandsagents.com) on
Amazon Bedrock. It plugs into the same `WorkflowDriver` as the Amazon Q path
(`shared/orchestration/workflow_driver.py`, `--runtime strands`), so the
build order, pytest test gates, retries, and traces are identical.

| Aspect | Behavior |
|---|---|
| Scope | Phase 4 only: metadata ‖ quality → transform → DAG → optional ontology → reviewer. Phases 0–2 and 5 stay in a human-facing client, so discovery must be complete first. |
| Agent definitions | Loaded from `.amazonq/cli-agents/adop-*.json` (prompt, resources, `fs_write` allowlist) |
| Tools | `fs_read`, `fs_write`, `run_pytest_gate`, `render_artifact`. There is no shell tool and no MCP. |
| Write guards | No writes to `scripts/`, `dags/`, `sql/` (use `render_artifact`); no `.py` outside `workloads/*/tests/`; orchestrator-owned run state (`run/context.json`, `run/requirements.jsonl`, discovery markers) is read-only |
| Handoff | Strands structured output validated as `AgentOutput`. The runner stamps `agent_name`, `workload_name`, `run_id`, and timestamps itself rather than trusting the model. |
| Review gate | Blocks on `Severity: HIGH` in `reviews/security-findings.md`, ignoring markdown emphasis and case |
| Dependency | Optional extra `strands` (`strands-agents==1.62.0`); nothing else imports it |

```bash
pip install -e '.[strands]'
python3 scripts/run_strands.py status                       # list loadable agents
python3 scripts/run_strands.py run --args args.json --dry-run   # offline contract check
python3 scripts/run_strands.py run --args args.json \
  --region us-east-1 --model <bedrock-model-id> --run-id <id>    # live Bedrock run
```

`args.json` is the onboarding args object produced after discovery (see
`.claude/commands/onboard-workflow.md`). A live run makes Bedrock calls and
writes workload artifacts, so run it on a workload whose files you can
review and revert. The ontology agent's Glue `get_table` tool is not yet
wired through Strands, and AgentCore Runtime deployment is not implemented.
The `strands-agentcore` extra is reserved for that.

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
gate. Sub-agents generate and test artifacts. They do not use AWS or MCP, with
one exception: the ontology agent has read-only Glue `get_table`.

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

Implementation status: the source contract accepts `jdbc`, `kafka`, and
`kinesis`, but the `bronze_ingestion` template reads only file sources
(`csv`, `parquet`, `json`, `avro`, `orc`) from S3. Those three types are
contract-level only until an ingestion template exists for them.

### How contracts are wired

One chain connects each contract to the code that enforces it. Extending a
contract means extending every link in it.

```text
contracts/vN/<type>.schema.json    shape of the spec (JSON Schema 2020-12)
  ↓ SPEC_TYPE_TO_SCHEMA            shared/codegen/spec_loader.py: spec type → schema file
  ↓ workloads/<wl>/config/*.yaml   spec instance; its "schema_version" picks vN
  ↓ shared/templates/<id>.j2       header declares template_id, version,
  ↓                                required_slots, schema_version
  ↓ renderer.render()              validates slots, refuses unsupported values,
  ↓                                writes artifact + 5-line provenance header
  ↓ drift_validator                template_id → spec type → spec file; re-renders
                                   and compares bytes
```

| Contract | Schema | Spec file | Template(s) | Produced by |
|---|---|---|---|---|
| Source | `source_profile` | `config/source.yaml` | none (input to Bronze) | metadata agent |
| Bronze zone | `bronze_spec` (v1, v2) | `config/bronze.yaml` | `bronze_ingestion` | transformation agent |
| Silver zone | `silver_spec` | `config/silver.yaml` | `silver_transform`, `iceberg_ddl` | transformation agent |
| Gold zone / target | `gold_spec` (v1, v2) | `config/gold.yaml` | `gold_aggregate`, `iceberg_ddl` | transformation agent |
| Quality | `quality_spec` | `config/quality_rules.yaml` | `quality_check` | quality agent |
| Orchestration | `dag_spec` (v1, v2) | `config/schedule.yaml` | `airflow_dag`, `glue_job_config` | DAG agent |
| Run state | `run_context` | `run/context.json` | none | orchestrator only |

### Extending contracts

Versioning rule (see [`contracts/README.md`](contracts/README.md)): a
published schema is immutable. Adding an optional field with a default is
allowed in place. Adding or removing a required field means a new version
directory (`v2` added required catalog and idempotency fields to
`bronze_spec`). Specs choose their version through `schema_version`.

**New data source** (for example, JDBC ingestion or a SaaS API):

1. Add the type to `source.type` (and `format` if needed) in
   `source_profile.schema.json`, plus any source-specific fields. Credentials
   are always a reference (`credentials.type` + `connection_id`), never a value.
2. Add the source's discovery questions to
   `.claude/rules/00-zone-questions.md` and its copies in
   `.kiro/steering/` and `.amazonq/rules/`. Codex has no copy of this file;
   update `AGENTS.md` and `.codex/skills/command-onboard-workflow/`. List the
   source's required decisions in the source table above.
3. Add an ingestion branch to `bronze_ingestion.py.j2`, or a new template,
   behind a version bump. Use `unsupported()` for any value the branch can't
   implement. Keep the runtime input guard: the S3 check applies only to
   file sources.
4. If discovery needs a provider MCP server, add it to
   `tool-registry/servers.yaml` and a profile under `mcp-profiles/`
   (disabled by default) with a Phase 0 health check.
5. Add tests: schema accept/reject cases, a render test, and a refusal test
   for unsupported values.

**New zone or zone capability** (for example, a new Silver dedup mode or an
extra curated layer):

1. A new enum value or optional field goes into the zone's schema. For
   example, `silver_spec.dedup_strategy` is currently `keep_latest`,
   `keep_first`, `drop_exact_duplicates_only` or `none`. A new required field
   means a new version.
2. A new zone gets its own `<zone>_spec.schema.json`, an entry in
   `SPEC_TYPE_TO_SCHEMA`, a template with header metadata, and an entry in
   `drift_validator._template_id_to_spec_type` and `_find_spec_file`.
3. Define its quality gate (Silver ≥ 0.80 and Gold ≥ 0.95 today) in
   `quality_spec` and the Cedar policies under `shared/policies/`. Gates can't
   be bypassed.
4. Add the zone's questions to the discovery rules and its fields to
   `run_context.human_answers`. The human supplies them, and sub-agents only
   translate them.
5. Update the sub-agent that produces the spec. Its definition exists once per
   platform: `.claude/agents/`, `.codex/agents/`, `.amazonq/cli-agents/`, and
   `.kiro/agents/`.

**New data target** (for example, a new Gold serving shape or a non-Glue backend):

1. A new Gold serving shape is a new `gold_spec.schema_type` value (today
   `star_schema`, `flat_iceberg`, `iceberg_dynamodb`) plus a branch in
   `gold_aggregate.py.j2` and the DDL template.
2. A new execution backend (EMR Spark, dbt/Snowflake, Databricks) should keep
   the zone specs unchanged. Put backend settings in a separate,
   versioned execution-target contract and add backend-specific templates.
   Neither exists yet. See
   [Dynamic routing and BYO technology stack](#dynamic-routing-and-byo-technology-stack).
3. Extend post-deployment verification
   (`shared/utils/post_deployment_verifier.py`) and the requirements auditor
   so the target's tables, jobs and grants show up as evidence.

After any template change, re-render the affected artifacts, then run
`python3 -m shared.codegen.drift_validator workloads/<wl>` and the test suites.

### Generated-code guardrails

Everything under `workloads/*/scripts/`, `dags/`, and `sql/` is rendered by
`shared.codegen.renderer.render()` and checked by
`shared.codegen.drift_validator`. A template edit therefore requires
re-rendering the affected artifacts. The templates refuse unsafe spec values
at render time rather than emitting them:

- `quality_check`: a `custom_sql` predicate containing `;`, `--`, `/*`, or a
  DDL/DML/DCL keyword (DROP, CREATE, ALTER, TRUNCATE, INSERT, UPDATE, DELETE,
  MERGE, GRANT, REVOKE) is rejected; `F.expr()` takes one boolean expression.
- `bronze_ingestion`: after Glue job arguments are substituted, `source_path`
  and `landing_zone` must be well-formed S3 URIs. Control characters, other
  schemes, invalid bucket names, and `..` segments are rejected.

Tests: `shared/tests/unit/test_codegen_security_guards.py`.

## Dynamic workflows

| Platform | Onboarding | Production readiness |
|---|---|---|
| Claude Code | `/onboard-workflow [REGULATION]` | `/devops-workflow [WORKLOAD] [FRAMEWORK]` |
| Codex | `$command-onboard-workflow [REGULATION]` | `$command-devops-workflow [WORKLOAD] [FRAMEWORK]` |
| Amazon Q | `q chat --agent adop-orchestrator` | `q chat --agent adop-devops` |
| Kiro | `kiro_workflow.py init`, `gate`, `audit` | Kiro DevOps agent after workload gates |
| Headless Strands | `run_strands.py run` (Phase 4 build after discovery) | Not covered |

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
runtimes/strands/                   Optional headless AWS Strands build runtime
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

# optional Strands runtime (needs the strands extra)
python3 -m pytest runtimes/strands/tests -q
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

