# MCP Server Setup Guide

**How to configure MCP servers for this project**

---

## Prerequisites

- Claude Code or compatible MCP client
- Python 3.9+
- AWS credentials configured (`~/.aws/credentials`)
- `uvx` installed for AWS MCP servers

---

## Configuration File

Copy `.mcp.json.example` to `~/.mcp.json` (or your Claude Code MCP config location):

```bash
cp .mcp.json.example ~/.mcp.json
```

**Edit the file** and replace placeholders:

```json
{
  "mcpServers": {
    "pii-detection": {
      "command": "python3",
      "args": [
        "/absolute/path/to/mcp-servers/pii-detection-server/server.py"
      ],
      "env": {
        "AWS_REGION": "us-east-1",
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

**Replace `/absolute/path/to/` with the actual path to this repository.**

Example:
```
/Users/yourname/Documents/Claude-data-operations/mcp-servers/pii-detection-server/server.py
```

---

## Available MCP Servers

### 1. PII Detection (Custom)

**Path**: `mcp-servers/pii-detection-server/server.py`
**Tools**: 6 (detect_pii_in_table, scan_database_for_pii, etc.)
**Usage**: PII detection and Lake Formation tagging

### 2. IAM (AWS)

**Install**: `uvx awslabs.iam-mcp-server@latest`
**Tools**: IAM role/policy management
**Usage**: Permission verification, least-privilege checks

### 3. Redshift (AWS)

**Install**: `uvx awslabs.redshift-mcp-server@latest`
**Tools**: Query execution, schema discovery
**Usage**: Data validation, Gold zone queries

### 4. CloudTrail (AWS)

**Install**: `uvx awslabs.cloudtrail-mcp-server@latest`
**Tools**: Event lookup, audit queries
**Usage**: Security auditing, compliance

### 5. Lambda (AWS)

**Install**: `uvx awslabs.lambda-mcp-server@latest`
**Tools**: Lambda function invocation
**Usage**: Lake Formation grants via Lambda

---

## Testing MCP Servers

### Test Individual Server

```bash
# Test PII detection server
echo '{"method":"tools/list"}' | python3 mcp-servers/pii-detection-server/server.py

# Test IAM server (if installed)
uvx awslabs.iam-mcp-server@latest --help
```

### Test in Claude Code

After configuring `~/.mcp.json`:

1. Restart Claude Code
2. Ask: "What MCP tools are available?"
3. Try: "List IAM roles in my AWS account"

---

## Troubleshooting

### Server not loading

**Check:**
```bash
# Verify config file
cat ~/.mcp.json | jq .

# Verify Python path
which python3

# Test server manually
python3 mcp-servers/pii-detection-server/server.py
```

### AWS permissions error

**Required IAM permissions:**
- `glue:GetTable`, `glue:GetTables`
- `lakeformation:CreateLFTag`, `lakeformation:AddLFTagsToResource`
- `iam:ListRoles`, `iam:SimulatePrincipalPolicy`
- `redshift:DescribeClusters`, `redshift-data:ExecuteStatement`
- `cloudtrail:LookupEvents`

---

## Security Notes

⚠️ **IMPORTANT**: The `.mcp.json` file contains local file paths and should NOT be committed to Git.

✅ Instead, use `.mcp.json.example` as a template and add `.mcp.json` to `.gitignore`.

---

## Documentation

- **Full Test Report**: `PII_DETECTION_TEST_REPORT.md`
- **Usage Examples**: `MCP_PII_USAGE_EXAMPLES.md`
- **Server README**: `mcp-servers/pii-detection-server/README.md`

---

**Last Updated**: March 17, 2026
