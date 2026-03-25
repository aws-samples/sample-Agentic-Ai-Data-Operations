# 10 -- DEPLOY: Agentcore Runtime (Agent in Cloud)

> Deploy the Data Onboarding Agent to Agentcore Runtime with all 13 Gateway tools.

## Purpose

Hosts the Data Onboarding Agent on Agentcore Runtime so it can be invoked via API. The agent connects to all 13 MCP servers on Gateway -- no local servers or CLI needed. Persistent memory across sessions.

## Local Demo Mode (Alternative)

Runtime deployment is **optional**. If you only need to demo or develop locally, you can skip this prompt entirely:

1. Deploy Gateway only (`prompts/09-deploy-agentcore-gateway.md`)
2. Replace `.mcp.json` with `.mcp.gateway.json`
3. Run Claude Code normally -- all 13 MCP tools are served from Gateway

This gives you cloud-hosted tools without deploying the agent to Runtime. The agent runs in Claude Code on your laptop with full human-in-the-loop control. See `prompts/environment-setup-agent/agentcore/README.md` for details on both execution modes.

## When to Use

Use this prompt (Runtime deployment) when you need **production mode**:

- After `prompts/09-deploy-agentcore-gateway.md` (Gateway with all 13 servers deployed)
- Want the Data Onboarding Agent accessible via REST API
- Building integrations that invoke the agent programmatically
- Team wants a shared agent instance with persistent memory

## Prerequisites

1. Gateway deployed via `prompts/09-deploy-agentcore-gateway.md` (all 13 servers healthy)
2. AWS credentials with Bedrock Agentcore permissions
3. Agent config at `prompts/environment-setup-agent/agentcore/runtime/agent.yaml`

## Prompt Template

```
Deploy Data Onboarding Agent to Agentcore Runtime.

Agent config: prompts/environment-setup-agent/agentcore/runtime/agent.yaml
Gateway: [GATEWAY_ID from prompt 09]
Memory: [agentcore / local]
AWS Region: [us-east-1]
Project name: [data-onboarding]
```

## What Claude Does

### Step 1: Verify Gateway Health

```
Action: Check all 13 Gateway servers are connected and responding
CLI:    aws bedrock-agent get-agent --agent-id {GATEWAY_ID}
Test:   Invoke health_check tool for each of the 13 servers
Output: Gateway status, 13 server health results
Gate:   REQUIRED servers (glue-athena, lakeformation, iam) must be healthy.
        BLOCK if any REQUIRED server fails.
```

### Step 2: Create Runtime IAM Execution Role

```
Action: Create IAM role for the Runtime agent
MCP:    mcp__iam__create_role (trust policy: agentcore.amazonaws.com)
        mcp__iam__put_role_policy (Bedrock model invoke + Gateway access)
Output: Role ARN
Gate:   Role exists and can invoke Bedrock models
```

Role name: `{PROJECT}-agentcore-runtime-role`
Permissions:
- `bedrock:InvokeModel` (for Claude Sonnet)
- Gateway access (all 13 server endpoints)
- CloudWatch logs

### Step 3: Register Agent Definition

```
Action: Create Agentcore Runtime agent from agent.yaml
Read:   prompts/environment-setup-agent/agentcore/runtime/agent.yaml
CLI:    aws bedrock-agent create-agent \
          --agent-name {agent.name} \
          --instruction (from system_prompt_files: CLAUDE.md + SKILLS.md + MCP_GUARDRAILS.md) \
          --foundation-model {agent.model.model_id} \
          --execution-role-arn {ROLE_ARN}
Output: Agent ID, agent version
Gate:   Agent status is PREPARED
```

### Step 4: Configure Memory

```
Action: Set up persistent memory namespace for the agent
CLI:    aws bedrock-agent create-agent-memory \
          --agent-id {AGENT_ID} \
          --memory-type SESSION_SUMMARY \
          --namespace {agent.memory.namespace}
Output: Memory configuration ID
Gate:   Memory namespace accessible
```

### Step 5: Connect All 13 Gateway Tools

```
Action: Associate all Gateway MCP servers as action groups on the Runtime agent
For each of the 13 servers in agent.tools.gateway_servers:
  CLI:  aws bedrock-agent create-agent-action-group \
          --agent-id {AGENT_ID} \
          --action-group-name {server} \
          --action-group-executor (Gateway endpoint for {server})
Output: 13 action groups connected
Gate:   Agent can list tools from all 13 servers
```

### Step 6: Test Agent Invocation

```
Action: Send a test query to verify the agent works end-to-end
CLI:    aws bedrock-agent-runtime invoke-agent \
          --agent-id {AGENT_ID} \
          --session-id test-session \
          --input-text "List all Glue databases in this account"
Output: Agent response (should list databases via glue-athena Gateway server)
Gate:   Agent responds with valid database list (not an error)
```

### Step 7: Present Verification Table

```
AGENTCORE RUNTIME DEPLOYMENT
──────────────────────────────────────────
Agent ID:          {AGENT_ID}
Agent Name:        data-onboarding-agent
Model:             claude-sonnet-4-20250514
Gateway:           {GATEWAY_ID}
Memory:            data-onboarding (session summary)
──────────────────────────────────────────
Gateway Health:    13/13 servers connected  [PASS/FAIL]
IAM Role:          {ROLE_ARN}              [PASS/FAIL]
Agent Registered:  {AGENT_ID}             [PASS/FAIL]
Memory Configured: data-onboarding         [PASS/FAIL]
Tools Connected:   13 Gateway servers      [PASS/FAIL]
Test Invocation:   "List databases"        [PASS/FAIL]
──────────────────────────────────────────
Overall: [ALL PASS / {N} FAILURES]

Invoke via API:
  aws bedrock-agent-runtime invoke-agent \
    --agent-id {AGENT_ID} \
    --session-id my-session \
    --input-text "Onboard customer data from s3://bucket/customers.csv"
```

## After Deployment

- **Invoke via CLI**: `aws bedrock-agent-runtime invoke-agent --agent-id {ID} --input-text "..."`
- **Invoke via SDK**: Use `boto3.client('bedrock-agent-runtime').invoke_agent()`
- **Monitor**: CloudWatch logs under `/aws/bedrock/agent/{AGENT_ID}`
- **Update agent**: Modify `prompts/environment-setup-agent/agentcore/runtime/agent.yaml`, re-run this prompt

## Teardown

```bash
# Delete agent
aws bedrock-agent delete-agent --agent-id {AGENT_ID}

# Delete IAM role
aws iam delete-role-policy --role-name {PROJECT}-agentcore-runtime-role --policy-name runtime-policy
aws iam delete-role --role-name {PROJECT}-agentcore-runtime-role

# Gateway teardown: see prompts/09-deploy-agentcore-gateway.md
```
