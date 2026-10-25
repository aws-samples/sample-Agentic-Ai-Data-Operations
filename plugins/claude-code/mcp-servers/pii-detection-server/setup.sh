#!/bin/bash
#
# Setup script for PII Detection MCP Server
#

set -e

echo "=================================================="
echo "PII Detection MCP Server Setup"
echo "=================================================="
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Script directory: $SCRIPT_DIR"
echo "Project root: $PROJECT_ROOT"
echo ""

# Step 1: Link PII detection script
echo "Step 1: Linking PII detection script..."
if [ ! -f "$SCRIPT_DIR/pii_detection_and_tagging.py" ]; then
  ln -s "$PROJECT_ROOT/workloads/us_mutual_funds_etf/scripts/governance/pii_detection_and_tagging.py" "$SCRIPT_DIR/pii_detection_and_tagging.py"
  echo "✓ Linked pii_detection_and_tagging.py"
else
  echo "✓ pii_detection_and_tagging.py already exists"
fi
echo ""

# Step 2: Make server executable
echo "Step 2: Making server executable..."
chmod +x "$SCRIPT_DIR/server.py"
echo "✓ server.py is now executable"
echo ""

# Step 3: Test server
echo "Step 3: Testing server..."
echo '{"method":"initialize","params":{}}' | python3 "$SCRIPT_DIR/server.py" | head -1
if [ $? -eq 0 ]; then
  echo "✓ Server responds to initialize"
else
  echo "✗ Server test failed"
  exit 1
fi
echo ""

# Step 4: Create MCP configuration
echo "Step 4: Creating MCP configuration..."

MCP_CONFIG_FILE="$HOME/.mcp.json"
TEMP_CONFIG="/tmp/mcp-config-$$.json"

# Check if .mcp.json exists
if [ -f "$MCP_CONFIG_FILE" ]; then
  echo "Found existing $MCP_CONFIG_FILE"

  # Backup existing config
  cp "$MCP_CONFIG_FILE" "${MCP_CONFIG_FILE}.backup-$(date +%Y%m%d-%H%M%S)"
  echo "✓ Backed up existing config"

  # Add pii-detection server to existing config
  python3 << EOF
import json

with open('$MCP_CONFIG_FILE', 'r') as f:
    config = json.load(f)

if 'mcpServers' not in config:
    config['mcpServers'] = {}

config['mcpServers']['pii-detection'] = {
    'command': 'python3',
    'args': ['$SCRIPT_DIR/server.py'],
    'env': {
        'AWS_REGION': 'us-east-1',
        'PYTHONUNBUFFERED': '1'
    }
}

with open('$TEMP_CONFIG', 'w') as f:
    json.dump(config, f, indent=2)

print('✓ Updated MCP configuration')
EOF

  mv "$TEMP_CONFIG" "$MCP_CONFIG_FILE"

else
  echo "Creating new $MCP_CONFIG_FILE"

  cat > "$MCP_CONFIG_FILE" << EOF
{
  "mcpServers": {
    "pii-detection": {
      "command": "python3",
      "args": ["$SCRIPT_DIR/server.py"],
      "env": {
        "AWS_REGION": "us-east-1",
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
EOF

  echo "✓ Created new MCP configuration"
fi

echo ""
echo "MCP configuration:"
cat "$MCP_CONFIG_FILE" | python3 -m json.tool
echo ""

# Step 5: Instructions
echo "=================================================="
echo "Setup Complete!"
echo "=================================================="
echo ""
echo "The PII Detection MCP Server has been configured."
echo ""
echo "To use it in Claude Code:"
echo "  1. Restart Claude Code (to load new MCP server)"
echo "  2. Use natural language prompts like:"
echo "     - 'Detect PII in finsights_silver.funds_clean'"
echo "     - 'Scan all tables in finsights_gold for PII'"
echo "     - 'Get PII report for finsights_silver database'"
echo ""
echo "Available tools:"
echo "  - detect_pii_in_table"
echo "  - scan_database_for_pii"
echo "  - create_lf_tags"
echo "  - get_pii_columns"
echo "  - apply_column_security"
echo "  - get_pii_report"
echo ""
echo "Configuration file: $MCP_CONFIG_FILE"
echo ""
