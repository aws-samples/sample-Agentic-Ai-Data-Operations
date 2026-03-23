# Prompt Flow: Architecture, Modularization, and Security

> Presentation-ready overview of the Agentic Data Onboarding prompt system. Covers structure, modularization, dependency management, enterprise-grade patterns, and the security model.

---

## 1. Prompt Structure

The system uses **6 modular prompts**, each with a defined phase, purpose, inputs, outputs, and validation criteria. A single human prompt triggers a multi-agent pipeline that produces 20+ files and 100+ automated tests.

### The Six Prompts

| # | Prompt | Phase | What It Does | Key Output |
|---|--------|-------|--------------|------------|
| 1 | **ROUTE** | Pre-flight | Searches `workloads/` for existing pipelines matching the requested data source. Prevents duplicate onboarding. | Found / Not Found / Partial |
| 2 | **GENERATE** | Pre-flight | Creates synthetic test data with realistic quality issues (nulls, duplicates, type mismatches). Produces reproducible fixtures with seed control. | CSV fixtures in `shared/fixtures/` |
| 3 | **ONBOARD** | Core | **Master orchestrator.** Runs 4 internal phases (Discovery, Dedup, Profile, Build), spawns 4 sub-agents, enforces test gates. Produces a complete Bronze-to-Silver-to-Gold pipeline. | 20+ files: configs, scripts, DAG, SQL, tests |
| 4 | **ENRICH** | Post-build | Links two onboarded datasets via foreign key. Adds join semantics, FK validation, cross-workload DAG dependencies. | Updated semantic.yaml, scripts, DAG, quality rules |
| 5 | **CONSUME** | Post-build | Creates a QuickSight dashboard on Gold zone data. Configures data sources, datasets, visuals, refresh schedule, and row-level security. | analytics.yaml, QuickSight resources |
| 6 | **GOVERN** | Post-build | Traces data lineage across the full pipeline. Generates compliance documentation, impact analysis, and data product catalog entries. | data_product_catalog.yaml, lineage diagrams |

### Prompt Template Structure

Every prompt follows a consistent template:

```
Purpose:         Why this prompt exists
Prerequisites:   What must be true before running
Inputs:          What the human provides (structured sections)
Agent Mapping:   Which agent(s) execute this prompt
Outputs:         Files and artifacts created
Validation:      Commands to verify correctness
```

The ONBOARD prompt has 7 input sections: Source details, Schema + column roles, Semantic layer (aggregations, terms, filters), Zone configuration, Quality rules, Schedule, and Build instructions.

---

## 2. How Prompts Are Modularized

### Separation of Concerns

Each prompt owns exactly one responsibility. No prompt duplicates another's work:

```
ROUTE     = Routing (search/match)         -- no file creation
GENERATE  = Data synthesis                 -- creates fixtures only
ONBOARD   = Pipeline construction          -- creates full workload
ENRICH    = Relationship management        -- updates existing workloads
CONSUME   = Visualization                  -- creates dashboard layer
GOVERN    = Compliance & lineage           -- creates documentation
```

### Sub-Agent Decomposition (Inside ONBOARD)

The ONBOARD prompt decomposes into 4 specialized sub-agents, each running in an isolated context:

```
ONBOARD (Data Onboarding Agent -- main conversation, human-facing)
  |
  |-- Phase 1: Discovery (inline) -- ask structured questions
  |-- Phase 2: Dedup (inline)     -- scan for overlapping sources
  |
  |-- Phase 3: Profile            -- spawn Metadata Agent (sub-agent)
  |     Output: schema, null rates, value distributions
  |     Gate:   unit + integration tests must pass
  |
  |-- Phase 4.1: Metadata         -- spawn Metadata Agent (sub-agent)
  |     Output: source.yaml, semantic.yaml
  |     Gate:   43 tests must pass
  |
  |-- Phase 4.2: Transform        -- spawn Transformation Agent (sub-agent)
  |     Output: transformations.yaml, ETL scripts
  |     Gate:   61 tests must pass
  |
  |-- Phase 4.3: Quality          -- spawn Quality Agent (sub-agent)
  |     Output: quality_rules.yaml, check scripts
  |     Gate:   41 tests must pass
  |
  |-- Phase 4.4: DAG              -- spawn Orchestration Agent (sub-agent)
  |     Output: Airflow DAG, schedule.yaml
  |     Gate:   51 tests must pass
  |
  |-- Phase 5: Human Review       -- present all artifacts + 196 test results
```

**Key design principle**: Sub-agents generate code and config only. They never execute AWS operations. All AWS interactions happen in the main conversation via MCP tools or CLI, maintaining a single point of control.

### Workload Isolation

Every onboarding workload is self-contained in its own directory:

```
workloads/{name}/
  config/       -- source.yaml, semantic.yaml, transformations.yaml, quality_rules.yaml, schedule.yaml
  scripts/      -- extract/, transform/, quality/, load/
  dags/         -- {name}_dag.py
  sql/          -- bronze/, silver/, gold/
  tests/        -- unit/, integration/
  README.md
```

Shared, reusable components live in `shared/` (operators, hooks, utilities, templates). This means adding a new dataset never modifies an existing workload's files.

---

## 3. Dependency Management

### Prompt Dependency Graph

```
    GENERATE (optional)
        |
        | produces CSV fixtures
        v
ROUTE ---------> ONBOARD ---------> ENRICH
(required)       (required)         (optional, requires 2+ workloads)
must run first   core pipeline
                     |
                     |-----------> CONSUME (optional, requires Gold zone)
                     |
                     |-----------> GOVERN  (optional, requires workload exists)
```

### Dependency Rules

| Rule | Enforced By |
|------|-------------|
| ROUTE must run before ONBOARD | Router Agent checks workloads/ before proceeding |
| GENERATE runs before ONBOARD only when no real data exists | Human decision |
| ONBOARD sub-agents run sequentially: Metadata -> Transform -> Quality -> DAG | Test gates -- each must pass before the next spawns |
| ENRICH requires 2+ completed workloads | Validates both `workloads/{a}/` and `workloads/{b}/` exist |
| CONSUME requires Gold zone tables | Validates `sql/gold/` and quality gate pass at >= 0.95 |
| GOVERN requires at least 1 completed workload | Validates `workloads/{name}/` exists with all subdirectories |

### Data Flow Between Prompts

Information flows forward through the pipeline -- each prompt's output feeds the next:

```
Human Input --> ONBOARD Phase 1 (Discovery)
                    |
                    v
              Metadata Agent --> source.yaml, semantic.yaml (schema + business context)
                    |
                    v
              Transform Agent --> uses schema from Metadata Agent
                    |               + cleaning rules from human
                    |               + column roles from semantic.yaml
                    v
              Quality Agent --> uses schema from Metadata Agent
                    |             + baselines from profiling
                    |             + thresholds from human
                    v
              DAG Agent --> uses all scripts from Transform + Quality
                    |        + schedule from human
                    v
              ENRICH --> reads semantic.yaml from both workloads
                    |      adds FK relationships, join semantics
                    v
              CONSUME --> reads Gold zone schema + semantic.yaml
                           builds dashboard visuals from measures/dimensions
```

### Pattern Combinations

| Pattern | Prompt Chain | Result |
|---------|-------------|--------|
| Minimal | ROUTE -> ONBOARD | Single workload, Bronze->Silver->Gold |
| With Relationships | ROUTE -> ONBOARD (A) -> ONBOARD (B) -> ENRICH (A<->B) | Two workloads with validated FK |
| With Visualization | ROUTE -> ONBOARD -> CONSUME | Workload + business dashboard |
| Full Production | ROUTE -> ONBOARD -> ENRICH -> CONSUME -> GOVERN | Complete data product |
| Demo Setup | GENERATE -> GENERATE -> ONBOARD -> ONBOARD -> ENRICH -> CONSUME | End-to-end demo with synthetic data |

**Phase 5: Deployment & Verification**: After human approval in Phase 4, the ONBOARD prompt continues with deployment (Step 5.8 MWAA + Step 5.9 smoke tests). See SKILLS.md Phase 5 and prompts/03-onboard-build-pipeline.md Steps 9-10 for the 8 post-deployment smoke tests (S3 bucket verification, Glue catalog registration, IAM permissions, KMS key access, data quality baseline, Iceberg metadata validation, Airflow DAG validation, and end-to-end query test).

**Regulation Prompts**: `prompts/regulation/` provides optional compliance add-ons (GDPR, CCPA, HIPAA, SOX, PCI DSS) that can be loaded during ONBOARD Phase 1 when regulatory requirements are identified. These prompts inject additional quality rules, audit requirements, and data retention policies.

---

## 4. Enterprise-Grade Patterns

### 4.1 Automated Test Gates

Every sub-agent's output is gated by automated tests. No artifact moves forward without passing:

```
Sub-agent returns artifacts
    |
    v
Run unit + integration tests (pytest)
    |
    +-- ALL PASS --> Proceed to next sub-agent
    |
    +-- SOME FAIL
            |
            v
        Retry count < 2?
            |
            +-- YES --> Re-spawn sub-agent with error context
            |           (original context + failure details + "fix these")
            |
            +-- NO  --> ESCALATE TO HUMAN
                        Show: which agent, which tests, error details,
                        what the agent tried. Human decides: fix/skip/abort.
```

**Verified results**: 3 workloads onboarded with 649 total tests (196 + 211 + 242) -- all passing.

### 4.2 Human-in-the-Loop at Every Critical Juncture

| Decision Point | What the Human Sees | Options |
|----------------|---------------------|---------|
| Phase 1: Discovery | Structured questions grouped by downstream agent | Answer or modify |
| Phase 3: Profiling | Column types, null rates, value distributions, PII flags, sample rows | Confirm or adjust |
| Phase 5: Review | All artifacts + test results in a single summary | Approve / Change / Abort |
| Post-build | ENRICH, CONSUME, GOVERN prompts are human-initiated | Run or skip each |

### 4.3 Idempotent Pipelines

Every transformation is idempotent -- running twice with the same input produces identical output:
- Verified via SHA-256 checksum comparison (guardrail OPS-001)
- Rejected rows go to quarantine tables (never silently dropped -- guardrail DQ-003)
- Row accounting enforced: `input_count == output_count + quarantine_count`

### 4.4 Quality Gates Block Zone Promotion

Data cannot move to the next zone without passing quality thresholds:

| Zone Boundary | Threshold | Enforcement |
|---------------|-----------|-------------|
| Landing -> Staging (Silver) | Quality score >= 80% | DQ-001 Cedar policy |
| Staging -> Publish (Gold) | Quality score >= 95% | DQ-001 Cedar policy |
| Any zone | No critical rule failures | DQ-002 Cedar policy |

### 4.5 Medallion Architecture with Immutable Landing

```
Landing (Bronze)          Staging (Silver)           Publish (Gold)
-----------------         ----------------           ---------------
Raw source format         Apache Iceberg on          Iceberg tables
(CSV, JSON, Parquet)      Amazon S3 Tables           (star schema, flat,
                                                      or use-case driven)
IMMUTABLE after write     Schema-enforced            Curated, aggregated
Write-once, never modify  Quality >= 80%             Quality >= 95%
KMS: alias/landing-key    KMS: alias/staging-key     KMS: alias/publish-key
```

Data is re-encrypted with zone-specific KMS keys at every zone boundary (guardrail OPS-002).

### 4.6 Observability and Audit

- **Guardrail summary**: 16 guardrails checked across 12 pipeline steps, results printed in a structured table
- **Audit log entries**: Every pipeline step logs who (agent/user ID), what (operation), when (ISO 8601), where (dataset)
- **Cedar decision logging**: Every policy evaluation is recorded with engine type (local/AVP), decision, and reasoning
- **CloudTrail integration**: In production, AVP decisions are automatically logged to CloudTrail

---

## 5. Security Model

### 5.1 Cedar Policy Engine (Amazon Verified Permissions)

All security, quality, integrity, and operational guardrails are externalized as **Cedar policies** -- Amazon's authorization policy language. This replaces inline boolean checks with a formal policy-as-code engine.

```
Pipeline Step (Python)
    |
    | runs actual check logic (regex, row counts, checksums)
    | passes boolean results + attributes as Cedar context
    v
CedarPolicyEvaluator
    |
    +-- Local mode (dev/test): cedarpy or JSON fallback
    +-- AVP mode (production): boto3 verifiedpermissions.is_authorized()
    |
    v
Allow / Deny decision (authoritative)
    |
    v
CloudTrail (automatic in AVP mode)
```

### 5.2 The 16 Guardrails

| Category | Code | What It Checks |
|----------|------|----------------|
| **Security** | SEC-001 | No hardcoded secrets (regex scan for AWS keys, passwords, tokens) |
| | SEC-002 | KMS key alias exists and is in Enabled state |
| | SEC-003 | PII columns masked (SHA-256 hash or `***REDACTED***`) |
| | SEC-004 | TLS 1.3 enforced on all data transfers |
| **Data Quality** | DQ-001 | Quality score meets zone threshold (80% Silver, 95% Gold) |
| | DQ-002 | No critical rule failures (PK not-null, PK unique) |
| | DQ-003 | No data dropped silently (input = output + quarantine) |
| | DQ-004 | Row count within 20% of historical baseline |
| **Integrity** | INT-001 | Landing zone immutability (no overwrites) |
| | INT-002 | FK referential integrity >= 90% |
| | INT-003 | Derived column formulas verified within 1% tolerance |
| | INT-004 | Output schema matches expected schema exactly |
| **Operational** | OPS-001 | Idempotency (re-run produces identical output via SHA-256) |
| | OPS-002 | Encryption re-keyed at zone boundaries |
| | OPS-003 | Audit log entry written for every step |
| | OPS-004 | Iceberg metadata sidecar generated |

Each guardrail is a Cedar `forbid` policy that blocks the action when the check fails. Default `permit` rules allow all actions -- the `forbid` policies selectively override when conditions are violated.

### 5.3 Agent Authorization (Least Privilege)

7 agents, each with Cedar policies defining exactly what they can and cannot do:

| Agent | Read | Write | MCP Tools | Key Restriction |
|-------|------|-------|-----------|-----------------|
| **Router** | All workload files | Nothing | No | Read-only gatekeeper |
| **Onboarding** | All zones + files | All (orchestrator) | Yes | Must be main conversation |
| **Metadata** | Landing + Staging data | Config files only | No | Cannot write scripts or data |
| **Transformation** | Landing + Staging data | Script + SQL files | No | Cannot write to Publish zone |
| **Quality** | All zones (read) | Quality rules config | No | Cannot modify data |
| **DAG** | All configs (read) | DAG files only | No | Cannot access data directly |
| **Analysis** | Publish zone only | Nothing | No | Gold read-only |

**Sub-agents cannot invoke MCP tools.** Only the main-conversation orchestrator can execute AWS operations. This creates a single choke point for all infrastructure changes.

### 5.4 MCP Tool Governance

16 MCP servers are configured. Each pipeline phase has prescriptive rules for which tool to use:

| Layer | What | Example |
|-------|------|---------|
| **Loaded servers** (4) | IAM, Lambda, Redshift, CloudTrail -- tools available in main conversation | `mcp__iam__simulate_principal_policy` for permission checks |
| **CLI fallback** (12) | S3, Glue, KMS, SageMaker Catalog, etc. -- connection failed, use AWS CLI | `aws glue get-tables` when Glue MCP is unavailable |
| **Phase guardrails** | Per-phase rules dictate which tool is mandatory vs optional | "ALWAYS simulate IAM permissions before source access" |
| **Sub-agent isolation** | Sub-agents generate scripts/configs -- never execute AWS operations | Transformation Agent writes `bronze_to_silver.py` but doesn't run it |

### 5.5 Encryption Model

```
Source Data
    |
    v
Landing Zone  --[KMS: alias/landing-data-key]--> Encrypted at rest (AES-256)
    |
    v (re-encrypt at zone boundary -- OPS-002)
Staging Zone  --[KMS: alias/staging-data-key]--> Different key per zone
    |
    v (re-encrypt at zone boundary -- OPS-002)
Publish Zone  --[KMS: alias/publish-data-key]--> Different key per zone
```

- KMS keys are referenced by alias, never raw key material
- Key state is validated before every encrypt/decrypt (SEC-002)
- All transfers use TLS 1.3 (SEC-004)
- All key operations logged to CloudTrail

### 5.6 PII Protection

- PII columns identified in `semantic.yaml` (auto-detected by Glue PII Detection + human confirmation)
- PII is masked before promotion to Staging: SHA-256 hash or `***REDACTED***`
- PII values never appear in logs, error messages, query results, or debug output
- Guardrail SEC-003 samples 10 rows after transformation to verify masking

### 5.7 Security Checklist (Enforced by All Agents)

Every agent follows these non-negotiable rules:

1. No hardcoded secrets -- credentials from Secrets Manager, Airflow Connections, or env vars only
2. No infrastructure details in code -- no AWS account IDs, VPC IDs, subnet IDs, or bucket names
3. Encryption everywhere -- AES-256 at rest (KMS), TLS 1.3 in transit
4. PII/PHI/PCI masking in all outputs
5. Audit logging on every data access and transformation
6. Least privilege IAM -- no wildcard (`*`) actions or resources
7. Input validation before SQL, file paths, shell commands, or API calls
8. Landing zone immutability -- Bronze data is never modified after ingestion
9. Quality gates block promotion -- no bypassing
10. Immutable audit logs -- append-only, cannot be deleted or modified

---

## 6. How It All Fits Together

### One Prompt, Full Pipeline

```
Human writes ONE ONBOARD prompt
    |
    v
System produces:
    +-- 5+ config files (source, semantic, transformations, quality rules, schedule)
    +-- 4+ ETL scripts (extract, transform, quality check, load)
    +-- 1 Airflow DAG
    +-- 4+ SQL files (per zone)
    +-- 100+ automated tests (unit + integration)
    +-- 39 guardrail checks across 12 pipeline steps
    +-- 23 Cedar policies (16 guardrail + 7 agent authorization)
    +-- Audit trail for every operation
```

### End-to-End Flow

```
ROUTE (check existing)
  |
  v
ONBOARD (master prompt)
  |-- Discovery: human answers structured questions
  |-- Dedup: verify no overlap with existing workloads
  |-- Profile: Glue Crawler + Athena on 5% sample
  |-- Build: 4 sub-agents, each with test gate
  |-- Review: human approves all artifacts
  |
  v
ENRICH (link datasets) -- optional
  |
  v
CONSUME (create dashboard) -- optional
  |
  v
GOVERN (trace lineage) -- optional
```

### What Makes It Enterprise-Grade

| Dimension | Implementation |
|-----------|---------------|
| **Policy-as-Code** | 23 Cedar policies in `shared/policies/`, evaluated by Amazon Verified Permissions |
| **Automated Testing** | 649 tests across 3 workloads, mandatory test gates before every phase transition |
| **Human Oversight** | Human-in-the-loop at discovery, profiling, review, and deployment |
| **Audit Trail** | Every operation logged with who/what/when/where; CloudTrail in production |
| **Least Privilege** | Per-agent Cedar authorization; sub-agents cannot invoke AWS tools |
| **Encryption** | Zone-specific KMS keys, re-keyed at boundaries, TLS 1.3 in transit |
| **Data Quality** | 5-dimension quality framework, zone-specific thresholds, critical rule enforcement |
| **Idempotency** | SHA-256 verified; re-run produces identical output |
| **Immutability** | Landing zone is write-once; audit logs are append-only |
| **Retry + Escalation** | Sub-agents retry twice on failure, then escalate to human with full context |
| **MCP Governance** | Per-phase tool selection rules, sub-agent isolation from AWS operations |
| **Compliance** | GOVERN prompt produces lineage docs, data product catalog, impact analysis |
| **Post-Deployment Verification** | 8 mandatory smoke tests after deployment (S3, Glue catalog, IAM, KMS, DQ baseline, Iceberg metadata, DAG validation, end-to-end query) |
| **Deployment Script Standard** | Every workload includes `deploy_to_aws.py` as a standard artifact for repeatable AWS deployment |
