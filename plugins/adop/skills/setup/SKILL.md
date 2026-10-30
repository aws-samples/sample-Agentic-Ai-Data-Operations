---
name: setup
description: Verify that the current repository is an ADOP checkout and explain the required Codex setup.
---

# ADOP Codex plugin setup

Use this skill after installing the ADOP plugin.

1. Confirm the current repository contains `AGENTS.md`, `.codex/skills/`,
   `shared/policies/`, `shared/orchestration/`, and `workloads/`.
2. If any required surface is missing, stop and explain that the plugin is
   designed for an ADOP repository. Do not generate pipeline artifacts in an
   unrelated repository.
3. Read `AGENTS.md` and treat it as authoritative.
4. Run these read-only checks from the repository root:

   ```bash
   python3 scripts/validate_integrations.py
   python3 scripts/sync_platforms.py check
   python3 scripts/start_codex.py --check
   ```

5. Explain that the plugin provides workflow entry points, while the checkout's
   `.codex/` hooks, `AGENTS.md`, shared Cedar engine, and shared policies remain
   the enforcement source.
6. Never ask the user to place credentials in the plugin. For production,
   follow the repository's AgentCore Runtime and authenticated AgentCore
   Gateway deployment boundary.
