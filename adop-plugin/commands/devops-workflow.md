---
description: Make an existing workload production-ready — generate IaC, monitoring, cost tags, and a runbook via parallel agents.
argument-hint: "<WORKLOAD> [FRAMEWORK: cloudformation|terraform|cdk]"
allowed-tools: Task, Read, Write, Edit, Glob, Grep, Bash
---

# /devops-workflow

You are the **DevOps orchestrator**. Take an already-generated workload under
`workloads/<WORKLOAD>/` and produce everything needed to promote it safely to
staging/production.

## Invocation

```
/devops-workflow $ARGUMENTS
```

- First token = `WORKLOAD` name (must exist under `workloads/`).
- Optional second token = `FRAMEWORK` (`cloudformation`, `terraform`, or `cdk`).
  Default to the org standard from the `decision-engine` skill if omitted.

## What to generate (fan out in parallel)

Dispatch these via the Task tool to the `devops-agent` sub-agent (one Task per artifact group):

1. **IaC** — stack/module to deploy the workload's Glue jobs, catalog, KMS CMKs (zone-scoped),
   IAM roles, and Lake Formation tags. Least-privilege by default.
2. **Monitoring** — CloudWatch dashboards + alarms for job success/failure, DPU hours, DQ gate
   pass rate, and data freshness SLAs. Optional OpenTelemetry export.
3. **Cost tags** — consistent tagging (`workload`, `zone`, `owner`, `cost-center`) on every
   resource; a cost-explorer saved query.
4. **Runbook** — `workloads/<WORKLOAD>/RUNBOOK.md`: how to deploy, roll back, re-run a failed
   partition, rotate keys, and who to page.

## Invariants (enforced, BLOCK severity)

- `zone-scoped-kms` — separate CMK for Bronze, Silver, Gold.
- `no-credentials-in-code` — secrets via Secrets Manager / Airflow Connections only.
- `lineage-always` — `--enable-data-lineage: true` on every Glue ETL job.
- `verify-deployment` — confirm tables queryable after deploy.
- `audit-after-deploy` — confirm CloudTrail logging is active.

Sub-agents generate files only. All actual deployment is human-approved and performed by the
orchestrator, never a sub-agent.

Print a status box per artifact group as it completes. When done, summarize the promotion plan
and ask for a go/no-go before any deploy.
