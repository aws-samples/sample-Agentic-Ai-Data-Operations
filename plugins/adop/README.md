# ADOP Codex plugin

This plugin exposes ADOP workflow entry points to Codex:

- `setup` — verify the current checkout and required native surfaces;
- `command-onboard-workflow` — run human-approved Bronze-to-Silver-to-Gold onboarding;
- `command-devops-workflow` — prepare a completed workload for production;
- `security-review` — review changes for security and policy-bypass risks.

The plugin is designed to run inside an ADOP repository. The repository's
`AGENTS.md`, `.codex/` hooks and skills, shared Cedar engine, shared policies,
deterministic renderer, and deployment checks remain authoritative.

The plugin contains no credentials and no production MCP endpoint. Production
deployments must use the documented Amazon Bedrock AgentCore Runtime,
authenticated AgentCore Gateway, and AgentCore policy boundary.
