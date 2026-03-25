# Amazon Bedrock AgentCore Gateway Architecture

**Deployed**: 2026-03-24

## Overview

This document describes the AgentCore Gateway deployment architecture for hosting MCP servers in AWS.

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│  CLIENT LAYER                                                       │
│                                                                     │
│  Claude Code (.mcp.gateway.json)                                   │
│    - Single MCP server entry: "agentcore-gateway"                  │
│    - Transport: SSE (Server-Sent Events over HTTPS)                │
│    - Auth: AWS SigV4 (uses AWS credentials)                        │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
                               │ HTTPS + AWS SigV4
                               │
┌──────────────────────────────▼─────────────────────────────────────┐
│  GATEWAY LAYER (AWS Managed)                                       │
│                                                                     │
│  Amazon Bedrock AgentCore Gateway                                  │
│  ID: data-onboarding-mcp-gateway-zqqrahrcm2                        │
│  URL: https://...gateway.bedrock-agentcore.us-east-1.amazonaws.com │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Translation Layer                                            │ │
│  │  - Receives MCP requests from Claude Code                    │ │
│  │  - Translates to Lambda event format                         │ │
│  │  - Routes to correct Lambda based on tool name               │ │
│  │  - Translates Lambda response back to MCP format             │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Security Guard                                               │ │
│  │  - Validates AWS SigV4 signatures                            │ │
│  │  - Enforces IAM policies                                     │ │
│  │  - Manages credential providers                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Composition Layer                                            │ │
│  │  - Tool registry (semantic search enabled)                   │ │
│  │  - Request routing to Lambda targets                         │ │
│  │  - Response aggregation                                      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  IAM Role: data-onboarding-agentcore-gateway-role                  │
│  Permissions: lambda:InvokeFunction on 4 Lambda functions          │
└──────────────────────┬──────────────────────────────────────────┬─┘
                       │                                          │
                       │ Lambda Invoke (IAM Auth)                 │
                       │                                          │
┌──────────────────────▼──────────────┐  ┌──────────────────────▼───┐
│  TARGET LAYER                       │  │  FUTURE TARGETS          │
│                                     │  │                          │
│  Lambda: glue-athena                │  │  Lambda: lakeformation   │
│  Target ID: NSQTQTGAOQ              │  │  Target ID: TBD          │
│  Status: READY                      │  │  Status: Not deployed    │
│                                     │  │                          │
│  Tools (3):                         │  │  Lambda: sagemaker       │
│  ├── get_databases                  │  │  Target ID: TBD          │
│  ├── get_tables                     │  │  Status: Not deployed    │
│  └── athena_query                   │  │                          │
│                                     │  │  Lambda: pii-detection   │
│  Credential Provider:               │  │  Target ID: TBD          │
│  GATEWAY_IAM_ROLE                   │  │  Status: Not deployed    │
│                                     │  │                          │
│  Execution Role:                    │  └──────────────────────────┘
│  data-onboarding-mcp-glue-athena    │
│  -role                              │
└──────────────────┬──────────────────┘
                   │
                   │ boto3 AWS SDK
                   │
┌──────────────────▼──────────────────────────────────────────────────┐
│  AWS SERVICES                                                        │
│                                                                      │
│  ├── AWS Glue Data Catalog (databases, tables, schema)              │
│  ├── Amazon Athena (query execution, results)                       │
│  ├── Amazon S3 (data storage, query results)                        │
│  └── AWS Lake Formation (permissions, tags)                         │
└──────────────────────────────────────────────────────────────────────┘
```

## Request Flow

### Example: List Glue Databases

```
1. User in Claude Code:
   "List all Glue databases"

2. Claude Code MCP Client:
   → Constructs MCP request:
     {
       "method": "tools/call",
       "params": {
         "name": "get_databases",
         "arguments": {}
       }
     }

3. MCP Client adds AWS SigV4 signature:
   → Uses AWS credentials from ~/.aws/credentials
   → Adds Authorization header

4. HTTP POST to Gateway URL:
   POST https://data-onboarding-mcp-gateway-zqqrahrcm2.gateway...

5. Gateway Security Guard:
   → Validates SigV4 signature ✓
   → Checks IAM permissions ✓

6. Gateway Translation Layer:
   → Looks up tool "get_databases" in registry
   → Finds Lambda target: glue-athena (NSQTQTGAOQ)
   → Translates MCP request → Lambda event:
     {
       "tool": "get_databases",
       "input": {}
     }

7. Gateway invokes Lambda:
   aws lambda invoke
     --function-name data-onboarding-mcp-glue-athena
     --payload '{"tool":"get_databases","input":{}}'

8. Lambda handler executes:
   glue = boto3.client('glue')
   response = glue.get_databases()

   return {
     "databases": [
       {"name": "bronze_zone", "description": "Raw data"},
       {"name": "silver_zone", "description": "Cleaned data"},
       {"name": "gold_zone", "description": "Curated data"}
     ]
   }

9. Gateway Translation Layer:
   → Translates Lambda response → MCP format:
     {
       "result": {
         "content": [
           {
             "type": "text",
             "text": "Found 3 databases:\n- bronze_zone\n- silver_zone\n- gold_zone"
           }
         ]
       }
     }

10. Claude Code receives MCP response ✓
    → Displays result to user
```

## Components

### 1. Gateway Resource

```yaml
Gateway ID: data-onboarding-mcp-gateway-zqqrahrcm2
Gateway URL: https://data-onboarding-mcp-gateway-zqqrahrcm2.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp
Status: READY
Protocol: MCP (version 2025-11-25)
Auth: AWS_IAM (SigV4)
Search: SEMANTIC
Region: us-east-1
Account: 133661573128
```

### 2. Gateway IAM Role

```yaml
Role Name: data-onboarding-agentcore-gateway-role
Role ARN: arn:aws:iam::133661573128:role/data-onboarding-agentcore-gateway-role

Trust Policy:
  Principal: bedrock-agentcore.amazonaws.com

Permissions:
  - lambda:InvokeFunction
    Resources:
      - data-onboarding-mcp-glue-athena
      - data-onboarding-mcp-lakeformation
      - data-onboarding-mcp-sagemaker-catalog
      - data-onboarding-mcp-pii-detection
```

### 3. Lambda Targets

#### glue-athena (READY)

```yaml
Target ID: NSQTQTGAOQ
Target Name: glue-athena
Status: READY
Description: AWS Glue Data Catalog and Athena query operations

Lambda Function:
  Name: data-onboarding-mcp-glue-athena
  ARN: arn:aws:lambda:us-east-1:133661573128:function:data-onboarding-mcp-glue-athena
  Runtime: python3.12
  Handler: lambda_handler.handler
  Timeout: 300s
  Memory: 512 MB

Tools (3):
  - get_databases: List all Glue databases
  - get_tables: List tables in a database
  - athena_query: Execute Athena SQL query

Credential Provider: GATEWAY_IAM_ROLE

Tool Schema: agentcore/gateway/schemas/glue-athena-tools.json
```

#### lakeformation (Not Deployed)

```yaml
Status: Pending deployment
Lambda: data-onboarding-mcp-lakeformation
Tools: 5 expected (list_lf_tags, grant_permissions, etc.)
```

#### sagemaker-catalog (Not Deployed)

```yaml
Status: Pending deployment
Lambda: data-onboarding-mcp-sagemaker-catalog
Tools: 4 expected (get_custom_metadata, put_custom_metadata, etc.)
```

#### pii-detection (Not Deployed)

```yaml
Status: Pending deployment
Lambda: data-onboarding-mcp-pii-detection
Tools: 2 expected (detect_pii, apply_lf_tags)
```

### 4. Tool Schemas

Each Lambda target has a tool schema (JSON) describing its tools.

**Format**:
```json
[
  {
    "name": "tool_name",
    "description": "What the tool does",
    "inputSchema": {
      "type": "object",
      "properties": {
        "param_name": {
          "type": "string",
          "description": "Parameter description (include defaults here)"
        }
      },
      "required": ["param_name"]
    }
  }
]
```

**Schema Rules**:
- ❌ NO `"default"` fields (not supported by Gateway)
- ✅ Document defaults in `"description"` instead
- ✅ All properties MUST have `"type"` and `"description"`
- ✅ Use `"required"` array for mandatory parameters

**Location**: `agentcore/gateway/schemas/{target}-tools.json`

### 5. MCP Configuration

**Local Mode** (`.mcp.json`):
```json
{
  "mcpServers": {
    "glue-athena": {
      "command": "uv",
      "args": ["run", "--no-project", ...],
      "transport": "stdio"
    },
    // ... 12 more servers
  }
}
```

**Gateway Mode** (`.mcp.gateway.json`):
```json
{
  "mcpServers": {
    "agentcore-gateway": {
      "url": "https://data-onboarding-mcp-gateway-zqqrahrcm2.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
      "transport": "sse",
      "auth": {
        "type": "aws-sigv4",
        "service": "bedrock-agentcore",
        "region": "us-east-1"
      }
    }
  }
}
```

**Key Differences**:
- Local: 13 separate server entries, stdio transport, local processes
- Gateway: 1 server entry, SSE transport, AWS-managed

## Benefits Over Lambda + API Gateway

| Feature | Lambda + API Gateway | AgentCore Gateway |
|---------|---------------------|-------------------|
| **Endpoints** | 13 separate URLs | 1 unified URL |
| **MCP Translation** | Custom adapter code | AWS-managed |
| **Tool Discovery** | Manual OpenAPI sync | Semantic search |
| **Authentication** | Per-endpoint config | Unified IAM SigV4 |
| **Observability** | Per-Lambda logs | Unified Gateway logs |
| **Maintenance** | High (13 endpoints) | Low (1 Gateway) |
| **Setup Time** | 20-30 min | 10-15 min |

## Cost Estimate

| Component | Cost |
|-----------|------|
| **Gateway** | Pay-per-request (~$0.00001/request) |
| **Lambda** | Free tier: 1M requests/month, 400,000 GB-seconds |
| **CloudWatch Logs** | $0.50/GB ingested |
| **Total** | ~$0/month for dev usage |

## Security Model

### Authentication Flow

```
1. Claude Code User
   → Has AWS credentials (~/.aws/credentials)
   → Needs IAM permission: bedrock-agentcore:InvokeGateway

2. Gateway IAM Role
   → Assumed by bedrock-agentcore.amazonaws.com
   → Has permission: lambda:InvokeFunction on 4 Lambdas

3. Lambda Execution Roles
   → Assumed by lambda.amazonaws.com
   → Has permissions: glue:*, athena:*, s3:*, lakeformation:*
```

### IAM Policies

**User Policy** (attached to Claude Code user):
```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock-agentcore:InvokeGateway",
    "bedrock-agentcore:ListGatewayTargets",
    "bedrock-agentcore:GetGateway"
  ],
  "Resource": "arn:aws:bedrock-agentcore:us-east-1:133661573128:gateway/*"
}
```

**Gateway Role Policy** (inline policy on Gateway role):
```json
{
  "Effect": "Allow",
  "Action": "lambda:InvokeFunction",
  "Resource": [
    "arn:aws:lambda:us-east-1:133661573128:function:data-onboarding-mcp-*"
  ]
}
```

**Lambda Execution Role Policy** (per-Lambda, least-privilege):
```json
{
  "Effect": "Allow",
  "Action": [
    "glue:GetDatabase",
    "glue:GetTables",
    "athena:StartQueryExecution",
    "athena:GetQueryResults",
    "s3:GetObject",
    "s3:PutObject",
    "lakeformation:GetDataAccess"
  ],
  "Resource": "*"
}
```

## Monitoring

### CloudWatch Logs

**Gateway Logs**:
- Log Group: `/aws/bedrock-agentcore/gateway/{gateway-id}`
- Streams: Per request ID
- Contents: MCP requests, routing decisions, Lambda invocations

**Lambda Logs**:
- Log Group: `/aws/lambda/data-onboarding-mcp-glue-athena`
- Streams: Per Lambda execution
- Contents: Tool invocations, AWS SDK calls, errors

### CloudWatch Metrics

**Gateway Metrics**:
- `InvocationCount`: Total MCP requests
- `Latency`: Request duration (Gateway → Lambda → Gateway)
- `ErrorRate`: Failed requests (4xx, 5xx)

**Lambda Metrics**:
- `Invocations`: Lambda execution count
- `Duration`: Lambda execution time
- `Errors`: Lambda failures
- `ConcurrentExecutions`: Active Lambda instances

### X-Ray Tracing

**Enabled by default** on Gateway and Lambda.

**Trace segments**:
1. Gateway receives MCP request
2. Gateway translates request
3. Gateway invokes Lambda
4. Lambda executes (boto3 calls auto-traced)
5. Gateway translates response
6. Gateway returns to client

## Troubleshooting

### Gateway Not Accessible

**Symptom**: `Could not reach Gateway endpoint`

**Check**:
1. Gateway status: `aws bedrock-agentcore-control get-gateway --gateway-identifier {ID}`
2. User IAM permissions: `bedrock-agentcore:InvokeGateway`
3. AWS credentials: `aws sts get-caller-identity`

### Target Registration Fails

**Symptom**: `Credential provider configurations is not defined`

**Fix**: Add credential provider config:
```bash
--credential-provider-configurations '[{"credentialProviderType":"GATEWAY_IAM_ROLE"}]'
```

### Lambda Invocation Fails

**Symptom**: Gateway returns error, Lambda not invoked

**Check**:
1. Gateway role policy: `lambda:InvokeFunction` on Lambda ARN
2. Lambda status: `aws lambda get-function --function-name {NAME}`
3. CloudWatch logs: `/aws/bedrock-agentcore/gateway/{ID}`

### Tool Schema Validation Error

**Symptom**: `Unknown parameter in toolSchema: 'default'`

**Fix**: Remove `"default"` fields from tool schema JSON

## Files Reference

| File | Purpose |
|------|---------|
| `prompts/admin/deploy-agentcore-gateway.md` | Full deployment guide |
| `agentcore/gateway/DEPLOYMENT_STATUS.md` | Current deployment state |
| `agentcore/gateway/GATEWAY_ARCHITECTURE.md` | This file |
| `agentcore/gateway/test_gateway.py` | Health check script |
| `agentcore/gateway/schemas/glue-athena-tools.json` | Tool schema for glue-athena |
| `.mcp.gateway.json` | MCP config for Claude Code (Gateway mode) |
| `.mcp.json` | MCP config for Claude Code (Local mode) |

## Next Steps

1. **Add remaining 3 Lambda targets**:
   - lakeformation
   - sagemaker-catalog
   - pii-detection

2. **Test end-to-end from Claude Code**:
   ```bash
   cp .mcp.gateway.json .mcp.json
   # Restart Claude Code
   # Test: "List all Glue databases"
   ```

3. **Cleanup old infrastructure**:
   - Delete Bedrock Agent KTOBR1XWZD
   - Remove API Gateway resources
   - Remove Lambda Function URLs

4. **Return to product catalog onboarding**:
   - Phase 4: Generate pipeline artifacts
   - Use Gateway tools for deployment (Phase 5)

---

**Last Updated**: 2026-03-24
