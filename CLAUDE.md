# CLAUDE.md — Agentic Data Onboarding System

This file configures Claude Code for the Agentic Data Onboarding platform.

## Project Identity

An autonomous data pipeline orchestration platform that moves data through **Bronze → Silver → Gold** zones using a multi-agent architecture. Integrates with AWS SageMaker Catalog (business metadata), SynoDB (metrics & SQL), Knowledge Graph (semantic search), and Apache Airflow for orchestration.

**Status**: Design-complete, implementation pending.

## Key Files

| File | Purpose |
|---|---|
| `.kiro/specs/agentic-data-onboarding/design.md` | Full architecture, component interfaces (TypeScript), data flow diagrams, API specs, error handling |
| `.kiro/specs/agentic-data-onboarding/requirements.md` | 40 requirements with acceptance criteria |
| `.kiro/specs/agentic-data-onboarding/tasks.md` | 25 implementation tasks with subtasks |
| `SKILLS.md` | Agent skill definitions — prompts, workflows, constraints for all 7 agents |
| `TOOLS.md` | AWS tooling reference — which specific service/tool to use at each pipeline step |
| `MCP_GUARDRAILS.md` | **MCP tool selection guardrails** — actual MCP tool names, per-phase rules, fallback decisions, live server status |
| `WORKFLOW.md` | Visual diagrams — end-to-end flow, sub-agent spawning, test gates, data zone progression, DAG tasks |

Read `design.md` before making architectural decisions. Read `SKILLS.md` before acting as any agent. Read `TOOLS.md` for AWS service selection. Read `MCP_GUARDRAILS.md` for which MCP tool vs CLI to use at each phase. See `WORKFLOW.md` for visual diagrams.

## Architecture Overview

```
MAIN CONVERSATION
├── Router (inline) — check workloads/, found or not found
└── Data Onboarding Agent (orchestrator, human-facing)
    │
    │  Phase 1-2: inline (questions, dedup, validation)
    │  Phase 3-4: spawns sub-agents via Agent tool
    │
    │  spawn → Metadata Agent ──→ TEST GATE ──→ proceed
    │  spawn → Transformation Agent ──→ TEST GATE ──→ proceed
    │  spawn → Quality Agent ──→ TEST GATE ──→ proceed
    │  spawn → Orchestration DAG Agent ──→ TEST GATE ──→ proceed
    │
    └── Present all artifacts + test results → human approves
    │
    │  Phase 5: Deploy (main conversation — see MCP_GUARDRAILS.md)
    │  IAM/Permissions → `iam` MCP (loaded)
    │  LF Grants → `lambda` MCP (loaded, via LF_access_grant Lambda)
    │  Query Verify → `redshift` MCP (loaded, via Spectrum)
    │  Audit → `cloudtrail` MCP (loaded)
    │  S3/Glue/KMS → AWS CLI fallback (MCP servers not loaded)
```

**MCP-First Rule**: All AWS operations use MCP server tools first. Sub-agents do NOT have MCP access — they generate scripts/configs only. Deployment runs in the main conversation via MCP. See `MCP_GUARDRAILS.md` for actual tool names, per-phase rules, and fallback decisions. See `TOOLS.md` for the full AWS service mapping.

**Data zones**: Bronze (raw, immutable) → Silver (cleaned, validated) → Gold (curated, aggregated)
**Semantic layer**: SageMaker Catalog (custom metadata columns for business context) + SynoDB (metrics & SQL) + Knowledge Graph (embeddings) + MCP Layer

**Agent model**: Data Onboarding Agent runs in main conversation (human-facing). All specialized agents are sub-agents spawned via the `Agent` tool. Each sub-agent must write and pass unit + integration tests before the orchestrator proceeds.

## Tech Stack

- **Language**: TypeScript (implementation), Python (Airflow DAGs, scripts)
- **Cloud**: AWS — S3 + S3 Tables (data zones), Glue (catalog), SageMaker Catalog (business metadata), Apache Iceberg (table format), Athena (queries), Step Functions (workflows), Lambda (agents), OpenSearch (knowledge graph), KMS (encryption)
- **Orchestration**: Apache Airflow
- **Testing**: Jest + fast-check (property-based)
- **Vector DB**: OpenSearch (knowledge graph / semantic search)
- **Auth**: API Key, OAuth 2.0, SAML, JWT

## Agent Behavior Model

When the user asks you to do something in this project, follow this protocol:

### 1. Route First (Router Agent)

Before anything else, check if the data the user is asking about already has a workload in `workloads/`. Search folder names, `config/source.yaml`, and `README.md` files for matches.

- **If found**: Point the user to the existing `workloads/{name}/` folder and summarize what's there (source, zones populated, DAG schedule). Ask what they want to do with it.
- **If not found**: Tell the user this data hasn't been onboarded yet and proceed to step 2.
- **If partial** (e.g., only Bronze exists): Report what's there and what's missing. Ask if they want to complete the pipeline or start over.

### 2. Ask Before Acting (Data Onboarding Agent — Phase 1)

For new onboarding, follow the **Data Onboarding Agent** discovery phase. Ask questions in separate categories — each feeds a different agent/layer:

- **Source** (→ Metadata Agent): location, format, credentials, frequency
- **Column identification** (→ Metadata Agent): PK, PII columns, exclusions
- **Cleaning rules** (→ Transformation Agent, Bronze→Silver): dedup, null handling, type casting ask more if required 
- **Metrics & dimensions** (→ SageMaker Catalog + SynoDB / Semantic Layer, Silver→Gold): column roles, dimension hierarchies, seed SQL examples
- **Quality** (→ Quality Agent): thresholds, compliance
- **Scheduling** (→ DAG Agent): cron, dependencies, failure handling

**Semantic layer storage**:
- `config/semantic.yaml` — local config file, loaded into stores at deploy time
- **SageMaker Catalog** (custom metadata columns) — column roles, data types, descriptions, PII flags, relationships, business terms. Stored as custom metadata properties on table/column entries in the Glue Data Catalog. All agents read this to understand the data.
- **SynoDB** (Metrics & SQL Store) — seed SQL examples + queries the Analysis Agent learns over time. The system gets smarter with use.

The Analysis Agent reasons about calculations on its own from column roles (measure, dimension, temporal) in SageMaker Catalog. It checks SynoDB for similar past queries. When it produces a useful new query, it saves it back to SynoDB. No pre-defined metric formulas needed.

### 3. Deduplicate & Validate Source (Phase 2)

Before creating anything, confirm the source is not already onboarded in another workload. Scan every `workloads/*/config/source.yaml` for overlap. Block exact duplicates, warn on overlaps. Also check `shared/` for reusable assets.

### 4. Profile Before Building (Phase 3)

Run a 5% sample profiling pass using Glue Crawler + Athena (see `TOOLS.md`). Present metadata to the human — column types, distinct values, null rates, PII flags, sample rows. Get confirmation before generating pipeline code.

### 5. Test After Every Sub-Agent (Phase 4)

Every sub-agent (Metadata, Transformation, Quality, DAG) must write unit and integration tests alongside its artifacts. After each sub-agent returns, run the tests:
- **All pass** → proceed to next sub-agent
- **Failures** → re-spawn sub-agent with error context (max 2 retries)
- **Still failing** → escalate to human with full details

Never skip test gates. Never proceed with failing tests.

Edit existing files rather than creating duplicates.

### 6. Follow the Folder Convention

Every onboarding workload gets its own directory:

```
workloads/{workload_name}/
├── config/          # source.yaml, semantic.yaml (metadata+business context), transformations.yaml, quality_rules.yaml, schedule.yaml
├── scripts/         # extract/, transform/, quality/, load/
├── dags/            # {workload_name}_dag.py
├── sql/             # bronze/, silver/, gold/
├── tests/           # unit/, integration/
└── README.md
```

Shared code goes in:

```
shared/
├── operators/       # Reusable Airflow operators
├── hooks/           # Reusable Airflow hooks
├── utils/           # quality_checks.py, schema_utils.py, encryption.py, notifications.py, pii_detection_and_tagging.py
├── templates/       # dag_template.py, config_template.yaml, quality_rules_template.yaml
└── sql/common/      # Cross-workload SQL
```

**PII Detection Framework** (`shared/utils/pii_detection_and_tagging.py`):
- Shared utility for AI-driven PII detection across all workloads
- Scans columns using name-based + content-based patterns
- Applies Lake Formation LF-Tags for column-level security (tag-based access control)
- Supports 12 PII types: EMAIL, PHONE, SSN, CREDIT_CARD, NAME, ADDRESS, DOB, IP_ADDRESS, DRIVER_LICENSE, PASSPORT, NATIONAL_ID, FINANCIAL_ACCOUNT
- Creates 3 LF-Tags: `PII_Classification`, `PII_Type`, `Data_Sensitivity`
- Enables compliance with GDPR, CCPA, HIPAA, SOX, PCI DSS
- Integrated into profiling (Phase 3) and runs after Staging load
- **MCP Integration**: Custom MCP server at `mcp-servers/pii-detection-server/` enables natural language governance via Claude Code

### 7. Present a Plan

For non-trivial tasks (anything that creates multiple files or modifies pipeline logic), summarize your plan and get human approval before executing. Use `EnterPlanMode` for multi-file changes.

## Coding Conventions

### TypeScript (Core Platform)

- All agent interfaces are defined in `design.md` — follow those type signatures exactly.
- Use async/await for all I/O operations.
- Return typed `Promise<T>` from all agent methods.
- Errors must include context: agent name, operation, input summary — never raw stack traces to end users.
- Use discriminated unions for status types (e.g., `'pending' | 'running' | 'completed' | 'failed'`).

### Python (Airflow DAGs & Scripts)

- Follow the DAG template in `SKILLS.md` (Orchestration DAG Agent section).
- Use Airflow Variables and Connections for all configuration — zero hardcoded values.
- Use `TaskGroup` (not `SubDagOperator`).
- Use `PythonOperator` calling scripts in `workloads/{name}/scripts/`, not inline logic.
- Set `catchup=False`, `max_active_runs=1`, `retries=3` with exponential backoff as defaults.
- Every DAG must have `on_failure_callback`, `sla` on critical tasks, and `doc_md`.

### YAML Configuration

- Use the config schemas from `SKILLS.md` for `source.yaml`, `transformations.yaml`, `quality_rules.yaml`, and `schedule.yaml`.
- Never put credentials in YAML — reference Secrets Manager ARNs or Airflow Connection IDs.
- Include comments explaining non-obvious configuration choices.

### SQL

- Place SQL files in `workloads/{name}/sql/{zone}/`.
- Use fully qualified table names: `database.schema.table`.
- Always include `LIMIT` in analytical queries.
- Use CTEs over nested subqueries.
- Never use `SELECT *` in production queries.
- Never include DDL in Gold zone SQL — Gold is read-only for analysis.

## Security Rules (Non-Negotiable)

These apply to ALL code generated in this project:

1. **No hardcoded secrets** — Credentials, connection strings, API keys, and tokens come from AWS Secrets Manager, Airflow Connections, or environment variables. Never in source code, YAML config, DAG files, or comments.
2. **No infrastructure details in code** — Never include AWS account IDs, VPC IDs, subnet IDs, or S3 bucket names in code or comments. Use variables.
3. **Encryption everywhere** — AES-256 at rest (KMS), TLS 1.3 in transit. Reference KMS keys by alias, never raw key material.
4. **PII/PHI/PCI detection & masking** — ALL workloads MUST run PII detection (automatic via `shared/utils/pii_detection_and_tagging.py`). Classified fields must be masked in logs, error messages, query results, and debug output. Never log actual values of sensitive fields. Lake Formation LF-Tags applied for column-level access control.
5. **Regulatory compliance** — Ask about GDPR, CCPA, HIPAA, SOX, PCI DSS requirements during discovery. Apply appropriate controls: tag-based access control (TBAC), data retention policies, audit trails, encryption at rest and in transit.
6. **Audit logging** — All data access, transformations, quality checks, and PII tag changes log: who (user/agent ID), what (operation), when (timestamp), where (dataset). CloudTrail enabled for all Lake Formation operations.
7. **Least privilege** — Each agent/task uses minimum required IAM permissions. No wildcard (`*`) actions or resources.
8. **Input validation** — Validate all user inputs before use in SQL, file paths, shell commands, or API calls. Prevent injection attacks.
9. **Bronze immutability** — Bronze zone data is NEVER modified after ingestion. Any code that attempts to update Bronze data is a bug.
10. **Quality gates block promotion** — Data MUST pass quality checks before moving to the next zone. No bypassing quality gates.
11. **Immutable audit logs** — Audit logs cannot be deleted or modified. Use append-only storage.

## Data Zone Rules

| Zone | Mutability | Quality Gate | Partitioning | Format |
|---|---|---|---|---|
| Bronze | Immutable (write-once) | None (raw ingestion) | By ingestion date | Raw source format (CSV, JSON, Parquet) |
| Silver | Updatable (schema-enforced) | Score >= 0.80, no critical failures | By business dimensions | **Apache Iceberg on Amazon S3 Tables** (always) |
| Gold | Updatable (curated) | Score >= 0.95, no critical failures | By time + business dimensions | **Iceberg** (format/schema based on discovery — see below) |

**Silver is always Iceberg** — no exceptions. Registered in Glue Data Catalog. Time-travel enabled.

**Gold format is determined by use case** (asked during Phase 1 discovery):

| Use Case | Schema | Follow-up Questions |
|---|---|---|
| Reporting & Dashboards | Star Schema (fact + dims) | Data size, dashboard latency, SCD history |
| Ad-hoc Analytics | Flat denormalized Iceberg | Data size, time-travel needs |
| ML / Feature Engineering | Flat wide Iceberg | Data size, pre-computed features |
| API / Real-time Serving | Iceberg + DynamoDB cache | Latency, QPS |

Default: **Iceberg tables** (time-travel, ACID, schema evolution, works with Athena/Redshift/EMR).

## Quality Standards

- **5 dimensions**: Completeness, Accuracy, Consistency, Validity, Uniqueness
- **Quality checks are deterministic** — same data always produces same score
- **Critical rule failures block zone promotion** regardless of overall score
- **Anomaly detection**: outliers (>3 std dev), distribution shifts, volume anomalies (>20% deviation), null spikes
- **Historical comparison**: always compare current run against baseline
- **PII detection** (automatic): AI-driven scanning after profiling, Lake Formation LF-Tags applied for column-level security, supports 12 PII types with 4 sensitivity levels (CRITICAL/HIGH/MEDIUM/LOW)

## Testing Strategy

- **Unit tests**: Jest + fast-check for every agent method. Mock external dependencies.
- **Property-based tests**: Transformation idempotency, lineage completeness, quality monotonicity, schema preservation, Bronze immutability.
- **Integration tests**: End-to-end Bronze→Silver→Gold pipeline, NL query processing, scheduled workflow execution, agent coordination, auth flows.
- **Coverage target**: 80% minimum.

When writing tests, place them in `workloads/{name}/tests/` for workload-specific tests or project-root `tests/` for shared infrastructure.

## Transformation Rules

- Transformations MUST be **idempotent** — running twice produces identical output.
- Never drop records silently — quarantine failed records with error context.
- Schema evolution: new fields → add with `nullable=true`; removed fields → keep with nulls; type changes → safe cast, quarantine failures.
- Always record lineage: source dataset, target dataset, transformation type, timestamp.
- Always validate output schema against the SageMaker Catalog before writing.

## Airflow DAG Rules

Detailed DO/DON'T list is in `SKILLS.md` under the Orchestration DAG Agent. Key highlights:

**Always**: `catchup=False`, `max_active_runs=1`, `retries=3`, exponential backoff, `on_failure_callback`, `TaskGroup` for stage organization, Airflow Variables for config.

**Never**: Hardcoded secrets, `SubDagOperator`, `provide_context=True`, `start_date=datetime.now()`, `depends_on_past=True` (without justification), inline computation in DAG files, disabled retries in production.

## Working With This Repo

### Starting a New Onboarding Workload

1. Ask the user for source, destination, transformation, quality, and scheduling details.
2. Check `workloads/` and `shared/` for existing assets to reuse.
3. Create the workload folder structure under `workloads/{name}/`.
4. Generate config YAML files from user answers.
5. Generate transformation scripts, quality checks, and the Airflow DAG.
6. Create a `README.md` in the workload folder.
7. Present the full plan for approval before writing files.

### Modifying an Existing Workload

1. Read ALL existing files in `workloads/{name}/` before making changes.
2. Understand the current pipeline flow from the DAG and config files.
3. Make targeted edits — do not regenerate files that don't need changes.
4. Update the workload `README.md` if behavior changes.
5. Run existing tests to verify nothing breaks.

### Adding Shared Utilities

1. Check if a similar utility already exists in `shared/utils/`.
2. If adding new shared code, ensure it has no workload-specific logic.
3. Add tests for shared utilities.
4. Update any workloads that could benefit from the new shared code.

## Error Handling Philosophy

Errors fall into three categories. The Data Onboarding Agent decides escalation:

| Category | Examples | Action |
|---|---|---|
| **Retryable** | Network timeout, API throttling, transient S3 errors | Retry with exponential backoff (max 3 attempts) |
| **Fixable** | Schema mismatch, missing config, quality below threshold | Ask the human for correction |
| **Fatal** | Invalid credentials, source permanently offline, data corruption | Halt pipeline, alert human immediately |

Never silently swallow errors. Log full context (agent, operation, input summary, error type) and escalate appropriately.

## Glossary

| Term | Meaning |
|---|---|
| Bronze Zone | Raw, immutable data as ingested from source (original format preserved) |
| Silver Zone | Cleaned, validated, schema-enforced data — **always Apache Iceberg on S3 Tables** |
| Gold Zone | Curated, business-ready data — Iceberg tables in format determined by use case (star schema, flat, etc.) |
| Apache Iceberg | Open table format for Silver and Gold zones — provides ACID transactions, time-travel, schema evolution, partition pruning |
| S3 Tables | Amazon S3 bucket type optimized for Apache Iceberg tables — automatic compaction and catalog integration |
| SageMaker Catalog | Extends Glue Data Catalog with custom metadata columns — stores column roles, business context, PII flags, relationships |
| SynoDB | Metrics & SQL Store — seed SQL examples + queries the Analysis Agent learns over time |
| Knowledge Graph | Vector embeddings for semantic search (OpenSearch) |
| MCP Layer | Model Context Protocol — standard interface for AI model interaction with the platform |
| Quality Gate | Threshold check that blocks data from advancing to the next zone |
| Lineage | Record of data provenance — which source produced which target via which transformation |
| SCD Type 2 | Slowly Changing Dimension pattern — preserves historical records in Gold zone dimension tables |
| Star Schema | Fact table (measures + FK keys) + dimension tables (attributes) — recommended for reporting/BI use cases |
