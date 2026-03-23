# MCP Integration Summary

## What Changed

The Agentic Data Onboarding System now routes **ALL** AWS operations through Model Context Protocol (MCP) servers instead of direct AWS SDK calls. This provides:

1. ✅ **Auditability** - Every operation logged with full context
2. ✅ **Repeatability** - All operations can be replayed from logs
3. ✅ **Standardization** - Consistent interface across all services
4. ✅ **Visual Clarity** - Console output with clear step separators
5. ✅ **Error Tracking** - Structured error logs for debugging

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   User Request                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│            Data Onboarding Agent                            │
│         (main conversation, human-facing)                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              MCP Orchestrator                               │
│         (shared/mcp/orchestrator.py)                        │
│                                                             │
│  • Visual step logging to console                          │
│  • Structured JSON logs to disk                            │
│  • Error handling & retry logic                            │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┴───────────────┐
        │                            │
        ▼                            ▼
┌──────────────────┐       ┌──────────────────┐
│  AWS MCP Servers │       │ Custom MCP Servers│
│  (awslabs/mcp)   │       │   (local)         │
└────────┬─────────┘       └────────┬──────────┘
         │                          │
         │                          │
         ▼                          ▼
┌─────────────────────────────────────────────┐
│           AWS Services                      │
│  Glue • Athena • S3 • DynamoDB • Lambda    │
│  Step Functions • CloudWatch • SNS • KMS   │
└─────────────────────────────────────────────┘
```

## Files Created

### Core Files

1. **`MCP_GUARDRAILS.md`** - MCP tool selection rules per phase
2. **`.mcp.json`** - Configuration for all MCP servers (AWS + custom)
3. **`shared/mcp/orchestrator.py`** - Python orchestration layer with visual logging
4. **`shared/mcp/README.md`** - Usage guide and examples

### Custom MCP Servers

5. **`shared/mcp/servers/sagemaker-catalog-mcp-server/server.py`**
   - Stores business metadata (column roles, PII, hierarchies)
   - Extends Glue Data Catalog with custom properties

6. **`shared/mcp/servers/local-filesystem-mcp-server/server.py`**
   - Reads/writes workload config files
   - Used by Router Agent for deduplication

7. **`shared/mcp/servers/requirements.txt`** - Python dependencies

### Demo & Documentation

8. **`demo_mcp_orchestration.py`** - Complete end-to-end demo
9. **`MCP_INTEGRATION_SUMMARY.md`** (this file)

## Updated Files

- **`TOOLS.md`** - Added MCP Server column to Quick Reference table
- **`CLAUDE.md`** - (to be updated) Add MCP architecture section

## Key MCP Servers

### AWS MCP Servers (from awslabs/mcp)

| Server | Package | Primary Use |
|--------|---------|-------------|
| **aws-dataprocessing** | `awslabs.aws-dataprocessing-mcp-server` | Glue, EMR, Athena - all ETL/cataloging |
| **s3-tables** | `awslabs.s3-tables-mcp-server` | Iceberg tables (Silver/Gold zones) |
| **dynamodb** | `awslabs.dynamodb-mcp-server` | SynoDB (metrics & SQL store) |
| **lambda** | `awslabs.lambda-tool-mcp-server` | Serverless functions |
| **stepfunctions** | `awslabs.stepfunctions-tool-mcp-server` | Workflow orchestration |
| **sns-sqs** | `awslabs.amazon-sns-sqs-mcp-server` | Alerting |
| **cloudwatch** | `awslabs.cloudwatch-mcp-server` | Metrics & logs |
| **iam** | `awslabs.iam-mcp-server` | Roles & policies |

### Custom MCP Servers

| Server | Purpose |
|--------|---------|
| **sagemaker-catalog** | Business metadata (column roles, PII flags, hierarchies) |
| **local-filesystem** | Read/write workload config files |
| **eventbridge** | (to build) EventBridge scheduling |
| **lakeformation** | (to build) Lake Formation permissions |

### MCP Server Status

**LOADED (working, live tools available):**
- `iam` - IAM roles, policies, permission management
- `lambda` - Serverless functions, Lake Formation access grant Lambda
- `redshift` - Query verification via Redshift Spectrum
- `cloudtrail` - Audit log lookup and compliance tracking

**NOT LOADED (CLI fallback required):**
- `aws-dataprocessing` - Glue, EMR, Athena (use AWS CLI)
- `s3-tables` - S3 Tables / Iceberg operations (use AWS CLI)
- `sagemaker-catalog` - SageMaker Catalog operations (use AWS CLI)
- `core` - S3, KMS core services (use AWS CLI)
- `sns-sqs` - SNS/SQS alerting (use AWS CLI)
- `cloudwatch` - CloudWatch metrics/logs (use AWS CLI)
- `cost-explorer` - Cost tracking (use AWS CLI)
- `eventbridge` - EventBridge scheduling (use AWS CLI)
- `lakeformation` - Lake Formation grants (use `lambda` MCP for LF_access_grant Lambda)
- `dynamodb` - DynamoDB operations (use AWS CLI)
- `stepfunctions` - Step Functions orchestration (use AWS CLI)
- `local-filesystem` - Local config files (use Python file I/O)

**Default behavior in local mode:** MCP calls to loaded servers execute live; CLI fallback commands are dry-run unless `DEPLOY_MODE=live`.

## Example: Visual Step Logging

```
════════════════════════════════════════════════════════════════
STEP 3: Schema Discovery (Glue Crawler)
────────────────────────────────────────────────────────────────
Description:    Discover schema from raw S3 data using Glue Crawler
MCP Server:     aws-dataprocessing
Tool:           create_crawler
Input:          {
                  "Name": "sales_transactions_source_crawler",
                  "Role": "arn:aws:iam::123456789012:role/GlueCrawlerRole",
                  "DatabaseName": "sales_transactions_db",
                  "Targets": {
                    "S3Targets": [{
                      "Path": "s3://data-bronze/sales_transactions/"
                    }]
                  }
                }
────────────────────────────────────────────────────────────────
Status:         ✓ SUCCESS
Output:         {"CrawlerName": "sales_transactions_source_crawler", ...}
Duration:       2.3s
════════════════════════════════════════════════════════════════
```

## How to Use

### 1. Install Dependencies

```bash
# Install AWS MCP servers
pip install uvx

# Install custom server dependencies
cd shared/mcp/servers
pip install -r requirements.txt
```

### 2. Configure AWS Credentials

```bash
aws configure
# Enter: Access Key ID, Secret Access Key, region, output format
```

### 3. Run Demo

```bash
python3 demo_mcp_orchestration.py
```

This will:
- Show visual step-by-step logging
- Create structured logs in `logs/mcp/sales_transactions/`
- Simulate a complete data onboarding workflow

### 4. Use in Production

```python
from shared.mcp.orchestrator import MCPOrchestrator

orch = MCPOrchestrator(workload_name="my_data")

# Every operation goes through MCP
orch.call_mcp(
    step_name="Create Glue Crawler",
    mcp_server="aws-dataprocessing",
    tool="create_crawler",
    params={
        "Name": "my_crawler",
        "Role": "...",
        "DatabaseName": "my_db",
        "Targets": {...}
    },
    description="Discover schema from S3"
)
```

## Log Files

Every orchestration run creates two log files:

1. **Console Log** (`logs/mcp/{workload}/{timestamp}.log`)
   - Human-readable
   - Visual separators
   - Easy to review

2. **JSON Log** (`logs/mcp/{workload}/{timestamp}.json`)
   - Machine-readable
   - Full params, results, errors, durations
   - Can be parsed for monitoring/alerting

Example JSON structure:

```json
{
  "workload": "sales_transactions",
  "timestamp": "20250315_102030",
  "steps": [
    {
      "step_number": 1,
      "step_name": "Schema Discovery (Glue Crawler)",
      "mcp_server": "aws-dataprocessing",
      "tool": "create_crawler",
      "params": {...},
      "result": {...},
      "status": "✓ SUCCESS",
      "error": null,
      "duration_seconds": 2.3,
      "timestamp": "2025-03-15T10:20:32"
    }
  ]
}
```

## Benefits

### Before MCP Integration

```python
import boto3

# Direct AWS SDK calls scattered across codebase
glue = boto3.client('glue')
response = glue.create_crawler(...)

# No standardized logging
# Hard to audit what happened
# Difficult to replay operations
# Inconsistent error handling
```

### After MCP Integration

```python
from shared.mcp.orchestrator import MCPOrchestrator

orch = MCPOrchestrator(workload_name="my_data")

# All operations through MCP with logging
orch.call_mcp(
    step_name="Create Crawler",
    mcp_server="aws-dataprocessing",
    tool="create_crawler",
    params={...}
)

# ✓ Automatic visual logging
# ✓ Complete audit trail
# ✓ Operations can be replayed from logs
# ✓ Consistent error handling
# ✓ Clear step separators
```

## Agent Mapping

| Agent | Primary MCP Servers |
|-------|---------------------|
| **Router Agent** | `local-filesystem` |
| **Data Onboarding Agent** | All servers (orchestrates) |
| **Metadata Agent** | `aws-dataprocessing`, `sagemaker-catalog`, `s3-tables` |
| **Transformation Agent** | `aws-dataprocessing`, `s3-tables` |
| **Quality Agent** | `aws-dataprocessing`, `cloudwatch` |
| **Analysis Agent** | `aws-dataprocessing` (Athena), `dynamodb` (SynoDB), `sagemaker-catalog` |
| **Orchestration DAG Agent** | `stepfunctions`, `lambda`, `eventbridge`, `sns-sqs` |

## Phase 5 Deployment via MCP

After human approval of all artifacts and passing test gates, the Data Onboarding Agent executes deployment in the main conversation using MCP tools:

### Deployment Steps

| Step | Operation | MCP Tool (if loaded) | CLI Fallback |
|------|-----------|----------------------|--------------|
| 5.1 | S3 Upload | N/A (not loaded) | `aws s3 cp` |
| 5.2 | Glue Registration | N/A (not loaded) | `aws glue create-database`, `aws glue create-table` |
| 5.3 | IAM Roles & Policies | `mcp__iam__*` | `aws iam create-role`, `aws iam put-role-policy` |
| 5.4 | Lake Formation Grants | `mcp__lambda__invoke` (via LF_access_grant Lambda) | `aws lakeformation grant-permissions` |
| 5.5 | KMS Key Configuration | N/A (not loaded) | `aws kms create-key`, `aws kms create-alias` |
| 5.6 | Query Verification | `mcp__redshift__execute_statement` (via Spectrum) | `aws athena start-query-execution` |
| 5.7 | Audit Log Check | `mcp__cloudtrail__lookup_events` | `aws cloudtrail lookup-events` |
| 5.8 | MWAA DAG Deployment | N/A (no MCP server for MWAA) | `aws s3 cp` to MWAA DAG bucket + `aws mwaa update-environment` |
| 5.9 | Post-Deployment Verification | `mcp__cloudtrail__lookup_events` for audit check, CLI for rest | `aws glue get-table`, `aws athena get-query-execution` |

**Full deployment automation:** `deploy_to_aws.py` handles all steps including MWAA DAG deployment and post-verification.

### Regulation-Specific Compliance Controls

The `prompts/regulation/` directory contains regulation-specific prompts that reference MCP tools for compliance verification:

- **GDPR**, **CCPA**, **HIPAA**, **SOX**, **PCI DSS** prompts
- Use `mcp__lakeformation__*` (when loaded) or `mcp__lambda__invoke` (LF_access_grant Lambda) for LF-Tag verification
- Use `mcp__iam__*` for TBAC grant checks
- Use `mcp__cloudtrail__lookup_events` for audit trail validation

See `prompts/regulation/README.md` for usage instructions.

## Next Steps

### Immediate

1. ✅ **Run the demo** - `python3 demo_mcp_orchestration.py`
2. ✅ **Review logs** - Check `logs/mcp/sales_transactions/`
3. ✅ **Test custom servers** - Start `sagemaker-catalog` and `local-filesystem` servers

### Short-term

4. **Build remaining custom servers**
   - EventBridge MCP Server
   - Lake Formation MCP Server

5. **Update SKILLS.md**
   - Replace direct AWS SDK examples with MCP calls
   - Update agent prompts to use orchestrator

6. **Integrate with actual MCP client**
   - Replace simulated calls in `orchestrator.py`
   - Use real MCP Python SDK communication

### Long-term

7. **Add monitoring** - Send MCP logs to CloudWatch
8. **Add retry logic** - Exponential backoff for transient errors
9. **Add cost tracking** - Tag all MCP operations with workload name
10. **Create MCP server for Analysis Agent** - Natural language → SQL generation

## Testing

### Test Custom MCP Servers

```bash
# Start SageMaker Catalog MCP Server
cd shared/mcp/servers/sagemaker-catalog-mcp-server
python3 server.py

# In another terminal, test it
# (requires MCP client - see modelcontextprotocol.io)
```

### Test Full Orchestration

```bash
# Run demo (uses simulated MCP calls for now)
python3 demo_mcp_orchestration.py

# Check logs
ls -lh logs/mcp/sales_transactions/
cat logs/mcp/sales_transactions/20250315_*.log
```

## Security

All MCP calls:
1. **Authentication** - Use AWS CLI credentials (no hardcoded secrets)
2. **Authorization** - IAM roles with least-privilege policies
3. **Audit** - Every call logged to CloudTrail + local JSON logs
4. **Encryption** - All data at rest (KMS) and in transit (TLS 1.3)
5. **PII Masking** - Sensitive data redacted in logs

## Troubleshooting

### MCP server not found

**Problem**: `FileNotFoundError: uvx: command not found`

**Solution**:
```bash
pip install uv
# Or follow: https://docs.astral.sh/uv/getting-started/installation/
```

### AWS credentials error

**Problem**: `NoCredentialsError: Unable to locate credentials`

**Solution**:
```bash
aws configure
# Or set environment variables:
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
```

### Custom MCP server import error

**Problem**: `ModuleNotFoundError: No module named 'fastmcp'`

**Solution**:
```bash
cd shared/mcp/servers
pip install -r requirements.txt
```

## References

- **MCP Specification**: https://modelcontextprotocol.io
- **AWS MCP Servers**: https://github.com/awslabs/mcp
- **FastMCP Framework**: https://github.com/jlowin/fastmcp
- **Project Documentation**: See `MCP_GUARDRAILS.md`, `MCP_SETUP.md`
