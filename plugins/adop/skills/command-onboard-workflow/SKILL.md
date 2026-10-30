---
name: command-onboard-workflow
description: Run ADOP human-approved Bronze-to-Silver-to-Gold onboarding in an ADOP repository.
---

# ADOP onboarding

This is the installable Codex entry point for the canonical ADOP onboarding
workflow.

Before acting:

1. Read `AGENTS.md` and the authoritative workload
   `workloads/<name>/run/context.json` when a workload already exists.
2. Read `.codex/skills/command-onboard-workflow/SKILL.md` and follow its phase
   ordering, discovery gate, sub-agent contracts, test gates, and deployment
   sequence.
3. Route first by checking `workloads/` for an existing workload.
4. Do not generate pipeline code, scripts, configs, or DAGs until the required
   human discovery answers are complete.
5. Preserve the deterministic renderer, Cedar checks, requirements audit,
   tracing, and workload evidence required by the repository.
6. Present inherited organization/domain/project zone contracts and accept them
   by default, or record only stricter per-run overrides. Keep source and target
   contracts separate and ask connector-specific questions.

The plugin does not replace the repository's project hooks or policy files.
Use the native `.codex/` workflow as the implementation authority. Never infer
PII, compliance, transformations, quality thresholds, schedule/timezone,
ontology preference, IAM principals, or deployment authorization.
