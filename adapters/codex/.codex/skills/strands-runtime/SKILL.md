---
name: strands-runtime
description: Run the ADOP headless orchestration through AWS Strands Agents.
---

# Optional AWS Strands runtime

Use this skill when the user explicitly asks to run ADOP through Strands.
Run `python3 scripts/run_strands.py status` first, then invoke the runtime with
the confirmed onboarding args JSON, AWS region, and Bedrock model ID.

AgentCore is an optional deployment target. The local and CI runtime must work
without it.
