---
name: command-devops-workflow
description: Make a completed ADOP workload production-ready with monitoring, alerting, cost controls, and a runbook.
---

# ADOP production readiness

1. Read `AGENTS.md`, the workload `run/context.json`, and
   `.codex/skills/command-devops-workflow/SKILL.md`.
2. Confirm the workload has passed its onboarding, quality, audit, and
   deployment prerequisites.
3. Run the requirements auditor and present its artifact/product inventory to
   the human before IaC generation.
4. Ask the human to select one or more IaC formats and confirm the target
   products (S3, Iceberg, Glue, Lake Formation, Snowflake); never infer them.
5. Spawn one IaC generation job per approved format only after the audit passes.
6. Follow the canonical DevOps workflow for monitoring, alerting, runbooks,
   cost tags, budgets, backup/DR, and log retention.
7. Keep all infrastructure changes workload-scoped and least-privilege.
8. Do not deploy or change AWS resources without the required human approval,
   deployment gate, and human-provided principals.
9. For production agent hosting, use the documented AgentCore Runtime,
   authenticated AgentCore Gateway, and AgentCore policy boundary.

The repository's native `.codex/` skill and `AGENTS.md` remain authoritative.
