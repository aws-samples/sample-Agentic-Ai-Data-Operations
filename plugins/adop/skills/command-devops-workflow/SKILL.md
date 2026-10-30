---
name: command-devops-workflow
description: Make a completed ADOP workload production-ready with monitoring, alerting, cost controls, and a runbook.
---

# ADOP production readiness

1. Read `AGENTS.md`, the workload `run/context.json`, and
   `.codex/skills/command-devops-workflow/SKILL.md`.
2. Confirm the workload has passed its onboarding, quality, audit, and
   deployment prerequisites.
3. Follow the canonical DevOps workflow for monitoring, alerting, runbooks,
   cost tags, budgets, backup/DR, and log retention.
4. Keep all infrastructure changes workload-scoped and least-privilege.
5. Do not deploy or change AWS resources without the required human approval,
   deployment gate, and human-provided principals.
6. For production agent hosting, use the documented AgentCore Runtime,
   authenticated AgentCore Gateway, and AgentCore policy boundary.

The repository's native `.codex/` skill and `AGENTS.md` remain authoritative.
