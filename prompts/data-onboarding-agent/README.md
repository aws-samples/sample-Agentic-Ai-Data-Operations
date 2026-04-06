# Data Onboarding Agent

**Agent Type**: Orchestrator (Human-in-the-loop)
**Runs**: Per data source (repeatable)
**Prerequisites**: Environment setup complete (see `../environment-setup-agent/`)

## Purpose

The Data Onboarding Agent orchestrates the end-to-end data pipeline creation: from discovery to deployment. It asks questions, spawns specialized sub-agents, validates outputs, and deploys artifacts to AWS.

## Architecture

```
Data Onboarding Agent (Main conversation, human-facing)
  │
  ├── Phase 0: Health Check & Auto-Detect
  ├── Phase 1: Discovery (ask questions)
  ├── Phase 2: Validation (dedup check)
  │
  ├── Phase 3: Profiling
  │   └── spawns → Metadata Agent (sub-agent)
  │
  ├── Phase 4: Artifact Generation
  │   ├── spawns → Transformation Agent (sub-agent)
  │   ├── spawns → Quality Agent (sub-agent)
  │   └── spawns → Orchestration Agent (sub-agent)
  │
  └── Phase 5: Deployment (uses MCP tools)
```

## Workflow: Bronze → Silver → Gold

This agent moves data through 3 zones:

| Zone | Description | Format | Quality Gate |
|------|-------------|--------|--------------|
| **Bronze** | Raw, immutable source data | Original format | None (raw ingestion) |
| **Silver** | Cleaned, validated, schema-enforced | Apache Iceberg (always) | Score >= 0.80 |
| **Gold** | Curated, business-ready analytics | Iceberg (star/flat/wide) | Score >= 0.95 |

## Prompts in This Folder

### Core Workflow (Run in Order)

| # | Prompt | Purpose | Time |
|---|--------|---------|------|
| 01 | `01-route-check-existing.md` | Check if data already onboarded | < 1 min |
| 02 | `03-onboard-build-pipeline.md` | **Master prompt**: Phases 0-5 (health, discovery, validation, profiling, artifacts, deployment) | 45 min |
| 03 | `04-enrich-link-datasets.md` | Link to other workloads (optional) | 5 min |
| 04 | `05-govern-trace-lineage.md` | Audit trail, lineage graph (optional) | 5 min |

**Note**: Prompt 02 covers all phases (0-5) in one master template. For synthetic data generation (demos/testing), see [`../examples/generate-synthetic-data.md`](../examples/generate-synthetic-data.md).

### Supporting Content

| Folder | Purpose |
|--------|---------|
| `regulation/` | GDPR, CCPA, HIPAA, SOX, PCI DSS compliance prompts |
| `troubleshooting/` | Fix Iceberg/Glue issues, debug agent logging |

## Quick Start

```bash
# Start from prompt 01
# Claude Code will guide you through 01 → 02 → 03 → 04

# Typical flow:
User: "Onboard product catalog from S3"
  ↓
Claude: Runs 01-route (checks workloads/)
  ↓
Claude: Runs 02-onboard (master prompt: phases 0-5)
  ├─ Phase 0: Health check (AWS resources + MCP servers)
  ├─ Phase 1: Discovery (asks questions about source, schema, quality)
  ├─ Phase 2: Validation (dedup check, confirm source)
  ├─ Phase 3: Profiling (sample data, detect PII, spawn Metadata Agent)
  ├─ Phase 4: Artifacts (spawn Transformation, Quality, DAG agents)
  └─ Phase 5: Deployment (deploy to AWS via MCP tools)
  ↓
User: Answers questions during Phases 1-2
  ↓
Claude: Runs 05-06-07-08 (profile → generate → deploy)
  ↓
Output: workloads/product_catalog/ with pipeline + DAG
```

## Phase Descriptions

### Phase 0: Health Check & Auto-Detect
**Purpose**: Verify environment before starting
- Scan AWS resources (IAM, S3, Glue, LF-Tags, MWAA)
- Check MCP server health (13 servers)
- Gate: Block if critical resources or REQUIRED MCP servers missing

### Phase 1: Discovery
**Purpose**: Understand the data
- Ask about source (S3 path, format, credentials)
- Identify columns (PK, PII, exclusions)
- Define transformations (dedup, nulls, types)
- Specify quality thresholds
- Set schedule (cron, dependencies)

### Phase 2: Validation
**Purpose**: Prevent duplicates
- Scan `workloads/*/config/source.yaml`
- Detect exact duplicates (block)
- Warn on overlaps (same bucket, different prefix)

### Phase 3: Profiling
**Purpose**: Understand data schema and quality
- Sample 5% of data via Glue Crawler + Athena
- Detect column types, nulls, distinct values
- Flag PII columns (name-based + content-based)
- Apply Lake Formation LF-Tags
- Spawn Metadata Agent (sub-agent)

### Phase 4: Artifact Generation
**Purpose**: Generate all pipeline code
- Spawn Transformation Agent → ETL scripts
- Spawn Quality Agent → quality checks
- Spawn Orchestration Agent → Airflow DAG
- Run tests (unit + integration)
- Gate: Block if tests fail

### Phase 5: Deployment
**Purpose**: Deploy to AWS
- Upload scripts to S3
- Create Glue jobs (PySpark + Iceberg)
- Grant Lake Formation permissions
- Deploy DAG to MWAA
- Verify deployment (smoke tests)

## Sub-Agents (Spawned by Phase 3-4)

| Sub-Agent | Spawned By | Purpose | MCP Access |
|-----------|------------|---------|------------|
| **Metadata Agent** | Phase 3 | Profile schema, detect PII, infer relationships | ❌ No |
| **Transformation Agent** | Phase 4 | Design transformations, generate ETL scripts | ❌ No |
| **Quality Agent** | Phase 4 | Design quality rules, generate checks | ❌ No |
| **Orchestration Agent** | Phase 4 | Generate Airflow DAG, dependencies | ❌ No |

**Note**: Sub-agents generate code/config only. Main agent deploys via MCP tools (Phase 5).

## Output Artifacts

After completing all phases, you have:

```
workloads/{name}/
├── config/
│   ├── source.yaml          (source details)
│   ├── semantic.yaml        (SageMaker Catalog metadata)
│   ├── transformations.yaml (Bronze→Silver→Gold logic)
│   ├── quality_rules.yaml   (quality thresholds)
│   └── schedule.yaml        (Airflow schedule)
├── scripts/
│   ├── extract/            (S3 → Bronze)
│   ├── transform/          (Bronze → Silver → Gold)
│   ├── quality/            (quality checks)
│   └── load/               (write Iceberg tables)
├── dags/
│   └── {name}_dag.py       (Airflow DAG)
├── tests/
│   ├── unit/               (pytest)
│   └── integration/        (end-to-end)
├── deploy_to_aws.py        (deployment script)
└── README.md
```

## Quality Gates

Data must pass quality gates to advance zones:

| Gate | Threshold | Critical Failures | Action |
|------|-----------|-------------------|--------|
| Bronze → Silver | Score >= 0.80 | 0 allowed | Block if failed |
| Silver → Gold | Score >= 0.95 | 0 allowed | Block if failed |

**Quality Dimensions**:
- Completeness (null rate)
- Accuracy (schema conformance)
- Consistency (cross-field validation)
- Validity (data type, range)
- Uniqueness (primary key dedup)

## Compliance (Regulation Prompts)

For regulated data, run a regulation prompt DURING Phase 1 discovery:

| Regulation | Prompt | Key Controls |
|------------|--------|--------------|
| **GDPR** | `regulation/gdpr.md` | Consent tracking, 365-day retention, right to erasure |
| **CCPA** | `regulation/ccpa.md` | Opt-out tracking, 730-day retention, right to know/delete |
| **HIPAA** | `regulation/hipaa.md` | PHI encryption, minimum necessary, 7-year audit |
| **SOX** | `regulation/sox.md` | 0.95+ quality gates, immutable Bronze, auditor roles |
| **PCI DSS** | `regulation/pci-dss.md` | CVV dropped, PAN tokenized, Luhn validation |

**When to apply**: Claude will ask "Any regulatory requirements?" during Phase 1. If yes, it loads the appropriate regulation prompt.

## Troubleshooting

**Issue**: "Workload already exists"
- Check: `workloads/{name}/` folder
- Action: Modify existing or use different name

**Issue**: "MCP server failed"
- Check: `claude mcp list`
- See: `../../docs/mcp-setup.md`

**Issue**: "Quality gate failed (score < 0.80)"
- Review: `workloads/{name}/tests/quality_report.json`
- Action: Fix data quality issues or adjust thresholds

**Issue**: "Glue job failed (Iceberg write)"
- See: `troubleshooting/fix-iceberg-glue.md`

**Issue**: "DAG not appearing in Airflow UI"
- Check: All `Variable.get()` have `default_var`
- Check: DAG file at root of MWAA dags/ prefix

## Related Documentation

- `../environment-setup-agent/README.md` - Run this first
- `../data-analysis-agent/README.md` - Run this after onboarding
- `../../SKILLS.md` - Detailed agent skill definitions
- `../../MCP_GUARDRAILS.md` - MCP tool selection rules per phase
- `../../docs/workflow-diagrams.md` - Visual diagrams of the workflow
- `../../CLAUDE.md` - Project-level configuration

## Examples

See `../examples.md` for:
- Sales transactions (CSV)
- Customer master (Parquet)
- Healthcare patients (HIPAA)
- Financial portfolios (SOX)

---

**Ready to onboard data?** Start with `01-route-check-existing.md`
