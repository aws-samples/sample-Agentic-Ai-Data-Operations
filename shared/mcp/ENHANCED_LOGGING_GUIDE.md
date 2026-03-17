# Enhanced MCP Logging Guide

## Overview

The enhanced orchestrator provides **detailed, agent-aware logging** with clear visual separations, comprehensive timing information, and operation classification.

## Key Features

### 1. ✅ **Agent Identification**
Every operation clearly shows which agent is executing:

```
╔════════════════════════════════════════════════════════════════╗
║  AGENT: Metadata Agent          PHASE: Schema Discovery       ║
╚════════════════════════════════════════════════════════════════╝
```

### 2. ✅ **Operation Classification**
Operations are automatically classified:

| Icon | Type | Examples |
|------|------|----------|
| 📖 | **READ** | get, list, describe, query, scan, search |
| ✍️ | **WRITE** | create, put, insert, update, set, add |
| 🗑️ | **DELETE** | delete, remove, drop |
| ⚡ | **EXECUTE** | start, run, execute, invoke, trigger |
| ✅ | **VALIDATE** | validate, check, test, verify |

### 3. ✅ **Detailed Timing Information**

```
⏱️  Timing Details:
  {
    "Start": "10:58:57.534",     # Precise start time
    "End": "10:58:57.964",       # Precise end time
    "Duration": "0.430s"         # Actual duration
  }
🚀 Performance: Faster than expected (0.43s vs 1.00s)
```

### 4. ✅ **MCP Server & Tool Details**

```
🔧 MCP Server:         aws-dataprocessing
🛠️  Tool:             create_crawler
📦 Resources:
  [
    "Name=sales_transactions_crawler",
    "DatabaseName=sales_transactions_db"
  ]
⏱️  Expected Duration: ~3.0s
```

### 5. ✅ **Clear Visual Separations**

```
════════════════════════════════  # Major separator (step header)
────────────────────────────────  # Minor separator (sections)
┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈  # Dotted (execution marker)
╔════════════════════════════════  # Agent banner (top)
╚════════════════════════════════  # Agent banner (bottom)
```

### 6. ✅ **Resource Tracking**

Automatically extracts and displays AWS resources being created/modified:

```
📦 Resources:
  [
    "Name=sales_transactions_crawler",
    "DatabaseName=sales_transactions_db",
    "JobName=bronze_to_silver_job"
  ]
```

### 7. ✅ **Agent Performance Statistics**

At the end of each agent phase:

```
📊 Statistics:
  Total Operations   3
  Successful         3
  Failed             0
  Total Duration     15.45s

📦 Resources Created:
  ✓ Glue Crawler: sales_transactions_crawler
  ✓ Glue Database: sales_transactions_db
  ✓ SageMaker Catalog Metadata: sales_transactions_silver
```

### 8. ✅ **Final Summary with Breakdown**

```
⏱️  Overall Timing:
  Start Time:          2026-03-16 10:58:57
  End Time:            2026-03-16 11:02:34
  Total Elapsed:       3:37
  Total Operation Time: 215.67s

📊 Operations Summary:
  Total Steps:    12
  Success Rate:   100.0%

🤖 Agent Breakdown:
  Router Agent:
    Operations:     1
    Duration:       0.43s
    Success Rate:   100.0%

  Metadata Agent:
    Operations:     3
    Duration:       15.45s
    Success Rate:   100.0%

  Transformation Agent:
    Operations:     4
    Duration:       125.20s
    Success Rate:   100.0%

🔧 MCP Server Usage:
  aws-dataprocessing:
    Calls:          7
    Duration:       140.65s
    Avg per call:   20.09s

  sagemaker-catalog:
    Calls:          2
    Duration:       1.20s
    Avg per call:   0.60s
```

---

## Usage

### Basic Usage (Replace Old Orchestrator)

```python
# OLD
from shared.mcp.orchestrator import MCPOrchestrator
orch = MCPOrchestrator(workload_name="my_data")

# NEW - Enhanced
from shared.mcp.orchestrator_enhanced import EnhancedMCPOrchestrator, AgentType
orch = EnhancedMCPOrchestrator(workload_name="my_data")
```

### Agent-Aware Logging

```python
# Start an agent phase
orch.start_agent_phase(
    agent=AgentType.METADATA,
    phase="Phase 3: Schema Discovery"
)

# Execute operations with agent tracking
orch.call_mcp(
    step_name="Create Glue Crawler",
    agent=AgentType.METADATA,               # NEW: Agent parameter
    mcp_server="aws-dataprocessing",
    tool="create_crawler",
    params={...},
    description="Discover schema from S3",
    expected_duration=3.0                   # NEW: Expected time for perf tracking
)

# Complete agent phase with summary
orch.agent_summary(
    agent=AgentType.METADATA,
    summary="✓ Schema discovered\n✓ Metadata stored",
    resources_created=[                      # NEW: Track resources
        "Glue Crawler: my_crawler",
        "Glue Database: my_db"
    ]
)
```

### Complete Example

```python
from shared.mcp.orchestrator_enhanced import (
    EnhancedMCPOrchestrator,
    AgentType,
    OperationType
)

# Initialize
orch = EnhancedMCPOrchestrator(workload_name="customer_data")

# ─────────────────────────────────────────────────────────────
# PHASE 1: Router Agent
# ─────────────────────────────────────────────────────────────
orch.start_agent_phase(
    agent=AgentType.ROUTER,
    phase="Phase 1: Check Existing Workloads"
)

orch.call_mcp(
    step_name="Check for Duplicates",
    agent=AgentType.ROUTER,
    mcp_server="local-filesystem",
    tool="search_workloads_by_source",
    params={
        "source_type": "rds",
        "location_pattern": "customer"
    },
    description="Check if customer data already onboarded",
    expected_duration=1.0
)

orch.agent_summary(
    agent=AgentType.ROUTER,
    summary="✓ No duplicates found\n→ Proceeding to onboarding",
    resources_created=[]
)

# ─────────────────────────────────────────────────────────────
# PHASE 3: Metadata Agent
# ─────────────────────────────────────────────────────────────
orch.start_agent_phase(
    agent=AgentType.METADATA,
    phase="Phase 3: Schema Discovery & Profiling"
)

orch.call_mcp(
    step_name="Schema Discovery",
    agent=AgentType.METADATA,
    mcp_server="aws-dataprocessing",
    tool="create_crawler",
    params={
        "Name": "customer_crawler",
        "DatabaseName": "customer_db",
        "Role": "arn:aws:iam::123456789012:role/GlueCrawlerRole",
        "Targets": {
            "S3Targets": [{"Path": "s3://bronze/customers/"}]
        }
    },
    description="Discover schema from S3",
    expected_duration=3.0
)

orch.call_mcp(
    step_name="Profile Data Quality",
    agent=AgentType.METADATA,
    mcp_server="aws-dataprocessing",
    tool="start_query_execution",
    params={
        "QueryString": """
            SELECT
                COUNT(*) as total_rows,
                COUNT(DISTINCT customer_id) as unique_customers,
                COUNT(email) as email_count,
                SUM(CASE WHEN email IS NULL THEN 1 ELSE 0 END) as null_emails
            FROM customer_db.customers
            TABLESAMPLE BERNOULLI(5)
        """,
        "QueryExecutionContext": {"Database": "customer_db"}
    },
    description="Profile 5% sample for quality metrics",
    expected_duration=15.0
)

orch.call_mcp(
    step_name="Store Metadata",
    agent=AgentType.METADATA,
    mcp_server="sagemaker-catalog",
    tool="put_custom_metadata",
    params={
        "database": "customer_db",
        "table": "customers_silver",
        "custom_metadata": {
            "columns": {
                "customer_id": {"role": "identifier", "pii": False},
                "email": {"role": "identifier", "pii": True},
                "revenue": {"role": "measure", "default_aggregation": "sum"}
            }
        }
    },
    description="Store business metadata in SageMaker Catalog",
    expected_duration=1.0
)

orch.agent_summary(
    agent=AgentType.METADATA,
    summary="""
    ✓ Schema discovered via Glue Crawler
    ✓ Data profiled (5% sample): 50,000 rows, 48,523 unique customers
    ✓ Business metadata stored in SageMaker Catalog
    → Ready for transformation
    """,
    resources_created=[
        "Glue Crawler: customer_crawler",
        "Glue Database: customer_db",
        "SageMaker Catalog: customers_silver metadata"
    ]
)

# ─────────────────────────────────────────────────────────────
# PHASE 4: Transformation Agent
# ─────────────────────────────────────────────────────────────
orch.start_agent_phase(
    agent=AgentType.TRANSFORMATION,
    phase="Phase 4: Bronze → Silver → Gold Pipeline"
)

orch.call_mcp(
    step_name="Create Bronze→Silver ETL Job",
    agent=AgentType.TRANSFORMATION,
    mcp_server="aws-dataprocessing",
    tool="create_job",
    params={
        "Name": "customer_bronze_to_silver",
        "Role": "arn:aws:iam::123456789012:role/GlueETLRole",
        "Command": {
            "Name": "glueetl",
            "ScriptLocation": "s3://scripts/bronze_to_silver.py"
        }
    },
    description="Create Glue ETL job for cleaning and validation",
    expected_duration=2.0
)

orch.call_mcp(
    step_name="Create Silver Iceberg Table",
    agent=AgentType.TRANSFORMATION,
    mcp_server="s3-tables",
    tool="create_table",
    params={
        "name": "customers_silver",
        "namespace": "customer_db",
        "format": "ICEBERG"
    },
    description="Create Iceberg table for Silver zone",
    expected_duration=2.0
)

orch.agent_summary(
    agent=AgentType.TRANSFORMATION,
    summary="""
    ✓ Bronze→Silver ETL job created
    ✓ Silver Iceberg table created
    ✓ Transformation pipeline ready
    """,
    resources_created=[
        "Glue Job: customer_bronze_to_silver",
        "S3 Table: customers_silver (Iceberg)"
    ]
)

# ─────────────────────────────────────────────────────────────
# Final Summary
# ─────────────────────────────────────────────────────────────
orch.final_summary()
```

---

## Log Output Comparison

### OLD Orchestrator (Basic)

```
════════════════════════════════════════════════════════════════
STEP 1: Create Glue Crawler
────────────────────────────────────────────────────────────────
MCP Server:     aws-dataprocessing
Tool:           create_crawler
Input:          {...}
────────────────────────────────────────────────────────────────
Status:         ✓ SUCCESS
Output:         {...}
Duration:       2.3s
════════════════════════════════════════════════════════════════
```

**Issues**:
- ❌ No agent identification
- ❌ No operation type
- ❌ No resource tracking
- ❌ No timing breakdown
- ❌ No performance comparison
- ❌ No cumulative statistics

### NEW Enhanced Orchestrator

```
╔════════════════════════════════════════════════════════════════╗
║  AGENT: Metadata Agent          PHASE: Schema Discovery       ║
╚════════════════════════════════════════════════════════════════╝

════════════════════════════════════════════════════════════════
[10:58:57.987] STEP 1: Create Glue Crawler
Agent: Metadata Agent
────────────────────────────────────────────────────────────────

⚙️  Operation Type:   WRITE
📝 Description:        Discover schema from S3
🔧 MCP Server:         aws-dataprocessing
🛠️  Tool:             create_crawler
📦 Resources:          [Name=customer_crawler, DatabaseName=customer_db]
⏱️  Expected Duration: ~3.0s

  📥 Input Parameters:
    {...}

┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
⚡ Executing at 10:58:57.999...

────────────────────────────────────────────────────────────────

🎯 Status:            ✅ ✓ SUCCESS

  📤 Output:
    {
      "CrawlerName": "customer_crawler",
      "Status": "CREATED",
      "Arn": "arn:aws:glue:us-east-1:123456789012:crawler/customer_crawler"
    }

⏱️  Timing Details:
  {
    "Start": "10:58:57.986",
    "End": "10:58:58.160",
    "Duration": "0.174s"
  }
🚀 Performance:       Faster than expected (0.17s vs 3.00s)
════════════════════════════════════════════════════════════════
```

**Benefits**:
- ✅ Clear agent identification
- ✅ Operation type classification
- ✅ Resource tracking
- ✅ Detailed timing with start/end
- ✅ Performance comparison
- ✅ Better visual separation
- ✅ Precise timestamps

---

## JSON Log Structure (Enhanced)

```json
{
  "workload": "customer_data",
  "start_time": "2026-03-16T10:58:57.123456",
  "end_time": "2026-03-16T11:02:34.654321",
  "total_duration_seconds": 217.53,
  "total_steps": 12,
  "statistics": {
    "operations_per_agent": {
      "Router Agent": {
        "total_operations": 1,
        "successful": 1,
        "failed": 0,
        "total_duration": 0.43
      },
      "Metadata Agent": {
        "total_operations": 3,
        "successful": 3,
        "failed": 0,
        "total_duration": 15.45
      },
      "Transformation Agent": {
        "total_operations": 4,
        "successful": 4,
        "failed": 0,
        "total_duration": 125.20
      }
    },
    "mcp_server_usage": {
      "aws-dataprocessing": {
        "call_count": 7,
        "total_duration": 140.65,
        "operations": [
          "create_crawler",
          "start_query_execution",
          "create_job",
          ...
        ]
      },
      "sagemaker-catalog": {
        "call_count": 2,
        "total_duration": 1.20,
        "operations": ["put_custom_metadata", "get_custom_metadata"]
      }
    },
    "success_rate": 100.0
  },
  "steps": [
    {
      "step_number": 1,
      "step_name": "Check for Duplicates",
      "agent": "Router Agent",
      "description": "Check if customer data already onboarded",
      "mcp_server": "local-filesystem",
      "tool": "search_workloads_by_source",
      "operation_type": "READ",
      "resources": [],
      "params": {...},
      "result": {...},
      "status": "✓ SUCCESS",
      "error": null,
      "timing": {
        "start": "2026-03-16T10:58:57.123456",
        "end": "2026-03-16T10:58:57.554321",
        "duration_seconds": 0.430,
        "expected_duration": 1.0
      }
    },
    ...
  ]
}
```

---

## Migration from Old to Enhanced

### Step 1: Update Import

```python
# OLD
from shared.mcp.orchestrator import MCPOrchestrator

# NEW
from shared.mcp.orchestrator_enhanced import (
    EnhancedMCPOrchestrator,
    AgentType
)
```

### Step 2: Add Agent Parameter

```python
# OLD
orch.call_mcp(
    step_name="Create Crawler",
    mcp_server="aws-dataprocessing",
    tool="create_crawler",
    params={...}
)

# NEW - Add agent parameter
orch.call_mcp(
    step_name="Create Crawler",
    agent=AgentType.METADATA,           # ADD THIS
    mcp_server="aws-dataprocessing",
    tool="create_crawler",
    params={...},
    expected_duration=3.0                # OPTIONAL: Add expected time
)
```

### Step 3: Add Phase Banners

```python
# NEW - Add at start of each agent phase
orch.start_agent_phase(
    agent=AgentType.METADATA,
    phase="Phase 3: Schema Discovery"
)

# ... operations ...

# NEW - Add at end of each agent phase
orch.agent_summary(
    agent=AgentType.METADATA,
    summary="✓ Schema discovered\n✓ Metadata stored",
    resources_created=[
        "Glue Crawler: my_crawler",
        "Glue Database: my_db"
    ]
)
```

### Step 4: Add Final Summary

```python
# NEW - Add at end of workflow
orch.final_summary()
```

---

## Performance Tracking

The enhanced orchestrator tracks performance vs expectations:

```python
orch.call_mcp(
    step_name="Profile Data",
    agent=AgentType.METADATA,
    mcp_server="aws-dataprocessing",
    tool="start_query_execution",
    params={...},
    expected_duration=15.0  # Expected: 15 seconds
)
```

**If faster than expected**:
```
🚀 Performance: Faster than expected (12.3s vs 15.0s)
```

**If slower than expected**:
```
🐌 Performance: Slower than expected (18.7s vs 15.0s)
```

This helps identify:
- ✅ Operations that need optimization
- ✅ Unrealistic expectations
- ✅ Performance regressions
- ✅ Infrastructure issues

---

## Best Practices

### 1. Always Specify Agent

```python
# GOOD
orch.call_mcp(..., agent=AgentType.METADATA, ...)

# BAD (won't work with enhanced orchestrator)
orch.call_mcp(..., mcp_server="...", ...)  # Missing agent parameter
```

### 2. Use Phase Banners for Clarity

```python
# Start of each major phase
orch.start_agent_phase(AgentType.TRANSFORMATION, "Phase 4: Pipeline Build")
# ... operations ...
orch.agent_summary(AgentType.TRANSFORMATION, "✓ Pipeline created")
```

### 3. Track Resources Created

```python
orch.agent_summary(
    agent=AgentType.TRANSFORMATION,
    summary="...",
    resources_created=[
        "Glue Job: my_job",
        "S3 Table: my_table",
        "Lambda: my_function"
    ]
)
```

### 4. Set Realistic Expected Durations

```python
# Profiling on large datasets
expected_duration=30.0  # 30 seconds

# Simple metadata operations
expected_duration=1.0   # 1 second

# ETL job creation
expected_duration=2.0   # 2 seconds
```

### 5. Review Final Summary

Always call `orch.final_summary()` at the end to get:
- Overall timing
- Success rate per agent
- MCP server usage statistics
- Performance insights

---

## Troubleshooting

### Issue: Missing Agent Parameter Error

**Error**: `TypeError: call_mcp() missing 1 required positional argument: 'agent'`

**Solution**: Add agent parameter to all `call_mcp()` calls:
```python
orch.call_mcp(..., agent=AgentType.METADATA, ...)
```

### Issue: Performance Always Shows as Faster

**Cause**: `expected_duration` not set or set too high

**Solution**: Set realistic expectations based on operation type:
- Read operations: 0.5-2s
- Write operations: 1-5s
- Execute operations: 5-30s (depending on job)

### Issue: Resources Not Showing

**Cause**: Resource identifiers not in standard parameter keys

**Solution**: Use standard keys in params:
- `Name`, `DatabaseName`, `TableName`, `JobName`, etc.
- Or add custom keys to `_extract_resources()` method

---

## Next Steps

1. ✅ Use enhanced orchestrator in all new workflows
2. ✅ Migrate existing workflows gradually
3. ✅ Set realistic expected durations
4. ✅ Review agent summaries for optimization opportunities
5. ✅ Use final summary statistics for capacity planning
