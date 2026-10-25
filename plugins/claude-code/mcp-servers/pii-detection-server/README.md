# PII Detection MCP Server

**Custom MCP Server for AI-Powered PII Detection and Lake Formation Tagging**

---

## Overview

This MCP server enables Claude Code to detect PII in your data lake and automatically apply Lake Formation Tags (LF-Tags) for governance and access control.

### Key Features

- **AI-Powered PII Detection**: Claude analyzes data and identifies PII patterns
- **Automated LF-Tag Application**: Applies tags to columns in Lake Formation
- **Tag-Based Access Control**: Enable fine-grained column-level security
- **Natural Language Interface**: Use plain English to manage PII governance

---

## Architecture

```
Claude Code (AI Agent)
    ↓
PII Detection MCP Server
    ↓
├── PII Detection Logic (Python)
├── Lake Formation Client (boto3)
└── Athena Client (content sampling)
    ↓
AWS Lake Formation
    └── LF-Tags on Columns
```

### Agent-Driven Approach

**1. AI Detection:**
- Claude analyzes column names, descriptions, and sample data
- Identifies PII types (EMAIL, PHONE, SSN, etc.)
- Determines sensitivity levels (CRITICAL, HIGH, MEDIUM, LOW)

**2. Automated Tagging:**
- MCP server applies LF-Tags to identified columns
- Tags: `PII_Classification`, `PII_Type`, `Data_Sensitivity`

**3. Access Control:**
- Lake Formation uses tags for permissions
- Principals get access based on sensitivity levels

---

## Installation

### Quick Setup

```bash
cd /path/to/claude-data-operations/mcp-servers/pii-detection-server
chmod +x setup.sh
./setup.sh
```

### Manual Setup

1. **Link PII Detection Script:**
```bash
ln -s ../../workloads/us_mutual_funds_etf/scripts/governance/pii_detection_and_tagging.py \
  pii_detection_and_tagging.py
```

2. **Make Server Executable:**
```bash
chmod +x server.py
```

3. **Add to MCP Configuration:**

Create or edit `~/.mcp.json`:

```json
{
  "mcpServers": {
    "pii-detection": {
      "command": "python3",
      "args": [
        "/path/to/claude-data-operations/mcp-servers/pii-detection-server/server.py"
      ],
      "env": {
        "AWS_REGION": "us-east-1",
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

4. **Restart Claude Code:**

The MCP server will be loaded automatically.

---

## Usage

### From Claude Code (Natural Language)

**Detect PII in a table:**
```
Detect PII in the finsights_silver.funds_clean table and apply LF-Tags
```

**Scan entire database:**
```
Scan all tables in finsights_gold database for PII
```

**Get PII report:**
```
Generate a PII report for finsights_silver database
```

**Apply tag-based security:**
```
Grant demo-role access to columns with LOW and MEDIUM PII sensitivity
```

**List PII columns:**
```
Show me all CRITICAL PII columns in finsights_gold.customer_data table
```

---

## Available Tools

### 1. detect_pii_in_table

Detect PII in a specific table.

**Parameters:**
- `database` (required): Glue database name
- `table` (required): Table name
- `content_detection` (optional): Enable content sampling (default: true)
- `apply_tags` (optional): Apply LF-Tags (default: true)

**Example:**
```json
{
  "database": "finsights_silver",
  "table": "customer_data",
  "content_detection": true,
  "apply_tags": true
}
```

**Response:**
```json
{
  "database": "finsights_silver",
  "table": "customer_data",
  "pii_detected": true,
  "pii_columns": 3,
  "columns": {
    "email": {
      "pii_types": ["EMAIL"],
      "sensitivity": "HIGH",
      "confidence_scores": {"EMAIL": 100.0}
    },
    "phone": {
      "pii_types": ["PHONE"],
      "sensitivity": "MEDIUM",
      "confidence_scores": {"PHONE": 100.0}
    },
    "ssn": {
      "pii_types": ["SSN"],
      "sensitivity": "CRITICAL",
      "confidence_scores": {"SSN": 95.0}
    }
  }
}
```

---

### 2. scan_database_for_pii

Scan all tables in a database.

**Parameters:**
- `database` (required): Glue database name
- `content_detection` (optional): Enable content sampling (default: false)
- `apply_tags` (optional): Apply LF-Tags (default: true)

**Example:**
```json
{
  "database": "finsights_gold",
  "content_detection": false,
  "apply_tags": true
}
```

---

### 3. create_lf_tags

Create Lake Formation tags for PII classification.

**Parameters:**
- `force_recreate` (optional): Recreate tags if they exist (default: false)

**Tags Created:**
- `PII_Classification`: CRITICAL, HIGH, MEDIUM, LOW, NONE
- `PII_Type`: EMAIL, PHONE, SSN, CREDIT_CARD, NAME, etc.
- `Data_Sensitivity`: CRITICAL, HIGH, MEDIUM, LOW

---

### 4. get_pii_columns

Get list of columns tagged with PII.

**Parameters:**
- `database` (required): Glue database name
- `table` (required): Table name
- `sensitivity_level` (optional): Filter by sensitivity

**Example:**
```json
{
  "database": "finsights_gold",
  "table": "customer_data",
  "sensitivity_level": "CRITICAL"
}
```

---

### 5. apply_column_security

Apply tag-based access control.

**Parameters:**
- `principal_arn` (required): IAM principal ARN
- `sensitivity_levels` (required): Array of allowed sensitivity levels
- `database` (optional): Specific database

**Example:**
```json
{
  "principal_arn": "arn:aws:iam::123456789012:role/AnalystRole",
  "sensitivity_levels": ["LOW", "MEDIUM"]
}
```

This grants the AnalystRole SELECT permissions on all columns tagged with LOW or MEDIUM sensitivity.

---

### 6. get_pii_report

Generate PII report for a database or table.

**Parameters:**
- `database` (required): Glue database name
- `table` (optional): Specific table
- `format` (optional): Output format (json | summary)

**Example:**
```json
{
  "database": "finsights_silver",
  "format": "summary"
}
```

**Response:**
```json
{
  "database": "finsights_silver",
  "tables_with_pii": 3,
  "summary": {
    "critical": 2,
    "high": 5,
    "medium": 3,
    "low": 1
  }
}
```

---

## Agent-Driven PII Detection

### How It Works

**1. Claude Analyzes Data:**
- Reads table schema (column names, types)
- Optionally samples data content
- Applies PII detection patterns
- Assigns sensitivity levels

**2. Agent Invokes MCP Tools:**
- `detect_pii_in_table` for specific tables
- `scan_database_for_pii` for entire databases
- `apply_column_security` for access control

**3. Lake Formation Enforcement:**
- LF-Tags applied to columns
- Tag-based policies control access
- Audit trail maintained

### Example Workflow

**User Prompt:**
```
Analyze the finsights_silver database and protect any PII columns by tagging them appropriately. Then grant analysts access to only non-sensitive data.
```

**Claude's Actions:**
1. Calls `scan_database_for_pii` on finsights_silver
2. Reviews results and confirms PII types
3. Calls `apply_tags=true` to tag columns
4. Calls `apply_column_security` for analyst role with LOW sensitivity

---

## Integration with Data Pipeline

### Option 1: Add to Airflow DAG

```python
from airflow.operators.python import PythonOperator
import subprocess

def run_pii_detection_via_mcp(**context):
    """Use MCP server to detect PII"""
    # This would be called by Claude Code
    # For Airflow, use the Python script directly
    cmd = [
        'python3',
        'scripts/governance/pii_detection_and_tagging.py',
        '--database', 'finsights_silver',
        '--all-tables'
    ]
    subprocess.run(cmd, check=True)

pii_task = PythonOperator(
    task_id='pii_detection',
    python_callable=run_pii_detection_via_mcp,
    dag=dag
)
```

### Option 2: Invoke via Claude Code

In Claude Code, after data loads:
```
The silver zone data load is complete. Please scan all tables for PII and apply appropriate tags.
```

Claude will use the MCP server to automatically detect and tag PII.

---

## Testing

### Test MCP Server

```bash
# Test initialize
echo '{"method":"initialize","params":{}}' | python3 server.py

# Test tools list
echo '{"method":"tools/list","params":{}}' | python3 server.py

# Test PII detection
echo '{"method":"tools/call","params":{"name":"detect_pii_in_table","arguments":{"database":"finsights_silver","table":"funds_clean","content_detection":false,"apply_tags":false}}}' | python3 server.py
```

### Test from Claude Code

After setup, test with:
```
Test the PII detection MCP server by listing available tools
```

---

## Troubleshooting

### Issue: MCP server not loading

**Check:**
1. `~/.mcp.json` exists and is valid JSON
2. Server path is correct
3. `server.py` is executable (`chmod +x`)
4. Restart Claude Code

**Verify:**
```bash
python3 server.py
# Should wait for input (server is running)
```

### Issue: ImportError for pii_detection_and_tagging

**Solution:**
```bash
cd /path/to/mcp-servers/pii-detection-server
ln -s ../../workloads/us_mutual_funds_etf/scripts/governance/pii_detection_and_tagging.py .
```

### Issue: AWS permissions error

**Required IAM permissions:**
- `glue:GetTable`, `glue:GetTables`
- `athena:StartQueryExecution`, `athena:GetQueryResults`
- `lakeformation:CreateLFTag`, `lakeformation:AddLFTagsToResource`
- `s3:GetObject`, `s3:PutObject` (for Athena results)

---

## Security Considerations

### IAM Permissions

The MCP server runs with your AWS credentials. Ensure:
- Least privilege access
- No overly broad permissions
- Audit trail enabled (CloudTrail)

### PII Detection Accuracy

- **Name-based detection**: 100% confidence but limited coverage
- **Content-based detection**: Higher coverage but may have false positives
- **Review before production**: Always review detected PII before applying tags

### Tag-Based Access Control

- Test permissions before granting to production roles
- Use `SELECT` only (not `INSERT`, `UPDATE`, `DELETE`)
- Monitor access with CloudTrail logs

---

## Comparison: MCP vs Direct Script

| Feature | MCP Server | Direct Script |
|---------|-----------|---------------|
| **Integration** | Claude Code native | Command-line |
| **Natural Language** | ✅ Yes | ❌ No |
| **AI-Driven** | ✅ Claude analyzes | ⚠️  Pattern-based |
| **Flexibility** | ✅ High | ⚠️  Medium |
| **Setup** | ⚠️  Requires config | ✅ Immediate |
| **Best For** | Interactive use | Automation/CI |

**Recommendation:**
- Use MCP server for interactive data governance in Claude Code
- Use direct script for automated pipeline integration

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| **PII_DETECTION_AND_TAGGING.md** | Python script documentation |
| **MCP_PII_TAGGING_SOLUTION.md** | Lambda + MCP alternative |
| **README.md** | This document |

---

**MCP Server Version:** 1.0.0
**Protocol:** MCP 2024-11-05
**Created:** March 17, 2026
**Status:** ✅ Ready for use
