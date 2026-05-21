---
project: agentic-data-onboarding
stack: Python (Glue PySpark, Airflow DAGs), SQL, AWS, Apache Iceberg
status: design-complete, implementation pending
---

# CLAUDE.md — Agentic Data Onboarding System

Bronze → Silver → Gold data pipeline orchestration. Multi-agent architecture with AWS integration.

## STOP — Human-in-the-Loop Gate (Phase 1 Discovery)

**DO NOT GENERATE ANY PIPELINE CODE, SCRIPTS, CONFIGS, OR DAGS UNTIL YOU HAVE EXPLICIT HUMAN ANSWERS FOR ALL ITEMS BELOW.**

This is a human-in-the-loop gate. The HUMAN provides the rules. The agent does NOT guess or infer them.

### Required Questions (ask ALL before proceeding)

**Identify the zone first**, then ask zone-targeted questions (see `.claude/rules/00-zone-questions.md`):

- **Bronze** → source path, credentials, ingestion pattern, retention
- **Silver** → PK, dedup strategy, null handling, business logic, transformations
- **Gold** → business outcome, KPIs, aggregation grain, schema choice, BI tool

**Always ask regardless of zone:**
1. **PII/compliance** → which columns are PII? GDPR/CCPA/HIPAA/SOX/PCI?
2. **Quality** → thresholds per dimension, critical vs warning rules
3. **Scheduling** → cron expression, dependencies, failure handling

**Auto-discover first** (schema, format, nulls, row count) — then ask only what you couldn't discover. Present findings before questions.

### Completion Checklist — ALL must have HUMAN-PROVIDED answers

```
[ ] Zone identified (Bronze, Silver, Gold, or all)
[ ] Zone-specific questions answered (see rules/00-zone-questions.md)
[ ] Transformation rules confirmed by user (derived columns, calculations, custom logic — NEVER skip this even if you think "none needed")
[ ] PII columns and compliance requirements confirmed by user
[ ] Quality thresholds explicitly stated (or user says "use defaults")
[ ] Schedule explicitly stated by user
[ ] Ontology collection preference confirmed (opt-in/opt-out for semantic layer enrichment via Ontology agent)
```

**If ANY item is missing, ASK THE USER. Do not proceed.**

### NEVER do these

- NEVER guess dedup strategy from column names
- NEVER infer null handling from data observations
- NEVER assume quality thresholds without user stating them
- NEVER generate a schedule based on source frequency — ask
- NEVER assume PII columns from names alone — ask user to confirm
- NEVER skip the transformation question — even if you auto-derived type casts and PII masking, you MUST ask about derived columns, calculations, and custom business logic
- NEVER skip the ontology question — always ask whether the user wants semantic layer enrichment (opt-in)

You MAY profile data and PRESENT observations, then MUST ask: "How would you like to handle these?"

See `.claude/rules/01-human-gate-examples.md` for correct/incorrect behavior examples.

## Security Rules (Non-Negotiable)

1. **No hardcoded secrets** — use Secrets Manager, Airflow Connections, or env vars
2. **No infrastructure details in code** — no account IDs, VPC IDs, bucket names in source
3. **Encryption** — AES-256 at rest (KMS), TLS 1.3 in transit
4. **PII detection mandatory** — all workloads run `shared/utils/pii_detection_and_tagging.py`, LF-Tags + TBAC for column-level access
5. **Bronze immutability** — NEVER modify Bronze zone after ingestion
6. **Quality gates block promotion** — no bypassing
7. **Least privilege IAM** — no wildcard actions or resources
8. **Audit logging** — who, what, when, where for all operations

## Agent Behavior Protocol

1. **Route First** → check `workloads/` for existing data (found/not-found/partial)
2. **Ask Before Acting** → MANDATORY GATE above (Phase 1) — human provides all rules
3. **Deduplicate** → scan `workloads/*/config/source.yaml` for overlap (Phase 2)
4. **Profile** → 5% sample via Glue Crawler + Athena, present to human (Phase 3)
5. **Test Gates** → every sub-agent writes + passes tests before proceeding (Phase 4)
6. **Present Plan** → get human approval before multi-file changes

## Key Files

| File | Read When |
|---|---|
| `SKILLS.md` | Before acting as any agent |
| `TOOL_ROUTING.md` | Selecting which MCP tool to use |
| `MCP_GUARDRAILS.md` | Per-phase deploy guardrails |
| `tool-registry/servers.yaml` | Canonical MCP server list (13 servers) |
| `docs/workflow-diagrams.md` | Visual diagrams of flow |

## Folder Convention

```
workloads/{name}/
├── config/    # source.yaml, semantic.yaml, transformations.yaml, quality_rules.yaml, schedule.yaml
├── scripts/   # extract/, transform/, quality/, load/
├── dags/      # {name}_dag.py
├── sql/       # bronze/, silver/, gold/
├── tests/     # unit/, integration/
├── logs/      # Pipeline execution traces (trace_events.jsonl, run_*/)
└── README.md

shared/
├── operators/   # Reusable Airflow operators
├── hooks/       # Reusable Airflow hooks
├── utils/       # quality_checks.py, pii_detection_and_tagging.py, etc.
├── templates/   # dag_template.py, config_template.yaml
└── sql/common/  # Cross-workload SQL
```

## Data Zones

| Zone | Mutability | Quality Gate | Format |
|---|---|---|---|
| Bronze | Immutable | None | Raw source format |
| Silver | Updatable | >= 0.80 | Apache Iceberg on S3 Tables (always) |
| Gold | Updatable | >= 0.95 | Iceberg (schema per use case) |

Gold schema determined by use case (ask during Phase 1): Star Schema (reporting), Flat Iceberg (analytics/ML), Iceberg + DynamoDB (API serving).

## Mandatory: Workload Logs & Agent Tracing

Every workload MUST include a `logs/` directory. Every pipeline run MUST produce structured traces:

1. **`trace_events.jsonl`** — generated by `AgentTracer` for every run (operational trace)
2. **`decisions` array** — every sub-agent MUST include reasoning/alternatives in its `AgentOutput`
3. **`StructuredLogger`** — every ETL script MUST use it for row counts, transforms, quality scores

No pipeline is complete without logging. Do not skip `logs/` when creating a workload. Do not generate ETL scripts without `StructuredLogger` wired in.

Key files: `shared/logging/agent_tracer.py`, `shared/logging/trace_viewer.py`, `shared/utils/structured_logger.py`

## Deterministic Codegen (Non-Negotiable)

All artifacts under `workloads/*/scripts/`, `dags/`, `sql/` MUST be produced by
`shared.codegen.renderer.render()`. Free-form code generation is forbidden.

1. Sub-agents do NOT write code directly. They produce a spec (validated against
   `contracts/v1/*.schema.json`) and call the renderer.
2. The PreToolUse hook (`.claude/hooks/enforce_template_codegen.py`) blocks any
   Write/Edit/MultiEdit to those directories without the renderer token.
3. Every generated artifact has a 5-line header: spec_hash, template_id,
   template_hash, schema_version, rendered_at.
4. The drift validator (`shared.codegen.drift_validator`) runs in CI and as
   Step 4.5.2 in the orchestrator. Any drift fails the build.

If a slot is missing from the spec, the renderer raises MissingSlotError.
Do not work around this by editing the template — extend the spec schema and
bump template_version.

## Mandatory: Post-Deployment Verification (Step 5.9)

After deploying ANY workload to AWS, you MUST run `shared/utils/post_deployment_verifier.py` with 7 checks:

1. **Glue tables exist** — all Silver + Gold tables registered in catalog
2. **Athena queries work** — tables are queryable, not empty
3. **LF-Tags applied** — PHI columns tagged (PII_Classification, PII_Type, Data_Sensitivity)
4. **TBAC access control** — CRITICAL columns restricted to authorized roles
5. **KMS encryption** — key exists, rotation enabled
6. **MWAA DAG loaded** — no import errors, visible in Airflow
7. **CloudTrail events** — deployment operations logged (CreateTable, GrantPermissions)

Deployment is NOT complete until all checks PASS. If any fail, fix and re-verify.

## Additional Rules

Coding conventions, error handling, logging protocol, testing strategy, transformation rules, and glossary are in `.claude/rules/`. These load automatically — path-scoped rules load only when editing matching files.

**Deployment topology**: Default single-account. Multi-account opt-in via `docs/multi-account-deployment.md`.
