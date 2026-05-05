# Prompts - Agent-Based Organization

This folder contains all prompts organized by agent responsibility. Each agent has its own folder with related prompts.

## Agent Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AGENTIC WORKFLOW                              │
└─────────────────────────────────────────────────────────────────────────┘

  🏗️ Environment Setup       📊 Data Onboarding        🧬 Ontology Staging   🚀 DevOps
       Agent                      Agent                     Agent             Agent
         │                          │                         │                 │
         │ Sets up AWS              │ Onboards data           │ Emits OWL +     │ Automates
         │ infrastructure           │ Bronze→Silver→Gold      │ R2RML for AWS Semantic Layer │ CI/CD
         │                          │                         │                 │
         ▼                          ▼                         ▼                 ▼
   IAM, S3, KMS,            Route → Discover →        ontology.ttl +     Monitor, deploy,
   Glue, LF-Tags,          Profile → Generate →       mappings.ttl       optimize, heal
   MWAA, Gateway            Deploy artifacts          (local, for AWS Semantic Layer) pipelines
```

## Quick Navigation

| Agent | Folder | When to Use | Status |
|-------|--------|-------------|--------|
| **Environment Setup** | [`environment-setup-agent/`](environment-setup-agent/) | First time in AWS account | ✅ Ready |
| **Data Onboarding** | [`data-onboarding-agent/`](data-onboarding-agent/) | Per data source (repeatable) | ✅ Ready |
| **Ontology Staging** | [`data-onboarding-agent/ontology-staging-agent.md`](data-onboarding-agent/) | Phase 7 Step 8.5, optional | ✅ Ready |
| **DevOps** | [`devops-agent/`](devops-agent/) | Continuous operations | 📝 Coming Soon |
| **Examples & Helpers** | [`examples/`](examples/) | Demo data generation, testing | ✅ Ready |

## Typical User Journey

### First Time Setup (Run Once)

```bash
# Step 1: Set up AWS infrastructure
📂 environment-setup-agent/
  ├── setup-aws-infrastructure.md     (20 min)
  ├── deploy-agentcore-gateway.md     (15 min - optional)
  └── deploy-agentcore-runtime.md     (10 min - optional)

# Result: AWS account ready for data onboarding
```

### Onboarding a Data Source (Per Source)

```bash
# Step 2: Onboard data through Bronze → Silver → Gold
📂 data-onboarding-agent/
  ├── 01-route-check-existing.md       (< 1 min)
  ├── 03-onboard-build-pipeline.md     (45 min - master: phases 0-5)
  ├── 04-enrich-link-datasets.md       (5 min - optional)
  └── 05-govern-trace-lineage.md       (5 min - optional)

📂 examples/ (for demos/testing)
  └── generate-synthetic-data.md       (2-5 min - create sample data)

# Result: workloads/{name}/ with pipeline, DAG, tests deployed to AWS
```

### Analyzing Data (On-Demand)

```bash
# Step 3: Create dashboards and run queries
📂 data-analysis-agent/
  └── create-dashboard.md             (10 min)

# Result: QuickSight dashboard showing Gold zone data
```

### Automating Operations (Future)

```bash
# Step 4: Set up CI/CD and monitoring
📂 devops-agent/
  └── (Coming Q2-Q3 2026)

# Result: Automated deployments, monitoring, self-healing
```

## Agent Details

### 🏗️ Environment Setup Agent

**Purpose**: One-time AWS infrastructure setup

**Outputs**:
- IAM roles (13 MCP servers + workload execution)
- S3 buckets (bronze/silver/gold zones)
- KMS keys (encryption)
- Glue databases
- Lake Formation LF-Tags
- MWAA environment (Airflow)
- MCP Gateway (optional)
- Runtime Agent (optional)

**Read more**: [`environment-setup-agent/README.md`](environment-setup-agent/README.md)

---

### 📊 Data Onboarding Agent

**Purpose**: Orchestrate Bronze → Silver → Gold pipeline creation

**Workflow**:
1. **Route**: Check if data already onboarded
2. **Discover**: Ask questions about source, schema, quality
3. **Validate**: Prevent duplicates
4. **Profile**: Sample data, detect PII, spawn Metadata Agent
5. **Generate**: Spawn 3 sub-agents (Transformation, Quality, Orchestration)
6. **Deploy**: Upload to AWS (Glue, S3, LF-Tags, MWAA)
7. **Enrich**: Link to other datasets (optional)
8. **Govern**: Audit trail, lineage graph (optional)

**Outputs**:
- `workloads/{name}/` folder with pipeline code, DAG, tests
- Deployed Glue jobs (PySpark + Iceberg)
- Lake Formation permissions
- MWAA DAG running on schedule

**Read more**: [`data-onboarding-agent/README.md`](data-onboarding-agent/README.md)

---

### 🧬 Ontology Staging Agent

**Purpose**: Emit OWL ontology + R2RML mappings from `semantic.yaml` + Glue Catalog, staged locally for AWS Semantic Layer handoff.

**How it works**:
1. Reads `workloads/{name}/config/semantic.yaml` (column roles, relationships, hierarchies, PII)
2. Reads deployed Glue table schema via `glue-athena` MCP (`get_table`)
3. Induces OWL2 classes + datatype/object properties + subclass hierarchy
4. Generates R2RML TriplesMaps wiring classes to physical tables
5. Validates Turtle with rdflib (auto-fix + retry up to 2×)
6. Writes `ontology.ttl`, `mappings.ttl`, `ontology_manifest.json` locally

**Outputs** (all under `workloads/{name}/config/`):
- `ontology.ttl` — OWL2 classes, properties, hierarchy, PII annotations
- `mappings.ttl` — R2RML linking OWL to Glue tables
- `ontology_manifest.json` — version, checksums, steward checklist, `state: STAGED_LOCAL`

**Not in scope**: T-Box reasoning, SHACL authoring, publish, VKG reload — all owned by Data Steward inside the AWS Semantic Layer platform.

**Read more**: [`data-onboarding-agent/ontology-staging-agent.md`](data-onboarding-agent/ontology-staging-agent.md)

---

### 🚀 DevOps Agent (Coming Soon)

**Purpose**: CI/CD, monitoring, cost optimization, self-healing

**Planned Features**:
- Automated deployment on git push
- Pipeline failure alerts (Slack, email)
- Data quality drift detection
- Cost optimization recommendations
- Auto-retry failed jobs

**Status**: Design phase, planned for Q2-Q3 2026

**Read more**: [`devops-agent/README.md`](devops-agent/README.md)

---

## Supporting Content

| File/Folder | Purpose |
|-------------|---------|
| `examples.md` | Example workloads (sales, customers, healthcare, financial) |
| `PROPOSED_STRUCTURE.md` | Migration plan for this reorganization |

## Migration from Old Structure

**Old paths → New paths**:

| Old | New |
|-----|-----|
| `00-setup-environment.md` | `environment-setup-agent/01-setup-aws-infrastructure.md` |
| `01-route-check-existing.md` | `data-onboarding-agent/01-route-check-existing.md` |
| `02-generate-synthetic-data.md` | `examples/generate-synthetic-data.md` (demo/testing helper) |
| `03-onboard-build-pipeline.md` | `data-onboarding-agent/03-onboard-build-pipeline.md` (kept as master) |
| `04-enrich-link-datasets.md` | `data-onboarding-agent/04-enrich-link-datasets.md` |
| `05-consume-create-dashboard.md` | `data-analysis-agent/create-dashboard.md` |
| `06-govern-trace-lineage.md` | `data-onboarding-agent/05-govern-trace-lineage.md` |
| `07-fix-iceberg-glue.md` | `data-onboarding-agent/troubleshooting/01-fix-iceberg-glue.md` |
| `08-deep-agent-logging.md` | `data-onboarding-agent/troubleshooting/02-deep-agent-logging.md` |
| `09-deploy-agentcore-gateway.md` | `environment-setup-agent/02-deploy-agentcore-gateway.md` |
| `10-deploy-agentcore-runtime.md` | `environment-setup-agent/03-deploy-agentcore-runtime.md` |
| `regulation/` | `data-onboarding-agent/regulation/` |
| `admin/` | Merged into `environment-setup-agent/` |

## Related Documentation

| File | Purpose |
|------|---------|
| `../CLAUDE.md` | Project-level configuration |
| `../SKILLS.md` | Detailed agent skill definitions |
| `../MCP_GUARDRAILS.md` | MCP tool selection rules per phase |
| `../docs/workflow-diagrams.md` | Visual workflow diagrams |
| `../docs/mcp-setup.md` | MCP server configuration |
| `../README.md` | Project overview |

---

**Start here**: [`environment-setup-agent/setup-aws-infrastructure.md`](environment-setup-agent/setup-aws-infrastructure.md) (first time only)

**Then go to**: [`data-onboarding-agent/01-route-check-existing.md`](data-onboarding-agent/01-route-check-existing.md) (per data source)
