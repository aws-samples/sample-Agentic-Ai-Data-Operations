# Optional third-party MCP profiles

These provider connections are intentionally disabled and are not loaded by the
default or live-demo profiles.

Available optional providers:

- `snowflake-native` — remote Snowflake MCP endpoint
- `databricks-native` — remote Databricks MCP service
- `teradata` — Teradata MCP server launched with `uvx`

Canonical disabled profiles live beside this README:

- [`snowflake.json`](snowflake.json)
- [`databricks.json`](databricks.json)
- [`teradata.json`](teradata.json)

The client-specific optional files are synchronized projections of these
canonical profiles. They are not loaded unless explicitly selected.

The definitions are mirrored in the optional client configurations:

- `.mcp.optional.json`
- `.amazonq/mcp.optional.json`
- `.kiro/settings/mcp.optional.json`
- `.codex/config.optional.toml`
- the corresponding `plugins/` and `adapters/` copies

Before enabling one, set the provider-specific environment variables:

```bash
export SNOWFLAKE_MCP_URL="https://<account>/api/v2/databases/<db>/schemas/<schema>/mcp-servers/<name>"
export SNOWFLAKE_MCP_TOKEN="<short-lived-token>"

export DATABRICKS_MCP_URL="https://<workspace>/ai-gateway/mcp-services/<catalog>.<schema>.<service>"
export DATABRICKS_MCP_TOKEN="<short-lived-token>"

export TERADATA_DATABASE_URI="teradatasql://<user>:<password>@<host>/<database>"
```

Do not commit these values. Enable only the provider required for the current
workload, use a least-privilege identity, and run the provider's `tools/list`
and read-only connectivity checks before allowing mutation tools.
