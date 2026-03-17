# MCP Integration for Agentic Data Onboarding

This directory contains the MCP (Model Context Protocol) integration layer for the Agentic Data Onboarding System. All AWS operations are routed through MCP servers for auditability, repeatability, and standardization.

## Architecture

```
User Request
     ↓
Data Onboarding Agent
     ↓
MCP Orchestrator (orchestrator.py)
     ↓
┌────────────────┴─────────────────┐
│                                   │
AWS MCP Servers            Custom MCP Servers
(awslabs/mcp)              (local/custom)
     ↓                              ↓
AWS Services             Config Files / Local Ops
```

## Quick Start

### 1. Install AWS MCP Servers

```bash
# Install all required AWS MCP servers
pip install uvx

uvx awslabs.aws-dataprocessing-mcp-server@latest --help
uvx awslabs.s3-tables-mcp-server@latest --help
uvx awslabs.dynamodb-mcp-server@latest --help
uvx awslabs.lambda-tool-mcp-server@latest --help
uvx awslabs.stepfunctions-tool-mcp-server@latest --help
uvx awslabs.amazon-sns-sqs-mcp-server@latest --help
uvx awslabs.iam-mcp-server@latest --help
uvx awslabs.cloudwatch-mcp-server@latest --help
uvx awslabs.cloudtrail-mcp-server@latest --help
uvx awslabs.cost-explorer-mcp-server@latest --help
uvx awslabs.redshift-mcp-server@latest --help
uvx awslabs.core-mcp-server@latest --help
```

### 2. Install Custom MCP Server Dependencies

```bash
cd shared/mcp/servers
pip install -r requirements.txt
```

### 3. Configure AWS Credentials

```bash
aws configure
# Enter your AWS Access Key ID, Secret Access Key, region, and output format
```

### 4. Test Custom MCP Servers

```bash
# Test SageMaker Catalog MCP Server
python3 sagemaker-catalog-mcp-server/server.py &
MCP_SERVER_PID=$!

# Test Local Filesystem MCP Server
python3 local-filesystem-mcp-server/server.py &

# Kill test servers
kill $MCP_SERVER_PID
```

### 5. Run Example Orchestration

```bash
cd ../..  # Back to project root
python3 shared/mcp/orchestrator.py
```

This will run an example onboarding workflow with visual step logging:

```
════════════════════════════════════════════════════════════════
STEP 1: Check Existing Workload
────────────────────────────────────────────────────────────────
MCP Server:     local-filesystem
Tool:           list_directories
Input:          {"path": "workloads/"}
────────────────────────────────────────────────────────────────
Status:         ✓ SUCCESS
Output:         {"workloads": [...]}
Duration:       0.12s
════════════════════════════════════════════════════════════════
```

## Custom MCP Servers

### sagemaker-catalog-mcp-server

Stores business metadata (column roles, PII flags, hierarchies) as custom properties in the Glue Data Catalog.

**Tools**:
- `put_custom_metadata`: Store metadata for a table
- `get_custom_metadata`: Retrieve metadata for a table
- `get_column_metadata`: Get metadata for a specific column
- `list_measures`: List all measure columns (for SQL generation)
- `list_dimensions`: List all dimension columns

**Usage**:
```python
from mcp_orchestrator import MCPOrchestrator

orch = MCPOrchestrator(workload_name="sales")

orch.call_mcp(
    step_name="Store Column Roles",
    mcp_server="sagemaker-catalog",
    tool="put_custom_metadata",
    params={
        "database": "sales_db",
        "table": "sales_silver",
        "custom_metadata": {
            "columns": {
                "revenue": {
                    "role": "measure",
                    "default_aggregation": "sum",
                    "business_name": "Total Revenue"
                }
            }
        }
    }
)
```

### local-filesystem-mcp-server

Reads and writes workload configuration files. Used by the Router Agent to check for existing workloads.

**Tools**:
- `list_workloads`: List all workload directories
- `get_workload_config`: Read a config file (source.yaml, semantic.yaml, etc.)
- `search_workloads_by_source`: Find workloads by source type/location (deduplication)
- `write_workload_config`: Write a config file
- `read_file`: Read any project file

**Usage**:
```python
orch.call_mcp(
    step_name="Check for Duplicate Sources",
    mcp_server="local-filesystem",
    tool="search_workloads_by_source",
    params={
        "source_type": "s3",
        "location_pattern": "sales"
    }
)
```

## AWS MCP Servers

### aws-dataprocessing-mcp-server

Comprehensive data processing covering Glue, EMR, and Athena.

**Key Tools**:
- **Glue Crawlers**: `create_crawler`, `start_crawler`, `get_crawler`
- **Glue ETL Jobs**: `create_job`, `start_job_run`, `get_job_run`
- **Athena Queries**: `start_query_execution`, `get_query_results`, `get_query_execution`
- **Glue Data Quality**: `create_data_quality_ruleset`, `start_data_quality_rule_run`
- **Glue Data Catalog**: `get_database`, `get_table`, `get_partitions`

### s3-tables-mcp-server

Manage Apache Iceberg tables on S3 Tables (Silver/Gold zones).

**Key Tools**:
- `create_table_bucket`: Create S3 Tables bucket
- `create_table`: Create Iceberg table
- `update_table_metadata`: Update table metadata
- `get_table_metadata`: Retrieve table info

### dynamodb-mcp-server

Interact with DynamoDB (used for SynoDB - metrics & SQL store).

**Key Tools**:
- `put_item`: Store SQL query patterns
- `query`: Find similar past queries
- `scan`: List all queries
- `get_item`: Retrieve specific query

### Other AWS MCP Servers

- **lambda-tool-mcp-server**: Invoke Lambda functions for ingestion/triggers
- **stepfunctions-tool-mcp-server**: Create and run Step Functions state machines
- **amazon-sns-sqs-mcp-server**: Send alerts via SNS
- **iam-mcp-server**: Manage IAM roles and policies
- **cloudwatch-mcp-server**: Log metrics and create alarms
- **cloudtrail-mcp-server**: Query audit logs
- **cost-explorer-mcp-server**: Track workload costs
- **redshift-mcp-server**: Execute large-scale analytics queries

## Orchestrator Usage

The `MCPOrchestrator` class provides:

1. **Visual Step Logging** - Every operation printed with clear separators
2. **Structured JSON Logs** - All steps saved to `logs/mcp/{workload}/`
3. **Error Handling** - Automatic retry logic and error escalation
4. **Auditability** - Complete trace of all MCP calls

### Example: Full Pipeline

```python
from shared.mcp.orchestrator import MCPOrchestrator

orch = MCPOrchestrator(workload_name="customer_data")

# Phase 1: Check existing workloads
orch.call_mcp(
    step_name="Router: Check Existing",
    mcp_server="local-filesystem",
    tool="list_workloads",
    params={}
)

# Phase 3: Schema discovery
orch.call_mcp(
    step_name="Metadata: Glue Crawler",
    mcp_server="aws-dataprocessing",
    tool="create_crawler",
    params={
        "Name": "customer_data_crawler",
        "Role": "arn:aws:iam::123456789012:role/GlueCrawlerRole",
        "DatabaseName": "customer_db",
        "Targets": {"S3Targets": [{"Path": "s3://bronze/customer/"}]}
    }
)

# Phase 4: Bronze → Silver transformation
orch.call_mcp(
    step_name="Transformation: Bronze to Silver",
    mcp_server="aws-dataprocessing",
    tool="create_job",
    params={
        "Name": "customer_bronze_to_silver",
        "Role": "arn:aws:iam::123456789012:role/GlueETLRole",
        "Command": {
            "Name": "glueetl",
            "ScriptLocation": "s3://scripts/bronze_to_silver.py"
        }
    }
)

# Phase 4: Quality check
orch.call_mcp(
    step_name="Quality: Data Quality Check",
    mcp_server="aws-dataprocessing",
    tool="create_data_quality_ruleset",
    params={
        "Name": "customer_silver_quality",
        "Ruleset": "Rules = [Completeness 'email' > 0.95]"
    }
)

# Phase 4: Store metadata
orch.call_mcp(
    step_name="Metadata: Business Context",
    mcp_server="sagemaker-catalog",
    tool="put_custom_metadata",
    params={
        "database": "customer_db",
        "table": "customer_silver",
        "custom_metadata": {
            "columns": {
                "email": {"role": "identifier", "pii": True}
            }
        }
    }
)

# Summary
orch.phase_summary(
    phase_name="Pipeline Creation",
    summary="✓ All pipeline components created successfully"
)
```

## Log Files

All operations are logged to:

1. **Console Log**: `logs/mcp/{workload}/{timestamp}.log`
   - Human-readable with visual separators
   - Easy to review in text editor

2. **JSON Log**: `logs/mcp/{workload}/{timestamp}.json`
   - Machine-readable structured format
   - Includes all params, results, errors, durations
   - Can be parsed for monitoring/alerting

## Configuration

Edit `.mcp.json` in the project root to:
- Change AWS profile/region
- Enable/disable specific MCP servers
- Adjust log levels
- Add new custom MCP servers

## Next Steps

1. **Build remaining custom servers**: EventBridge, Lake Formation
2. **Integrate with SKILLS.md**: Update agent prompts to use MCP calls
3. **Add retry logic**: Implement exponential backoff for transient errors
4. **Add monitoring**: Send MCP logs to CloudWatch
5. **Add cost tracking**: Tag all MCP operations with workload name
