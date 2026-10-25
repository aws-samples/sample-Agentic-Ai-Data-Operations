# MCP server profiles

The active default profile is the AWS managed MCP server exposed through the
AWS Agent Toolkit. It is configured in the client-native files:

- `.mcp.json`
- `.codex/config.toml`
- `.amazonq/mcp.json`
- `.kiro/settings/mcp.json`

The Python servers in this directory are ADOP-specific or capability-specific
optional servers. They are not enabled by default. Use the matching optional
profile when the AWS managed MCP endpoint does not expose a required operation:

```text
.mcp.optional.json
.codex/config.optional.toml
.amazonq/mcp.optional.json
.kiro/settings/mcp.optional.json
```

Do not put credentials in these files. The active AWS MCP profile uses the
normal AWS credential chain. Optional provider-native Snowflake and Databricks
MCP endpoints belong in the selected client's environment-specific MCP
configuration and should be enabled only for the workload that needs them.

Before enabling an optional server:

1. Confirm the AWS or provider capability is missing from the default profile.
2. Enable the smallest server/tool set required.
3. Run the Phase 0 health and identity checks.
4. Record the selected server, effective principal, and reason in run evidence.
5. Disable it again when the workload no longer requires it.
