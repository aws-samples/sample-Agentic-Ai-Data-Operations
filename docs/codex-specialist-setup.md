# Codex specialist-agent setup

ADOP's Codex workflow delegates build responsibilities to named specialist
agents. Until Codex supports automatic discovery of agents bundled inside a
plugin, install the specialist contracts into the customer project's
`.codex/agents/` directory.

From the customer project root:

```bash
mkdir -p .codex/agents
cp /path/to/agent-integrations/adapters/codex/.codex/agents/*.toml .codex/agents/
```

The installed contracts are:

- `metadata-agent`
- `quality-agent`
- `transformation-agent`
- `dag-agent`
- `ontology-agent`
- `iac-agent`
- `requirements-auditor`

The onboarding and DevOps workflow skills select these names with
`agent_type`. Do not replace a matching specialist with `default`; the
specialist name must appear in the run trace.

This setup installs behavior contracts only. Customer credentials, compliance
decisions, schedules, IAM principals, and deployment settings remain
customer-provided and must not be copied from the ADOP repository.

Validate the installation from the ADOP repository with:

```bash
python3 scripts/validate_integrations.py
python3 scripts/sync_platforms.py check
```
