# ADOP — Claude Code Plugin

A Claude Code plugin that packages the **Agentic Data Operations Platform (ADOP)** reference
architecture into installable slash commands, sub-agents, skills, and a validation hook.

Describe a data source in natural language and ADOP orchestrates specialized sub-agents to
generate a **fully tested Bronze→Silver→Gold pipeline** — PySpark ETL, data-quality checks,
Airflow/Step Functions DAG, and an OWL semantic layer — with **inline compliance controls**
(GDPR, CCPA, HIPAA, SOX, PCI DSS).

> Adapted from the blog *"Agentic Data Operations Platform (ADOP): Data engineering into hours"*
> and `github.com/aws-samples/sample-Agentic-Ai-Data-Operations`.

## Design principle: agents in dev, artifacts in prod

ADOP is a **build-time accelerator, not a runtime dependency**. Agents reason and generate in
development; CI/CD promotes the **deterministic artifacts** (PySpark, SQL, DAGs, IAM/Cedar
policies) to prod. Production runs the artifacts **without calling a model** — so pipelines
stay auditable and cost-predictable.

## What's in the plugin

```
adop-plugin/
├── .claude-plugin/
│   ├── plugin.json         # plugin manifest
│   └── marketplace.json    # local marketplace entry (for /plugin marketplace add)
├── commands/
│   ├── onboard-workflow.md # /onboard-workflow — build a pipeline
│   └── devops-workflow.md  # /devops-workflow — production readiness
├── agents/                 # 6 sub-agents (metadata, quality, ontology, transform, orchestration, devops)
├── skills/
│   ├── decision-engine/    # "AI clone" standards + guardrails + invariants (with config/)
│   └── data-compliance/    # one regulation prompt per framework (regulations/)
└── hooks/
    ├── hooks.json          # PostToolUse → validate generated artifacts
    └── validate_artifacts.py
```

### Slash commands
- **`/onboard-workflow [REGULATION] <description>`** — orchestrates Phase 0→5, fans out
  sub-agents, and lands a tested pipeline under `workloads/<name>/`. A regulation prefix
  (`HIPAA`, `PCI`, …) triggers compliance-critical (Opus) build + parallel execution.
- **`/devops-workflow <workload> [framework]`** — generates IaC, monitoring, cost tags, and a
  runbook to promote a workload.

### Sub-agents (generate files only — no MCP/AWS/CLI)
`metadata-agent` · `data-quality-agent` · `ontology-agent` · `transformation-agent` ·
`orchestration-agent` · `devops-agent`

### Skills
- **decision-engine** — encodes your architecture standards and the 5-step tool-selection
  hierarchy, plus the mandatory invariants (Bronze immutable, quality gates, zone-scoped KMS,
  no creds in code, MCP-first, …). Edit `skills/decision-engine/config/` with your real values.
- **data-compliance** — inline controls applied at onboarding. One prompt file per framework in
  `skills/data-compliance/regulations/`. Legal reviews a prompt, not the code.

### Hook
- **validate-artifacts** (`PostToolUse` on Write/Edit) — checks anything written under
  `workloads/`: Python must parse, no hardcoded credentials (BLOCK), and nudges for DAG retries
  and Glue data-lineage (WARN). Implements Phase 4.5 validation.

## Install

From the directory containing `adop-plugin/`:

```
# In Claude Code
/plugin marketplace add ./adop-plugin
/plugin install adop@adop-marketplace
```

Or point Claude Code at the published repo marketplace, then `/plugin install adop`.

Verify:
```
/help          # should list /onboard-workflow and /devops-workflow
/agents        # should list the six adop sub-agents
```

## Quick start

```
/onboard-workflow HIPAA
Onboard claims data from s3://data-lake/bronze/claims/date=YYYY-MM-DD/claims.csv into Silver
with dedup on claim_id and not-null policy_number, and into a flat denormalized Gold Iceberg
table with derived measures (net_paid_ratio, days_to_submission, denial_category). Run daily at
03:00 UTC. Apply HIPAA controls with PHI masking in Silver and PHI suppression in Gold.
```

The agent asks discovery questions, profiles a sample, presents metadata for approval, then
generates the pipeline under `workloads/claims/`.

## Notes & responsibility

- **Not legal advice.** The regulation prompts encode common control patterns to *support*
  compliance efforts. You are responsible for validating controls meet your actual obligations.
- Agents may process regulated/PII data in development — review your data-handling practices and
  access controls before promoting artifacts to production.
- The real reference implementation targets AWS but extends to any service with a CLI or MCP
  interface (hybrid/multi-cloud).
