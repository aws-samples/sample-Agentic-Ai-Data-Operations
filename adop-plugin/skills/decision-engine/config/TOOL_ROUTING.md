# TOOL_ROUTING.md — intent-to-tool mapping for the Decision Engine.
# Match a natural-language operation to a tool. `not_when` is a negative filter: if true, skip.
# Edit to encode your org's real preferences.

## check data quality in Silver/Gold
- tool: glue-data-quality
- intent: ["run quality rules", "check completeness", "validate Silver data", "quality gate"]
- use: `aws glue start-data-quality-ruleset-evaluation-run` (DQDL)
- not_when: "Quick one-off check — Athena SQL is faster"
- mcp_server: glue-athena (REQUIRED)

## query / profile a table
- tool: athena
- intent: ["profile data", "sample rows", "ad-hoc query", "verify table queryable"]
- use: Athena SQL over the Glue catalog
- not_when: "Large repeated aggregations better suited to Redshift"
- mcp_server: glue-athena (REQUIRED)

## check permissions before source access
- tool: iam-simulate
- intent: ["can this role read the source", "verify access", "least privilege check"]
- use: `simulate_principal_policy` must return allowed before source access
- mcp_server: iam (REQUIRED)

## apply data governance tags
- tool: lakeformation
- intent: ["apply LF-Tags", "grant column access", "governance tag"]
- mcp_server: lakeformation (REQUIRED)

## detect PII
- tool: pii-detection
- intent: ["find PII", "classify sensitive columns", "PHI/PAN scan"]
- not_when: "Columns already classified in semantic.yaml"
- mcp_server: pii-detection (WARN → local heuristics fallback)
