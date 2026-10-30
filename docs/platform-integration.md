# Platform integration and clone-ready structure

The repository has two responsibilities:

1. Provide a working project surface immediately after cloning.
2. Package native integrations for Claude Code, Codex, Amazon Q Developer, and
   Kiro.

## Start after cloning

Launch the client from the repository root. The root files are the
clone-ready surface:

| Client | Entry point |
|---|---|
| Claude Code | `CLAUDE.md`, `.claude/`, `.mcp.json` |
| Codex | `AGENTS.md`, `.codex/`, `scripts/start_codex.py` |
| Amazon Q Developer | `AmazonQ.md`, `.amazonq/` |
| Kiro | `.kiro/` |

The default MCP profile exposes only `aws-mcp`. It is safe to clone and start
without enabling Snowflake, Databricks, Teradata, or the specialized local
servers.

## Repository layers

```text
shared/             Reusable Python code, policies, templates, tracing
contracts/          Versioned JSON schemas for workload specifications
runbooks/           Shared operating procedures for the agents
mcp-profiles/       Declarative MCP profiles and provider enablement
mcp-servers/        Custom MCP server implementations
tool-registry/      Canonical server and invariant registry
workloads/          Dataset-specific generated pipeline artifacts

.claude/            Claude Code project configuration
.codex/             Codex project configuration
.amazonq/           Amazon Q project configuration
.kiro/              Kiro project configuration

adapters/           Portable native snapshots for distribution/comparison
plugins/            Installable Claude Code and Codex plugin packages
docs/               Human-facing documentation
scripts/            Repository validation and workflow utilities
```

The native client folders remain at the root because the clients discover
their configuration there. They are not moved under `adapters/` or
`platforms/`.

## Plugin versus clone-ready project

The Claude plugin at `plugins/claude-code/` is an optional installable package.
It vendors the runtime and plugin metadata needed outside an ADOP checkout.
The root `.claude/` surface is what works when Claude Code is launched inside
the cloned repository.

The ADOP Codex plugin is available at `plugins/adop/`. Add the repository-local
marketplace and install it from Codex:

```bash
codex plugin marketplace add .
codex
```

Then open `/plugins` and install `adop`. The plugin provides setup, onboarding,
DevOps, and security-review skills. Its clone-ready project rules remain in
`.codex/` and `AGENTS.md`, which are still required for the repository's hooks
and enforcement behavior. Because the Codex CLI stores runtime configuration
under `CODEX_HOME`, use
`python3 scripts/start_codex.py` to load this checkout's AWS MCP profile without
overwriting the user's global Codex configuration. `adapters/codex/` is the
portable snapshot.

The adapter snapshots are checked for required files and MCP parity by:

```bash
python3 scripts/sync_platforms.py check
```

To synchronize clone-ready JSON MCP profiles from `.mcp.json`:

```bash
python3 scripts/sync_platforms.py sync --apply
```

This command does not enable optional MCP servers and does not deploy AWS
resources.

To verify the Codex MCP surface after cloning:

```bash
python3 scripts/start_codex.py --check
```

## Workload boundary

The platform integration check validates structure only. It does not generate
pipeline code or bypass the Phase 1 human discovery gate. A workload still
requires:

```text
workloads/{name}/run/requirements.jsonl
workloads/{name}/run/decisions.jsonl
workloads/{name}/logs/trace_events.jsonl
```

Use the live demo preflight separately when AWS access is required:

```bash
python3 scripts/mcp_demo.py check --profile demo
```
