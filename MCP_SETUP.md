# MCP Server Setup Guide

**How to configure MCP servers for this project**

---

## Quick Start (After Cloning)

The `.mcp.json` is included in the repo and works out of the box. Just ensure prerequisites are met:

```bash
# 1. Install uv (Python package runner)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Verify AWS credentials
aws sts get-caller-identity

# 3. Verify MCP servers connect
claude mcp list
```

That's it. All 11 MCP servers are pre-configured and will auto-install their dependencies via `uvx` on first use.

---

## Prerequisites

- **Claude Code** CLI installed
- **uv** (v0.9+) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Python 3.12+** — required by AWS MCP server packages
- **AWS credentials** configured (`~/.aws/credentials` or environment variables)
- **AWS region** — defaults to `us-east-1` (change in `.mcp.json` if needed)

---

## What's Configured

The `.mcp.json` in the repo root configures 11 MCP servers. Claude Code reads this automatically.

### Connected Servers (11)

| Server | Package | Purpose |
|--------|---------|---------|
| `aws.dp-mcp` | `awslabs.aws-dataprocessing-mcp-server` | Glue Crawlers, Glue ETL, Athena, Data Catalog |
| `core` | `awslabs-core-mcp-server` | S3 operations, KMS key management, Secrets Manager |
| `iam` | `awslabs-iam-mcp-server` | Role lookup, permission simulation, policy management |
| `lambda` | `awslabs-lambda-mcp-server` | Lake Formation grants via Lambda, Spark execution |
| `s3-tables` | `awslabs-s3-tables-mcp-server` | S3 Tables (Iceberg) management |
| `cloudtrail` | `awslabs-cloudtrail-mcp-server` | Audit trail, security investigation, compliance |
| `redshift` | `awslabs-redshift-mcp-server` | Schema verification, Gold zone queries via Spectrum |
| `cloudwatch` | `awslabs-cloudwatch-mcp-server` | Logs, metrics, alarms |
| `cost-explorer` | `awslabs-cost-explorer-mcp-server` | Cost tracking, budget analysis |
| `dynamodb` | `awslabs-dynamodb-mcp-server` | DynamoDB / SynoDB operations |
| `pii-detection` | Custom (local server) | PII detection + Lake Formation LF-Tag application |

### Not Available (dependency conflicts on PyPI)

| Server | Workaround |
|--------|-----------|
| `lakeformation` | Use `lambda` MCP (`LF_access_grant_new`) or `aws lakeformation` CLI |
| `sns-sqs` | `aws sns` / `aws sqs` CLI |
| `eventbridge` | `aws events` CLI |
| `stepfunctions` | `aws stepfunctions` CLI |

### Not Available (no PyPI package)

| Server | Workaround |
|--------|-----------|
| `sagemaker-catalog` | `aws glue` CLI with custom metadata properties |

---

## Customizing for Your Account

### Change AWS Region

Edit `.mcp.json` and replace `us-east-1` with your region:

```bash
# macOS
sed -i '' 's/us-east-1/your-region/g' .mcp.json

# Linux
sed -i 's/us-east-1/your-region/g' .mcp.json
```

### Change AWS Profile

If you use a named profile instead of `default`:

```bash
sed -i '' 's/"default"/"your-profile-name"/g' .mcp.json
```

### Disable a Server

Add `"disabled": true` to any server entry you don't need:

```json
"cost-explorer": {
  "disabled": true,
  "command": "uvx",
  ...
}
```

---

## Testing

### Health Check

```bash
claude mcp list
```

Expected: most servers show `Connected`. Some servers (`core`, `pii-detection`) have slow startup and may show `Failed to connect` on the health check but work fine during actual conversation.

### Test Individual Server

```bash
# AWS servers (via uvx)
uvx --from awslabs-iam-mcp-server awslabs.iam-mcp-server --help
uvx --from awslabs-core-mcp-server awslabs.core-mcp-server --help

# PII detection (custom server)
uv run --no-project --with boto3 --with mcp --python 3.13 \
  mcp-servers/pii-detection-server/server.py
```

### Test in Claude Code

After starting Claude Code in this project:

```
"List IAM roles in my AWS account"
"What Glue databases exist?"
"Look up recent CloudTrail events"
```

---

## Troubleshooting

### Server shows "Failed to connect"

1. **Check uv is installed**: `uv --version` (need 0.9+)
2. **Check Python 3.12+**: `python3.12 --version` or `python3.13 --version`
3. **Check AWS credentials**: `aws sts get-caller-identity`
4. **Try manual start**: `uvx --from awslabs-iam-mcp-server awslabs.iam-mcp-server --help`
5. **Slow startup**: `core` and `pii-detection` take 5-10s to start. The health check may timeout but they work in conversation.

### AWS permissions error

Minimum IAM permissions for MCP servers:

```json
{
  "Effect": "Allow",
  "Action": [
    "glue:GetTable", "glue:GetTables", "glue:GetDatabase", "glue:GetDatabases",
    "glue:CreateCrawler", "glue:StartCrawler", "glue:CreateJob", "glue:StartJobRun",
    "athena:StartQueryExecution", "athena:GetQueryResults",
    "s3:GetObject", "s3:PutObject", "s3:ListBucket",
    "kms:CreateKey", "kms:CreateAlias", "kms:DescribeKey",
    "lakeformation:CreateLFTag", "lakeformation:AddLFTagsToResource", "lakeformation:GrantPermissions",
    "iam:ListRoles", "iam:SimulatePrincipalPolicy",
    "redshift:DescribeClusters", "redshift-data:ExecuteStatement",
    "cloudtrail:LookupEvents",
    "cloudwatch:GetMetricData", "cloudwatch:DescribeAlarms",
    "dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query",
    "ce:GetCostAndUsage"
  ],
  "Resource": "*"
}
```

### `pii-detection` server fails

This custom server needs `boto3` and `mcp` packages. The `.mcp.json` uses `uv run --with boto3 --with mcp` to auto-install them. If it still fails:

```bash
# Test directly
uv run --no-project --with boto3 --with mcp --python 3.13 \
  mcp-servers/pii-detection-server/server.py
```

Common issues:
- Python 3.13 not installed → install via `brew install python@3.13`
- `pyproject.toml` interference → the `--no-project` flag should handle this

---

## Documentation

| File | Purpose |
|------|---------|
| `.mcp.json` | MCP server configuration (committed, portable) |
| `MCP_GUARDRAILS.md` | Tool selection rules per pipeline phase |
| `TOOL_ROUTING.md` | Intent-based tool routing guide |
| `mcp-servers/pii-detection-server/` | Custom PII detection MCP server |
| `docs/mcp-servers.md` | Server architecture overview |
| `docs/mcp-integration.md` | MCP integration with pipeline phases |

---

**Last Updated**: March 23, 2026
