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

That's it. All 13 MCP servers are pre-configured and will auto-install their dependencies via `uvx` on first use.

---

## Prerequisites

- **Claude Code** CLI installed
- **uv** (v0.9+) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Python 3.12+** — required by AWS MCP server packages
- **AWS credentials** configured (`~/.aws/credentials` or environment variables)
- **AWS region** — defaults to `us-east-1` (change in `.mcp.json` if needed)

---

## What's Configured

The `.mcp.json` in the repo root configures 13 MCP servers. Claude Code reads this automatically.

### Connected Servers (13)

| Server | Package | Purpose |
|--------|---------|---------|
| `glue-athena` | Custom FastMCP (`mcp-servers/glue-athena-server/`) | Glue Crawlers, Glue ETL, Athena, Data Catalog |
| `core` | `awslabs-core-mcp-server` | S3 operations, KMS key management, Secrets Manager |
| `iam` | `awslabs-iam-mcp-server` | Role lookup, permission simulation, policy management |
| `lambda` | `awslabs-lambda-mcp-server` | Lake Formation grants via Lambda, Spark execution |
| `s3-tables` | `awslabs-s3-tables-mcp-server` | S3 Tables (Iceberg) management |
| `cloudtrail` | `awslabs-cloudtrail-mcp-server` | Audit trail, security investigation, compliance |
| `redshift` | `awslabs-redshift-mcp-server` | Schema verification, Gold zone queries via Spectrum |
| `cloudwatch` | `awslabs-cloudwatch-mcp-server` | Logs, metrics, alarms |
| `cost-explorer` | `awslabs-cost-explorer-mcp-server` | Cost tracking, budget analysis |
| `dynamodb` | `awslabs-dynamodb-mcp-server` | DynamoDB operations (operational state, API cache) |
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

## Deployment Modes

This project supports two MCP deployment architectures:

### Mode 1: Local (Default)

**Architecture**: MCP servers run locally on your laptop via stdio transport.

```
Claude Code (.mcp.json)
  ↓ stdio (local processes)
  ├── 13 MCP servers (uvx / uv run)
       ↓ AWS SDK calls
       ↓
  AWS Services (Glue, Athena, S3, etc.)
```

**Pros**:
- ✅ Zero cloud setup needed
- ✅ Fast development iteration
- ✅ No AWS costs for MCP layer

**Cons**:
- ❌ Each developer needs local Python/uv setup
- ❌ Version drift between machines
- ❌ Not suitable for production pipelines

**Setup**: Already done! The `.mcp.json` in this repo is pre-configured.

---

### Mode 2: Gateway (Production)

**Architecture**: MCP servers run on AWS Lambda, unified via Amazon Bedrock AgentCore Gateway.

```
Claude Code (.mcp.gateway.json)
  ↓ MCP over HTTPS + AWS SigV4
  ↓
Amazon Bedrock AgentCore Gateway (unified endpoint)
  ↓ Routes to Lambda targets
  ├── Lambda: glue-athena (3 tools)
  ├── Lambda: lakeformation (5 tools)
  ├── Lambda: sagemaker-catalog (4 tools)
  └── Lambda: pii-detection (2 tools)
       ↓ AWS SDK calls
       ↓
  AWS Services (Glue, Athena, S3, etc.)
```

**Pros**:
- ✅ Zero local setup per developer
- ✅ Consistent versions across team
- ✅ Production-ready (AWS managed service)
- ✅ Built-in IAM authentication
- ✅ Unified observability

**Cons**:
- ❌ Requires AWS setup (~15 min)
- ❌ Small Lambda costs (~$0/month for dev)

**Setup**: See **Admin Guide** below.

---

## Gateway Deployment (Admin Guide)

**For production deployments**, use Amazon Bedrock AgentCore Gateway to host MCP servers in AWS.

### Quick Start

```bash
# See complete step-by-step guide
cat prompts/environment-setup-agent/02-deploy-agentcore-gateway.md

# Or follow the prompt-based deployment
# See: prompts/environment-setup-agent/02-deploy-agentcore-gateway.md
```

### What Gets Deployed

| Component | Count | Purpose |
|-----------|-------|---------|
| **Gateway** | 1 | Unified MCP endpoint with AWS SigV4 auth |
| **Lambda Targets** | 4+ | glue-athena, lakeformation, sagemaker-catalog, pii-detection |
| **IAM Role** | 1 | Gateway execution role (Lambda invoke permissions) |
| **Tool Schemas** | 4+ | JSON schemas describing each tool's interface |

### Deployment Steps (Summary)

1. **Create Gateway IAM Role** (trust policy: `bedrock-agentcore.amazonaws.com`)
2. **Create Gateway Resource** (MCP version `2025-11-25`, IAM auth)
3. **Create Tool Schemas** (JSON format, no `"default"` fields)
4. **Register Lambda Targets** (with credential provider config)
5. **Generate `.mcp.gateway.json`** (single unified endpoint)
6. **Test** (`python3 prompts/environment-setup-agent/agentcore/gateway/test_gateway.py`)

**Time**: ~15 minutes for 4 Lambda targets

**Full Guide**: See `prompts/environment-setup-agent/02-deploy-agentcore-gateway.md` for complete commands and troubleshooting.

---

### Switch Between Local and Gateway

```bash
# Activate Gateway mode
cp .mcp.gateway.json .mcp.json
# Restart Claude Code

# Revert to Local mode
cp .mcp.local.json .mcp.json
# or: git checkout .mcp.json
# Restart Claude Code
```

---

## Runtime Deployment (Optional)

Deploy the **Data Onboarding Agent** to Agentcore Runtime for fully cloud-hosted operation.

**Requires**: Gateway already deployed (see above)

**Setup**: See `prompts/environment-setup-agent/03-deploy-agentcore-runtime.md`

**Benefits**:
- API-driven agent invocation (no local Claude Code needed)
- Scheduled pipelines (cron, Airflow triggers)
- Multi-tenant (multiple agents share Gateway tools)

---

---

## Documentation

| File | Purpose |
|------|---------|
| `.mcp.json` | MCP server configuration (committed, portable) |
| `.mcp.gateway.json` | Gateway MCP configuration (generated by prompt 09) |
| `prompts/environment-setup-agent/agentcore/` | Gateway config, IAM policies, Runtime agent definition |
| `MCP_GUARDRAILS.md` | Tool selection rules per pipeline phase |
| `TOOL_ROUTING.md` | Intent-based tool routing guide |
| `mcp-servers/` | 4 custom MCP servers (FastMCP, dual stdio/SSE transport) |
| `docs/mcp-servers.md` | Server architecture overview |
| `docs/mcp-integration.md` | MCP integration with pipeline phases |

---

**Last Updated**: March 24, 2026
