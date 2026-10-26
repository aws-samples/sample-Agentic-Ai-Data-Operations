---
inclusion: auto
name: adop-strands-runtime
description: >-
  The optional headless AWS Strands runtime for ADOP: scripts/run_strands.py, --dry-run, and the AgentCore deployment target. Load only when asked about running ADOP headlessly, in CI, or on Strands/AgentCore.
---
# Optional ADOP Strands runtime

Kiro can run the headless ADOP workflow through the shared AWS Strands runtime.
This is opt-in and does not replace Kiro's human discovery gate.

```text
python3 scripts/run_strands.py status
python3 scripts/run_strands.py run \
  --args <path-to-onboarding-args.json> \
  --region <aws-region> \
  --model <bedrock-model-id>
```

Use `--dry-run` to verify the orchestration contract without calling Bedrock.
AgentCore is optional and is not required for local or CI execution.
