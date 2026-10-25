# MCP Server Setup Guide for Codex

**How to configure MCP servers for this project**

---

## Quick Start (After Cloning)

The repository stores its canonical Codex MCP definition in `.codex/config.toml`.
The Codex CLI itself loads runtime configuration from `CODEX_HOME`, so use the
repository wrapper to start Codex with this checkout's profile. The default
profile enables only the AWS managed MCP server through the AWS Agent Toolkit.
Specific AWS and ADOP servers remain disabled and are available in
`.codex/config.optional.toml` for explicit opt-in.

```bash
# 1. Install uv (Python package runner)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Verify AWS credentials
aws sts get-caller-identity

# 3. Inspect this checkout's servers without changing global Codex config
python3 scripts/start_codex.py --check

# 4. Validate the integration bundle
python3 scripts/validate_integrations.py
```

For a live end-to-end Glue/S3/Athena demonstration in an existing AWS
account, use the dedicated demo profile:

```bash
python3 scripts/mcp_demo.py check --profile demo
python3 scripts/mcp_demo.py activate --profile demo --apply
```

The demo profile is reversible and enables only the servers required for the
demonstration. It creates a timestamped backup before changing client files.
Restart the active client after activation. See
[`mcp-profiles/demo/README.md`](../mcp-profiles/demo/README.md).

The committed `.mcp.json` is retained for compatible MCP hosts and registry
consistency checks. `.codex/config.toml` is the canonical Codex profile, and
`scripts/start_codex.py` translates it into supported Codex command-line
overrides without modifying `~/.codex/config.toml`.

---

## Prerequisites

- **Codex** CLI installed
- **uv** (v0.9+) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Python 3.12+** — required by AWS MCP server packages
- **AWS credentials** configured (`~/.aws/credentials` or environment variables)
- **AWS region** — defaults to `us-east-1` in `.codex/config.toml`

---

## What's Configured

`.codex/config.toml` defines the default AWS managed MCP connection. The
optional server catalog retains the specific AWS and ADOP servers for
capabilities not exposed by the default endpoint.

### Optional Server Catalog

| Server | Package | Purpose |
|--------|---------|---------|
| `glue-athena` | Custom FastMCP (`mcp-servers/glue-athena-server/`) | Glue Crawlers, Glue ETL, Athena, Data Catalog |
| `core` | `awslabs-aws-api-mcp-server` | S3 operations, KMS key management, Secrets Manager |
| `iam` | `awslabs-iam-mcp-server` | Role lookup, permission simulation, policy management |
| `lambda` | `awslabs-lambda-tool-mcp-server` | Lake Formation grants via Lambda, Spark execution |
| `s3-tables` | `awslabs-s3-tables-mcp-server` | S3 Tables (Iceberg) management |
| `cloudtrail` | `awslabs-cloudtrail-mcp-server` | Audit trail, security investigation, compliance |
| `redshift` | `awslabs-redshift-mcp-server` | Schema verification, Gold zone queries via Spectrum |
| `cloudwatch` | `awslabs-cloudwatch-mcp-server` | Logs, metrics, alarms |
| `cost-explorer` | `awslabs-billing-cost-management-mcp-server` | Cost tracking, budget analysis |
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

### Enable an Optional Server

Keep the default `aws-mcp` profile unchanged. Copy or merge only the optional
server required for the current task from `.codex/config.optional.toml`:

```json
[mcp_servers."cost-explorer"]
enabled = false
command = "uvx"
...
```

### Prepare the Live Demo

The default profile intentionally exposes only `aws-mcp`. The live demo
profile adds Glue/Athena, Lake Formation, IAM, S3/KMS, PII, CloudWatch, and
CloudTrail capabilities:

```bash
python3 scripts/mcp_demo.py check --profile demo
python3 scripts/mcp_demo.py activate --profile demo --apply
```

Use `--offline` to validate local configuration without calling AWS. Use
`restore` with the printed backup directory to return to the AWS-only profile.

---

## Testing

### Health Check

```bash
python3 scripts/start_codex.py --check
```

Expected: `aws-mcp` is listed and enabled. A direct `codex mcp list` only
reports globally registered servers and does not prove that this checkout's
profile was loaded.

### Test Individual Server

```bash
# AWS servers (via uvx)
uvx --from awslabs-iam-mcp-server awslabs.iam-mcp-server --help
uvx --from awslabs-aws-api-mcp-server awslabs.aws-api-mcp-server --help

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
  ├── AWS managed MCP (uvx proxy)
  └── optional AWS/ADOP servers (uvx / uv run)
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

**Setup**: AWS managed MCP is already enabled in `.codex/config.toml`. Enable
optional servers intentionally for the account and capability you need.

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
python3 scripts/start_codex.py --check
# Restart Codex

# Revert to Local mode
# Restore the local stdio server entries in .codex/config.toml
python3 scripts/start_codex.py --check
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
| `.codex/config.toml` | Codex MCP server configuration; AWS MCP enabled by default |
| `.mcp.json` | Portable MCP configuration for compatible non-Codex hosts |
| `runbooks/environment-setup-agent/agentcore/` | Gateway config, IAM policies, Runtime agent definition |
| `MCP_GUARDRAILS.md` | Tool selection rules per pipeline phase |
| `TOOL_ROUTING.md` | Intent-based tool routing guide |
| `mcp-servers/` | 4 custom MCP servers (FastMCP, dual stdio/SSE transport) |
| `tool-registry/servers.yaml` | Canonical server list — names, tools, criticality |

---

**Last Updated**: March 24, 2026
