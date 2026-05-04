# Agentcore: Cloud-Hosted MCP Servers + Agent Runtime

Deploy all 13 MCP servers to **Agentcore Gateway** and the Data Onboarding Agent to **Agentcore Runtime**. No local Python, uv, or stdio servers needed -- everything runs in the cloud.

## Architecture

```
                    Agentcore Gateway (always deployed)
                    ┌─────────────────────────────────┐
                    │  13 MCP servers (cloud-hosted)   │
                    │  ├── glue-athena (:8001)         │
                    │  ├── lakeformation (:8002)       │
                    │  ├── sagemaker-catalog (:8003)   │
                    │  ├── pii-detection (:8004)       │
                    │  ├── iam                         │
                    │  ├── lambda                      │
                    │  ├── core                        │
                    │  ├── s3-tables                   │
                    │  ├── cloudtrail                  │
                    │  ├── redshift                    │
                    │  ├── cloudwatch                  │
                    │  ├── cost-explorer               │
                    │  └── dynamodb                    │
                    └────────────┬────────────────────┘
                                 │
               ┌─────────────────┼─────────────────┐
               │                                     │
  LOCAL DEMO MODE                      PRODUCTION MODE
  ───────────────────                  ───────────────────
  Claude Code (laptop)                 Agentcore Runtime
  ├── .mcp.gateway.json                ├── agent.yaml
  ├── reads SKILLS.md                  ├── CLAUDE.md + SKILLS.md
  ├── spawns sub-agents                │   loaded as instructions
  │   via Agent tool                   ├── sub-agents internal
  └── human-in-the-loop               └── API-accessible
                                           (no human needed)
```

MCP servers always run on Gateway. The agent runs locally (demo) or on Runtime (production).

## Execution Modes

Gateway is deployed **once** and used by **both** modes. The only difference is where the agent runs.

### Local Demo Mode

The agent runs in Claude Code on your laptop. MCP tools come from Gateway via SSE.

| Aspect | Details |
|--------|---------|
| **Agent** | Claude Code CLI on your laptop |
| **Tools** | All 13 MCP servers on Gateway (SSE transport) |
| **Sub-agents** | Spawned via Claude Code `Agent` tool (local) |
| **Human-in-the-loop** | Yes -- Claude asks questions, presents plans, gets approval |
| **Use case** | Demos, development, testing, single-user workflows |

**How to set up:**
1. Deploy Gateway: run `prompts/09-deploy-agentcore-gateway.md`
2. Replace `.mcp.json` with the generated `.mcp.gateway.json`
3. Run Claude Code normally -- use `prompts/03-onboard-build-pipeline.md` to onboard data

**How to revert to fully local (no Gateway):**
```bash
git checkout .mcp.json
```

### Production Mode

The agent runs on Agentcore Runtime in the cloud. MCP tools come from the same Gateway.

| Aspect | Details |
|--------|---------|
| **Agent** | Agentcore Runtime (cloud, API-accessible) |
| **Tools** | All 13 MCP servers on Gateway (same Gateway as demo mode) |
| **Sub-agents** | Managed internally by Runtime |
| **Human-in-the-loop** | Optional -- can be fully autonomous or pause for approval via API |
| **Use case** | Production pipelines, multi-user, API integrations, scheduled onboarding |

**How to set up:**
1. Deploy Gateway: run `prompts/09-deploy-agentcore-gateway.md` (if not already deployed)
2. Deploy Runtime: run `prompts/10-deploy-agentcore-runtime.md`
3. Invoke agent via API:
```bash
aws bedrock-agent-runtime invoke-agent \
  --agent-id {AGENT_ID} \
  --session-id my-session \
  --input-text "Onboard customer data from s3://bucket/customers.csv"
```

## Gateway vs Runtime

| Component | What It Does | When to Use |
|-----------|-------------|-------------|
| **Gateway** | Hosts all 13 MCP servers in the cloud | Always -- required for both demo and production modes |
| **Runtime** | Hosts the Data Onboarding Agent as a cloud API | Production mode only -- when the agent needs to be API-accessible |

Runtime requires Gateway (agent needs tools). Gateway can be used standalone with local Claude Code (demo mode).

## Directory Structure

```
agentcore/
├── gateway/
│   ├── config.yaml                       # All 13 server definitions
│   └── iam/
│       ├── glue-athena-policy.json       # Glue + Athena
│       ├── lakeformation-policy.json     # LF-Tags + TBAC
│       ├── sagemaker-catalog-policy.json # Glue table metadata
│       ├── pii-detection-policy.json     # PII scan + LF-Tags
│       ├── iam-policy.json              # IAM role/policy management
│       ├── lambda-policy.json           # Lambda invocation
│       ├── core-policy.json             # S3, KMS, Secrets Manager
│       ├── s3-tables-policy.json        # S3 Tables / Iceberg
│       ├── cloudtrail-policy.json       # Audit trail
│       ├── redshift-policy.json         # Redshift Data API
│       ├── cloudwatch-policy.json       # Logs, metrics, alarms
│       ├── cost-explorer-policy.json    # Cost tracking
│       └── dynamodb-policy.json         # DynamoDB operational state
├── runtime/
│   └── agent.yaml                       # Agent definition (all tools from Gateway)
└── README.md
```

## Prerequisites

1. Base infrastructure from `prompts/00-setup-environment.md` (IAM roles, S3, KMS, Glue DBs, LF-Tags)
2. AWS credentials with Bedrock Agentcore permissions
3. Custom MCP servers in `mcp-servers/` (already in repo)

## Deployment

### Step 1: Deploy Gateway (required for both modes)

Run `prompts/09-deploy-agentcore-gateway.md` -- Claude will:
1. Create Gateway IAM execution role
2. Attach 13 per-server policies from `agentcore/gateway/iam/`
3. Register Gateway with Bedrock Agentcore
4. Deploy all 13 servers (4 custom FastMCP + 9 PyPI)
5. Verify all endpoints respond
6. Generate `.mcp.gateway.json` for connecting

After this step, you can use **Local Demo Mode** immediately (replace `.mcp.json` with `.mcp.gateway.json`).

### Step 2: Deploy Runtime (production mode only)

Run `prompts/10-deploy-agentcore-runtime.md` -- Claude will:
1. Verify Gateway is healthy (all 13 servers)
2. Create Runtime IAM execution role
3. Register agent from `agentcore/runtime/agent.yaml`
4. Connect all 13 Gateway tools to the agent
5. Test agent invocation
6. Return agent endpoint URL

Skip this step if you only need demo mode.

## IAM Policies

Every server gets a least-privilege IAM policy scoped to exactly the AWS actions it needs:

| Server | Key Actions | Scope |
|--------|-------------|-------|
| glue-athena | Glue CRUD, Athena queries | Catalog resources, workgroups |
| lakeformation | LF-Tag CRUD, grant/revoke | Lake Formation resources |
| sagemaker-catalog | Glue GetTable, UpdateTable | Table resources |
| pii-detection | Glue read, LF-Tags, Athena | Catalog + LF resources |
| iam | Role/policy CRUD, simulation | IAM resources |
| lambda | InvokeFunction | Lambda functions |
| core | S3 CRUD, KMS, Secrets Manager | S3 buckets, KMS keys |
| s3-tables | S3 Tables / Iceberg ops | S3 Tables resources |
| cloudtrail | LookupEvents, Lake queries | CloudTrail resources |
| redshift | Data API, DescribeClusters | Redshift resources |
| cloudwatch | Metrics, logs, alarms | CloudWatch resources |
| cost-explorer | GetCostAndUsage | Cost Explorer |
| dynamodb | Table CRUD, query, scan | DynamoDB tables |

## Transport Modes

Custom servers (4) support dual transport via `MCP_TRANSPORT` environment variable:

```bash
# Local mode (default) -- stdio transport
python3 mcp-servers/glue-athena-server/server.py

# Cloud mode -- SSE transport on specified port
MCP_TRANSPORT=sse MCP_PORT=8001 python3 mcp-servers/glue-athena-server/server.py
```

PyPI servers (9) are deployed to Gateway as managed packages -- Agentcore handles their transport.

## Connecting to Gateway (Local Demo Mode)

After Gateway deployment, the prompt generates `.mcp.gateway.json` with all 13 server endpoints:

```json
{
  "mcpServers": {
    "glue-athena": {
      "url": "https://{gateway-endpoint}/glue-athena/sse"
    },
    "iam": {
      "url": "https://{gateway-endpoint}/iam/sse"
    }
  }
}
```

To switch from local to Gateway: replace `.mcp.json` with `.mcp.gateway.json`.
To switch back to fully local: restore the original `.mcp.json` (committed in git).

In production mode, the Runtime agent connects to Gateway automatically -- no `.mcp.gateway.json` needed.
