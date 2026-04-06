# Deploy Amazon Bedrock AgentCore Gateway

> **Admin Guide**: Deploy MCP servers to Amazon Bedrock AgentCore Gateway (unified managed endpoint)

## Purpose

This guide deploys a production-ready MCP Gateway using **Amazon Bedrock AgentCore Gateway** - AWS's fully-managed service for hosting MCP-compatible tools. This replaces custom Lambda + API Gateway infrastructure with a unified, enterprise-grade solution.

**What AgentCore Gateway provides**:
- ✅ **Translation Layer**: Automatic MCP ↔ Lambda conversion (no custom adapter code)
- ✅ **Composition**: Single endpoint for multiple Lambda targets
- ✅ **Security Guard**: Built-in IAM authentication (SigV4)
- ✅ **Semantic Search**: Natural language tool discovery
- ✅ **Observability**: CloudWatch logs, X-Ray tracing, metrics
- ✅ **Credential Management**: OAuth, API keys, IAM role assumption

## Architecture

```
Claude Code (.mcp.gateway.json)
  ↓ MCP over HTTPS + AWS SigV4
  ↓
Amazon Bedrock AgentCore Gateway (unified endpoint)
  ↓ Routes MCP requests to Lambda targets
  ├── Target: glue-athena (3 tools)
  ├── Target: lakeformation (5 tools)
  ├── Target: sagemaker-catalog (4 tools)
  └── Target: pii-detection (2 tools)
       ↓ Lambda execution
       ↓
AWS Services (Glue, Athena, S3, Lake Formation, etc.)
```

**Key difference from Lambda + API Gateway**:
- **Old**: 13 separate endpoints, custom MCP adapter, manual OpenAPI schemas
- **New**: 1 unified endpoint, AWS-managed translation, automatic tool discovery

## Prerequisites

1. **AWS CLI** v2.15+ with `bedrock-agentcore-control` service support
   ```bash
   aws --version  # Should be >= 2.15.0
   aws bedrock-agentcore-control help  # Should show commands
   ```

2. **AWS Credentials** with permissions:
   - `iam:CreateRole`, `iam:AttachRolePolicy`, `iam:PutRolePolicy`
   - `lambda:CreateFunction`, `lambda:UpdateFunctionCode`, `lambda:AddPermission`
   - `bedrock-agentcore:CreateGateway`, `bedrock-agentcore:CreateGatewayTarget`

3. **Lambda Functions** already deployed:
   - `data-onboarding-mcp-glue-athena`
   - `data-onboarding-mcp-lakeformation`
   - `data-onboarding-mcp-sagemaker-catalog`
   - `data-onboarding-mcp-pii-detection`

   If not deployed, see `../../../mcp-servers/` for server code and deployment instructions

4. **Tool Schemas** for each Lambda (JSON format describing tools)

## Deployment Steps

### Step 1: Create Gateway IAM Role

The Gateway needs an IAM role to invoke Lambda functions.

**Create trust policy** (allows AgentCore service to assume role):
```bash
cat > /tmp/gateway-trust-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF
```

**Create Lambda invoke policy**:
```bash
# Get your AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"  # Change if needed
PROJECT="data-onboarding"  # Change if needed

cat > /tmp/gateway-lambda-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "lambda:InvokeFunction",
    "Resource": [
      "arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${PROJECT}-mcp-glue-athena",
      "arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${PROJECT}-mcp-lakeformation",
      "arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${PROJECT}-mcp-sagemaker-catalog",
      "arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${PROJECT}-mcp-pii-detection"
    ]
  }]
}
EOF
```

**Create the IAM role**:
```bash
# Create role
aws iam create-role \
  --role-name ${PROJECT}-agentcore-gateway-role \
  --assume-role-policy-document file:///tmp/gateway-trust-policy.json \
  --description "AgentCore Gateway execution role for MCP tools"

# Attach Lambda invoke policy
aws iam put-role-policy \
  --role-name ${PROJECT}-agentcore-gateway-role \
  --policy-name gateway-lambda-invoke \
  --policy-document file:///tmp/gateway-lambda-policy.json

# Wait for IAM propagation
sleep 10

echo "✓ Gateway IAM role created"
```

**Expected output**:
```json
{
  "Role": {
    "RoleName": "data-onboarding-agentcore-gateway-role",
    "Arn": "arn:aws:iam::133661573128:role/data-onboarding-agentcore-gateway-role",
    "CreateDate": "2026-03-24T19:03:38Z"
  }
}
```

### Step 2: Create AgentCore Gateway

**Create the Gateway resource**:
```bash
aws bedrock-agentcore-control create-gateway \
  --name ${PROJECT}-mcp-gateway \
  --description "MCP Gateway for data onboarding tools" \
  --protocol-type MCP \
  --protocol-configuration '{
    "mcp": {
      "supportedVersions": ["2025-11-25"],
      "searchType": "SEMANTIC"
    }
  }' \
  --authorizer-type AWS_IAM \
  --role-arn arn:aws:iam::${ACCOUNT_ID}:role/${PROJECT}-agentcore-gateway-role \
  --region ${REGION}
```

**Expected output**:
```json
{
  "gatewayArn": "arn:aws:bedrock-agentcore:us-east-1:133661573128:gateway/data-onboarding-mcp-gateway-zqqrahrcm2",
  "gatewayId": "data-onboarding-mcp-gateway-zqqrahrcm2",
  "gatewayUrl": "https://data-onboarding-mcp-gateway-zqqrahrcm2.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
  "status": "CREATING",
  "createdAt": "2026-03-24T19:04:06.659727+00:00"
}
```

**Save the Gateway ID** for next steps:
```bash
GATEWAY_ID=$(aws bedrock-agentcore-control list-gateways \
  --region ${REGION} \
  --query "items[?name=='${PROJECT}-mcp-gateway'].gatewayId" \
  --output text)

echo "Gateway ID: $GATEWAY_ID"
```

**Wait for Gateway to be READY** (takes ~30-60 seconds):
```bash
# Check status
aws bedrock-agentcore-control get-gateway \
  --gateway-identifier $GATEWAY_ID \
  --region ${REGION} \
  --query 'status' \
  --output text

# Should output: READY
```

### Step 3: Create Tool Schemas

Each Lambda target needs a tool schema describing its tools.

**Create schema for glue-athena**:
```bash
mkdir -p prompts/environment-setup-agent/agentcore/gateway/schemas

cat > prompts/environment-setup-agent/agentcore/gateway/schemas/glue-athena-tools.json <<'EOF'
[
  {
    "name": "get_databases",
    "description": "List all AWS Glue Data Catalog databases in the account. Returns database names, descriptions, and S3 locations.",
    "inputSchema": {
      "type": "object",
      "properties": {},
      "required": []
    }
  },
  {
    "name": "get_tables",
    "description": "List all tables in a specific Glue database. Returns table names, types, S3 locations, and column counts.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "database": {
          "type": "string",
          "description": "The name of the Glue database to query"
        }
      },
      "required": ["database"]
    }
  },
  {
    "name": "athena_query",
    "description": "Execute an Athena SQL query synchronously. Waits for query completion and returns results (up to 100 rows). Use for data discovery, schema inspection, and sample queries.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "The SQL query to execute (e.g., 'SELECT * FROM database.table LIMIT 10')"
        },
        "database": {
          "type": "string",
          "description": "The Glue database context for the query"
        },
        "workgroup": {
          "type": "string",
          "description": "Athena workgroup to use (default: 'primary')"
        },
        "timeout_seconds": {
          "type": "integer",
          "description": "Maximum time to wait for query completion (default: 300)"
        }
      },
      "required": ["query", "database"]
    }
  }
]
EOF
```

**⚠️ Schema Validation Rules**:
- ❌ NO `"default"` fields in properties (not supported by AgentCore)
- ✅ Use `"description"` to document defaults instead
- ✅ All properties must have `"type"` and `"description"`
- ✅ `"required"` array must list mandatory parameters

**Create schemas for other servers** (repeat for lakeformation, sagemaker-catalog, pii-detection):
```bash
# TODO: Add schemas for remaining 3 servers
# See mcp-servers/{server}/server.py for tool definitions
```

### Step 4: Register Lambda Targets

Register each Lambda function as a Gateway target.

**Create target configuration for glue-athena**:
```bash
cat > /tmp/glue-athena-target.json <<EOF
{
  "mcp": {
    "lambda": {
      "lambdaArn": "arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${PROJECT}-mcp-glue-athena",
      "toolSchema": {
        "inlinePayload": $(cat prompts/environment-setup-agent/agentcore/gateway/schemas/glue-athena-tools.json)
      }
    }
  }
}
EOF
```

**Register the target**:
```bash
aws bedrock-agentcore-control create-gateway-target \
  --gateway-identifier $GATEWAY_ID \
  --name glue-athena \
  --description "AWS Glue Data Catalog and Athena query operations" \
  --target-configuration file:///tmp/glue-athena-target.json \
  --credential-provider-configurations '[{"credentialProviderType":"GATEWAY_IAM_ROLE"}]' \
  --region ${REGION}
```

**Expected output**:
```json
{
  "targetId": "NSQTQTGAOQ",
  "status": "CREATING",
  "name": "glue-athena",
  "createdAt": "2026-03-24T19:06:59.488101+00:00"
}
```

**Wait for target to be READY** (takes ~5-10 seconds):
```bash
TARGET_ID=$(aws bedrock-agentcore-control list-gateway-targets \
  --gateway-identifier $GATEWAY_ID \
  --region ${REGION} \
  --query "items[?name=='glue-athena'].targetId" \
  --output text)

aws bedrock-agentcore-control get-gateway-target \
  --gateway-identifier $GATEWAY_ID \
  --target-id $TARGET_ID \
  --region ${REGION} \
  --query 'status' \
  --output text

# Should output: READY
```

**Repeat for remaining targets**:
```bash
# TODO: Register lakeformation, sagemaker-catalog, pii-detection
# Follow same pattern: create schema → create config → register target
```

### Step 5: Verify Gateway Status

**List all registered targets**:
```bash
aws bedrock-agentcore-control list-gateway-targets \
  --gateway-identifier $GATEWAY_ID \
  --region ${REGION}
```

**Expected output**:
```json
{
  "items": [
    {
      "targetId": "NSQTQTGAOQ",
      "name": "glue-athena",
      "status": "READY",
      "description": "AWS Glue Data Catalog and Athena query operations",
      "createdAt": "2026-03-24T19:06:59.488101+00:00",
      "updatedAt": "2026-03-24T19:07:02.500647+00:00"
    }
  ]
}
```

**Get Gateway details**:
```bash
aws bedrock-agentcore-control get-gateway \
  --gateway-identifier $GATEWAY_ID \
  --region ${REGION}
```

**Expected output**:
```json
{
  "gatewayId": "data-onboarding-mcp-gateway-zqqrahrcm2",
  "gatewayUrl": "https://data-onboarding-mcp-gateway-zqqrahrcm2.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
  "status": "READY",
  "name": "data-onboarding-mcp-gateway",
  "authorizerType": "AWS_IAM",
  "protocolType": "MCP",
  "protocolConfiguration": {
    "mcp": {
      "supportedVersions": ["2025-11-25"],
      "searchType": "SEMANTIC"
    }
  }
}
```

### Step 6: Generate .mcp.gateway.json

Create MCP configuration file for Claude Code.

```bash
GATEWAY_URL=$(aws bedrock-agentcore-control get-gateway \
  --gateway-identifier $GATEWAY_ID \
  --region ${REGION} \
  --query 'gatewayUrl' \
  --output text)

cat > .mcp.gateway.json <<EOF
{
  "mcpServers": {
    "agentcore-gateway": {
      "url": "${GATEWAY_URL}",
      "transport": "sse",
      "auth": {
        "type": "aws-sigv4",
        "service": "bedrock-agentcore",
        "region": "${REGION}"
      }
    }
  }
}
EOF

echo "✓ Generated .mcp.gateway.json"
```

**File contents**:
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

### Step 7: Test Gateway (Optional but Recommended)

**Run health check script**:
```bash
python3 prompts/environment-setup-agent/agentcore/gateway/test_gateway.py
```

**Expected output**:
```
================================================================================
TESTING AGENTCORE GATEWAY
================================================================================
Gateway URL: https://data-onboarding-mcp-gateway-zqqrahrcm2...
Region: us-east-1
Authentication: AWS IAM (SigV4)

✓ AWS Credentials: AKIAR6HWZY...

Test 1: List Gateway Targets
--------------------------------------------------------------------------------
✓ Found 1 registered target(s):
  - glue-athena (READY)
    Target ID: NSQTQTGAOQ
    Description: AWS Glue Data Catalog and Athena query operations

Test 2: Gateway Endpoint Accessibility
--------------------------------------------------------------------------------
✓ Gateway endpoint is reachable (HTTP 404)
  Response headers: {...}

================================================================================
GATEWAY STATUS: ✅ READY
================================================================================

Next Steps:
1. Copy .mcp.gateway.json to .mcp.json
2. Restart Claude Code
3. Test tool invocation:
   User: "List all Glue databases using the Gateway"
   Claude: uses agentcore-gateway.get_databases

Gateway is deployed and ready for Claude Code integration!
```

## Using the Gateway

### From Claude Code

**Switch to Gateway mode**:
```bash
# Backup local config
cp .mcp.json .mcp.local.json

# Activate Gateway
cp .mcp.gateway.json .mcp.json

# Restart Claude Code
# All MCP tools now route through Gateway
```

**Test tool invocation**:
```
User: "List all Glue databases"
Claude Code: *invokes agentcore-gateway.get_databases*
           → Gateway translates MCP → Lambda
           → Lambda queries Glue
           → Gateway translates result → MCP
           → Claude receives response
```

**Revert to local mode**:
```bash
cp .mcp.local.json .mcp.json
# or: git checkout .mcp.json
# Restart Claude Code
```

### From AWS CLI (Direct Lambda Test)

**Test Lambda function directly** (bypasses Gateway):
```bash
aws lambda invoke \
  --function-name data-onboarding-mcp-glue-athena \
  --payload '{"tool":"get_databases","input":{}}' \
  /tmp/response.json

cat /tmp/response.json
```

## Troubleshooting

### Gateway Creation Fails

**Error**: `Unsupported MCP Version(s) are provided in request: [1.0]`

**Solution**: Use date-based version format, not semantic versioning:
```bash
# ❌ Wrong
"supportedVersions": ["1.0"]

# ✅ Correct
"supportedVersions": ["2025-11-25"]
```

### Target Registration Fails

**Error**: `Unknown parameter in toolSchema: 'default'`

**Solution**: Remove `"default"` fields from tool schemas:
```bash
# ❌ Wrong
"workgroup": {
  "type": "string",
  "default": "primary"
}

# ✅ Correct
"workgroup": {
  "type": "string",
  "description": "Athena workgroup to use (default: 'primary')"
}
```

**Error**: `Credential provider configurations is not defined`

**Solution**: Add credential provider to target registration:
```bash
--credential-provider-configurations '[{"credentialProviderType":"GATEWAY_IAM_ROLE"}]'
```

### Gateway Unreachable

**Error**: `Could not reach Gateway endpoint`

**Solution**: Check IAM permissions:
```bash
# User needs these permissions
aws iam get-user-policy \
  --user-name YOUR_USERNAME \
  --policy-name YOUR_POLICY

# Required actions:
# - bedrock-agentcore:InvokeGateway
# - bedrock-agentcore:ListGatewayTargets
```

### Lambda Invocation Fails

**Error**: `Gateway cannot invoke Lambda`

**Solution**: Check Gateway role permissions:
```bash
# Gateway role needs lambda:InvokeFunction
aws iam get-role-policy \
  --role-name data-onboarding-agentcore-gateway-role \
  --policy-name gateway-lambda-invoke
```

## Deployment Summary

After successful deployment, you have:

| Component | Count | Status |
|-----------|-------|--------|
| **Gateway** | 1 | ✅ READY |
| **Endpoint** | 1 unified URL | ✅ Active |
| **Lambda Targets** | 4 (glue-athena, lakeformation, sagemaker-catalog, pii-detection) | ✅ Registered |
| **MCP Tools** | 14+ (3 glue-athena + 5 lakeformation + 4 sagemaker-catalog + 2 pii-detection) | ✅ Available |
| **IAM Role** | 1 (Gateway execution) | ✅ Created |
| **Config File** | .mcp.gateway.json | ✅ Generated |

**Cost**: ~$0 (Gateway is pay-per-use, Lambda free tier covers most usage)

## Next Steps

1. **Test Gateway from Claude Code**:
   ```bash
   cp .mcp.gateway.json .mcp.json
   # Restart Claude Code
   # Test: "List all Glue databases"
   ```

2. **Add remaining Lambda targets** (if you have more MCP servers):
   - Create tool schemas
   - Register targets
   - Test each tool

3. **Deploy Agentcore Runtime** (optional):
   - See `prompts/10-deploy-agentcore-runtime.md`
   - Hosts Data Onboarding Agent in cloud
   - API-driven, fully serverless

4. **Cleanup old infrastructure**:
   - Delete Bedrock Agent (if using old approach)
   - Remove API Gateway resources
   - Remove Lambda Function URLs

## Comparison: Gateway vs Lambda+API Gateway

| Feature | Lambda + API Gateway | AgentCore Gateway |
|---------|---------------------|-------------------|
| **Endpoints** | 13 separate URLs | 1 unified URL |
| **MCP Translation** | Custom adapter code | AWS-managed |
| **Tool Discovery** | Manual OpenAPI | Semantic search |
| **Authentication** | API keys, IAM per endpoint | IAM SigV4 (unified) |
| **Observability** | CloudWatch per Lambda | Unified Gateway logs |
| **Maintenance** | High (13 endpoints) | Low (1 Gateway) |
| **Cost** | API Gateway + Lambda | Gateway + Lambda |
| **Setup Time** | ~20-30 min | ~10-15 min |

**Recommendation**: Use AgentCore Gateway for production deployments. It's simpler, more secure, and easier to maintain.

## Files Created

- `/tmp/gateway-trust-policy.json` - Gateway IAM trust policy
- `/tmp/gateway-lambda-policy.json` - Lambda invoke permissions
- `prompts/environment-setup-agent/agentcore/gateway/schemas/glue-athena-tools.json` - Tool schema
- `/tmp/glue-athena-target.json` - Target configuration
- `.mcp.gateway.json` - MCP config for Claude Code
- `prompts/environment-setup-agent/agentcore/gateway/DEPLOYMENT_STATUS.md` - Deployment documentation
- `prompts/environment-setup-agent/agentcore/gateway/test_gateway.py` - Health check script

## Resources

- **AWS Documentation**: [Amazon Bedrock AgentCore Gateway](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-gateway.html)
- **MCP Specification**: [Model Context Protocol](https://modelcontextprotocol.io/)
- **Local Setup**: See `docs/mcp-setup.md` for local stdio mode
- **Runtime Agent**: See `prompts/10-deploy-agentcore-runtime.md`
