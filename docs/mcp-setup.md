# MCP Server Setup Guide for Codex

**How to configure MCP servers for this project**

---

## Quick Start (After Cloning)

Codex reads the project MCP definitions from `.codex/config.toml`. The repository keeps every
server disabled by default because these commands can call AWS with the configured profile.
Enable only the servers required for the current non-production task.

```bash
# 1. Install uv (Python package runner)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Verify AWS credentials
aws sts get-caller-identity

# 3. Inspect the servers Codex can see
codex mcp list

# 4. Validate the repository registry
python3 scripts/validate_tool_registry.py
```

The committed `.mcp.json` is retained for compatible MCP hosts and for registry consistency
checks. It is not the source of truth for Codex project configuration.

---

## Prerequisites

- **Codex** CLI installed
- **uv** (v0.9+) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Python 3.12+** — required by AWS MCP server packages
- **AWS credentials** configured (`~/.aws/credentials` or environment variables)
- **AWS region** — defaults to `us-east-1` in `.codex/config.toml`

---

## What's Configured

`.codex/config.toml` defines 13 MCP servers. Each entry currently has `enabled = false`.

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

Edit `.codex/config.toml` and replace `us-east-1` with your region:

```bash
# macOS
sed -i '' 's/us-east-1/your-region/g' .codex/config.toml

# Linux
sed -i 's/us-east-1/your-region/g' .codex/config.toml
```

### Change AWS Profile

If you use a named profile instead of `default`:

```bash
sed -i '' 's/"default"/"your-profile-name"/g' .codex/config.toml
```

### Disable a Server

Keep `enabled = false` for any server you don't need:

```json
[mcp_servers."cost-explorer"]
enabled = false
command = "uvx"
...
```

---

## Testing

### Health Check

```bash
codex mcp list
```

Expected: the configured server entries are listed. A server is not usable until its
`enabled` flag is set to `true`, its dependencies resolve, and AWS credentials are valid.

### Test Individual Server

```bash
# AWS servers (via uvx)
uvx --from awslabs-iam-mcp-server awslabs.iam-mcp-server --help
uvx --from awslabs-core-mcp-server awslabs.core-mcp-server --help

# PII detection (custom server)
uv run --no-project --with boto3 --with mcp --python 3.13 \
  mcp-servers/pii-detection-server/server.py
```

### Test in Codex

After starting Codex in this project:

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

This custom server needs `boto3` and `mcp` packages. The `pii-detection` entry in
`.codex/config.toml` uses `uv run --with boto3 --with mcp` to install them on demand. If it
still fails:

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
Codex (.codex/config.toml)
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

**Setup**: The server definitions are already present in `.codex/config.toml`; enable them
intentionally for the account you want to use.

---

### Mode 2: Gateway (Production)

**Architecture**: MCP servers run on AWS Lambda, unified via Amazon Bedrock AgentCore Gateway.

```
Codex (.mcp.gateway.json)
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
cat runbooks/environment-setup-agent/02-deploy-agentcore-gateway.md

# Or follow the prompt-based deployment
# See: runbooks/environment-setup-agent/02-deploy-agentcore-gateway.md
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
6. **Test** (`python3 runbooks/environment-setup-agent/agentcore/gateway/test_gateway.py`)

**Time**: ~15 minutes for 4 Lambda targets

**Full Guide**: See `runbooks/environment-setup-agent/02-deploy-agentcore-gateway.md` for complete commands and troubleshooting.

---

### Switch Between Local and Gateway

```bash
# Activate Gateway mode
# Apply the generated Gateway connection settings to .codex/config.toml
codex mcp list
# Restart Codex

# Revert to Local mode
# Restore the local stdio server entries in .codex/config.toml
codex mcp list
# Restart Codex
```

---

## Runtime Deployment (Optional)

Deploy the **Data Onboarding Agent** to Agentcore Runtime for fully cloud-hosted operation.

**Requires**: Gateway already deployed (see above)

**Setup**: See `runbooks/environment-setup-agent/03-deploy-agentcore-runtime.md`

**Benefits**:
- API-driven agent invocation (no local Codex needed)
- Scheduled pipelines (cron, Airflow triggers)
- Multi-tenant (multiple agents share Gateway tools)

---

---

## Documentation

| File | Purpose |
|------|---------|
| `.codex/config.toml` | Codex MCP server configuration; disabled by default |
| `.mcp.json` | Portable MCP configuration for compatible non-Codex hosts |
| `runbooks/environment-setup-agent/agentcore/` | Gateway config, IAM policies, Runtime agent definition |
| `MCP_GUARDRAILS.md` | Tool selection rules per pipeline phase |
| `TOOL_ROUTING.md` | Intent-based tool routing guide |
| `mcp-servers/` | 4 custom MCP servers (FastMCP, dual stdio/SSE transport) |
| `tool-registry/servers.yaml` | Canonical server list — names, tools, criticality |

---

**Last Updated**: March 24, 2026
