---
name: security-review
description: Review ADOP changes for high-confidence security vulnerabilities and policy bypasses.
---

# ADOP security review

1. Read `AGENTS.md` and `.codex/skills/command-security-review/SKILL.md`.
2. Review only the pending ADOP changes and report high-confidence security
   findings with file and line references.
3. Check agent authorization, Cedar enforcement, secret handling, MCP/AWS
   access, deploy gates, deterministic code generation, PII controls, IAM
   scope, audit evidence, and production AgentCore boundaries.
4. Treat unknown/general agents as unable to invoke AWS or MCP tools.
5. Do not edit `shared/policies/**` or `run/deploy_gate.json`; policy changes
   require a human.

Return the findings in the format required by the canonical security-review
skill. Do not silently fix findings during a review.
