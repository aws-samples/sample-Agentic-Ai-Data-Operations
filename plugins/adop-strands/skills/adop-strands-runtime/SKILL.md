---
name: adop-strands-runtime
description: Run or test the ADOP data-onboarding workflow through AWS Strands Agents and Amazon Bedrock in an ADOP repository.
---

# ADOP Strands runtime

Use this skill when the user asks to run ADOP through AWS Strands, test the
Strands integration, or make a real Amazon Bedrock call.

This plugin is intended for an ADOP repository containing
`scripts/run_strands.py`, `runtimes/strands/`, `shared/orchestration/`, and the
workload contracts.

## Required workflow

1. Read the repository `AGENTS.md` and the workload's authoritative
   `run/context.json` before generating or changing artifacts.
2. Enforce the Phase 1 discovery gate. Do not invent source, credentials,
   transformations, PII, compliance, quality thresholds, schedule/timezone,
   ontology, or IAM principals. Record explicit human answers in the workload
   run evidence.
3. Prefer the repository's deterministic renderer for all generated scripts,
   DAGs, and SQL. Do not manually write renderer-owned artifacts.
4. Use the repository test gates and operational traces. A Bedrock response is
   not a successful phase unless the structured handoff and the test gate pass.
5. For a real call, use an explicitly configured AWS region and model. Verify
   AWS credentials without printing secrets. If the selected Bedrock model
   requires an inference profile, use the account's configured profile rather
   than retrying unsupported on-demand throughput.
6. Keep the run scoped to the requested workload. Do not deploy Glue, Lake
   Formation, MWAA, IAM, or other AWS infrastructure unless the user
   explicitly requests deployment and the required deployment approvals and
   human-provided principals are present.

## Commands

From the ADOP repository root:

```bash
python3 scripts/run_strands.py status
python3 scripts/run_strands.py run \
  --args <path-to-onboarding-args.json> \
  --region <aws-region> \
  --model <bedrock-model-or-inference-profile>
```

Use `--dry-run` only for a local contract check. Use `--no-review` only when
the user explicitly asks to omit the adversarial review; otherwise preserve the
review phase and report HIGH findings as a blocker.

AgentCore is optional. It is not required for local or CI Strands execution.
