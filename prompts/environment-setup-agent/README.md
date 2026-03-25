# Environment Setup Agent

**Agent Type**: Setup / Infrastructure
**Runs**: Once per AWS account
**Prerequisites**: AWS CLI, valid credentials

## Purpose

The Environment Setup Agent prepares the AWS infrastructure and MCP Gateway for all data onboarding workloads. This agent runs BEFORE any data onboarding work begins.

## What It Sets Up

1. **AWS Infrastructure** (IAM, S3, KMS, Glue, Lake Formation, Airflow)
2. **MCP Gateway** (Amazon Bedrock AgentCore Gateway for cloud-hosted MCP servers)
3. **Runtime Agent** (Optional: Cloud-hosted Data Onboarding Agent)

## Prompts in This Folder

| Prompt | Purpose | Time | Run Order |
|--------|---------|------|-----------|
| `setup-aws-infrastructure.md` | Create IAM roles, S3 buckets, KMS keys, Glue databases, LF-Tags, MWAA | ~20 min | 1st |
| `deploy-agentcore-gateway.md` | Deploy MCP servers to AgentCore Gateway (unified endpoint) | ~15 min | 2nd (optional) |
| `deploy-agentcore-runtime.md` | Deploy Data Onboarding Agent to Runtime (API-accessible) | ~10 min | 3rd (optional) |

## When to Run

**First time in AWS account**:
```bash
# Run all 3 prompts in order
1. setup-aws-infrastructure.md
2. deploy-agentcore-gateway.md (if using Gateway mode)
3. deploy-agentcore-runtime.md (if using Runtime mode)
```

**Already set up**:
- Skip this folder entirely
- Go directly to `data-onboarding-agent/` to onboard new data sources

**Switching modes**:
- Local → Gateway: Run `deploy-agentcore-gateway.md`
- Gateway → Local: `git checkout .mcp.json` (no prompt needed)

## After Setup

Once environment setup is complete:

1. **Local Mode**: MCP servers run on your laptop
   ```bash
   # Already configured in .mcp.json
   # Just start Claude Code
   ```

2. **Gateway Mode**: MCP servers run in AWS
   ```bash
   cp .mcp.gateway.json .mcp.json
   # Restart Claude Code
   ```

3. **Proceed to data onboarding**:
   ```bash
   # Start onboarding a data source
   # See: data-onboarding-agent/README.md
   ```

## Output Artifacts

After running these prompts, you have:

- ✅ IAM roles (13 MCP servers + workload execution)
- ✅ S3 buckets (bronze/silver/gold zones)
- ✅ KMS keys (encryption)
- ✅ Glue databases (bronze_zone, silver_zone, gold_zone)
- ✅ Lake Formation LF-Tags (PII_Classification, Data_Sensitivity, etc.)
- ✅ MWAA environment (Airflow for orchestration)
- ✅ Cedar policy store (Amazon Verified Permissions)
- ✅ MCP Gateway (optional - if deployed)
- ✅ Runtime Agent (optional - if deployed)

## Verification

Check that setup succeeded:

```bash
# Check AWS resources
aws s3 ls | grep finsights-datalake
aws glue get-databases | grep bronze_zone
aws lakeformation list-lf-tags

# Check MCP servers (local mode)
claude mcp list

# Check MCP Gateway (if deployed)
python3 prompts/environment-setup-agent/agentcore/gateway/test_gateway.py

# Check Runtime Agent (if deployed)
aws bedrock-agent list-agents | grep data-onboarding
```

## Troubleshooting

**Issue**: "AWS credentials not found"
- Run: `aws configure`
- Or set: `AWS_PROFILE=your-profile`

**Issue**: "IAM role already exists"
- This is OK - setup is idempotent
- Existing resources are reused

**Issue**: "MCP server failed to connect"
- See: `../../MCP_SETUP.md`
- Check: `uv --version` (need 0.9+)
- Check: Python 3.12+ installed

**Issue**: "Gateway deployment failed"
- Check: AWS CLI version >= 2.15.0
- Check: `bedrock-agentcore-control` service available
- See: `deploy-agentcore-gateway.md` troubleshooting section

## Related Documentation

- `../../MCP_SETUP.md` - MCP server configuration guide
- `agentcore/gateway/GATEWAY_ARCHITECTURE.md` - Gateway architecture
- `../../CLAUDE.md` - Project-level configuration
- `../data-onboarding-agent/README.md` - Next step after setup
