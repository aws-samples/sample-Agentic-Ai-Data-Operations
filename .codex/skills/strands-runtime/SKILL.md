---
name: strands-runtime
description: Run the ADOP headless orchestration through AWS Strands Agents.
---

# Optional AWS Strands runtime

Use this skill when the user explicitly asks to run ADOP through Strands.
The runtime is headless and reuses the existing ADOP contracts, renderer,
requirements audit, test gates, and tracing.

```bash
python3 scripts/run_strands.py status
python3 scripts/run_strands.py run \
  --args <path-to-onboarding-args.json> \
  --region <aws-region> \
  --model <bedrock-model-id>
```

Use `--dry-run` for an offline contract check. AgentCore is an optional
deployment target and must not be treated as a prerequisite for local or CI
runs.
