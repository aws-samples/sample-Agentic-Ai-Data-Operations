# standards.md — your organization's architecture constraints (the "blueprint").
# The model fills these in; it does not redraw them. Replace the examples with your real standards.

## Storage & format
- Lakehouse zones: Bronze (raw, immutable) → Silver (cleansed) → Gold (curated).
- Table format: Apache Iceberg on S3. Partition Gold by the natural query grain.

## Compute
- ETL: AWS Glue (PySpark). Streaming: Glue Streaming ETL.
- Prefer Athena for ad-hoc queries; Redshift only for heavy repeated aggregations.

## Security
- Zone-scoped KMS CMKs (separate for Bronze/Silver/Gold).
- No credentials in code — Secrets Manager / Airflow Connections only.
- Least-privilege IAM; `simulate_principal_policy` before source access.

## Orchestration
- Airflow by default; Step Functions when the org standard calls for it.
- retries=3, exponential backoff, alert on failure.

## Sub-agent limits
- Sub-agents NEVER call MCP/AWS/CLI. They generate files only.
- Only the orchestrator touches infrastructure, and only with human approval.

## Tooling philosophy
- MCP-first; CLI only on fallback (and log it).
- Cost sensitivity: <set your monthly DPU / token thresholds here>.
