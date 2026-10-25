# Live Demo MCP Profile

The `demo` profile enables the smallest complete MCP set for a live
Bronze → Silver → Gold demonstration in the existing AWS account:

- `aws-mcp` for AWS discovery and service operations
- `glue-athena` for Glue Catalog, crawlers, jobs, and Athena
- `lakeformation` for LF-Tags and TBAC
- `iam` for role discovery and permission simulation
- `pii-detection` for PII discovery and column controls
- `cloudtrail` for audit evidence

The managed `aws-mcp` surface handles S3, KMS, CloudWatch, and other AWS
service operations, avoiding legacy package-specific startup dependencies.

The normal profiles remain AWS-only and are not changed by this profile.

## Prepare the demo

From the integration bundle root:

```bash
python3 scripts/mcp_demo.py check --profile demo
python3 scripts/mcp_demo.py activate --profile demo --apply
```

Run the activation command before starting Claude Code, Codex, Amazon Q, or
Kiro. Local stdio MCP clients load their server list at session start, so a
client restart is required after activation.

Use `--aws-profile` and `--region` when the existing account is not the
default AWS profile or `us-east-1`:

```bash
python3 scripts/mcp_demo.py check --profile demo \
  --aws-profile my-account --region us-west-2
python3 scripts/mcp_demo.py activate --profile demo --apply \
  --aws-profile my-account --region us-west-2
```

The command creates a timestamped backup before changing any client profile.
Restore the previous profiles with:

```bash
python3 scripts/mcp_demo.py restore --backup .mcp-backups/demo/<timestamp>
```

All AWS mutations remain subject to IAM, the ADOP human approval gate, and
the repository's deployment guardrails.
