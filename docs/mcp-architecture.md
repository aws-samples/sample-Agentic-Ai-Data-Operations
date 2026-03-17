# MCP Server Architecture

**Understanding Where MCP Servers Live and How They Work**

---

## Quick Answer

**MCP servers are LOCAL Python/Node.js scripts that run on YOUR machine.**

They are NOT:
- ❌ Hosted on AWS
- ❌ Hosted by Anthropic
- ❌ Web services with URLs
- ❌ Remote APIs

They ARE:
- ✅ Local processes spawned by Claude Code
- ✅ Communicate via stdin/stdout (pipes)
- ✅ Use YOUR AWS credentials
- ✅ Run only when Claude Code is running

---

## File Locations

### 1. MCP Server Registry

**File:** `~/.mcp.json`

**Purpose:** Tells Claude Code which MCP servers to load when it starts.

**Content:**
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

**How it works:**
- Claude Code reads this file on startup
- For each entry, it spawns the specified command as a subprocess
- The subprocess runs `python3 server.py`
- Claude Code communicates with it via stdin/stdout

---

### 2. Custom MCP Server (PII Detection)

**Location:**
```
/path/to/claude-data-operations/mcp-servers/pii-detection-server/
├── server.py (19KB)                          # Main MCP server
├── README.md (10KB)                          # Documentation
├── setup.sh (3.4KB)                          # Setup script
└── pii_detection_and_tagging.py (symlink)    # → ../../shared/utils/
```

**Type:** Local Python script (MCP protocol implementation)

**Protocol:** MCP 2024-11-05 (JSON-RPC over stdio)

**When it runs:**
- Started automatically when Claude Code launches
- Runs as a background process
- Stopped automatically when Claude Code exits

**What it does:**
- Listens for JSON-RPC messages on stdin
- Executes PII detection logic
- Calls AWS APIs (Glue, Athena, Lake Formation)
- Returns results via stdout

---

### 3. Shared Detection Logic

**Location:**
```
/path/to/claude-data-operations/shared/utils/pii_detection_and_tagging.py
```

**Purpose:** The actual PII detection implementation (imported by the MCP server)

**Why separate?**
- Can be used standalone (without MCP)
- Can be imported by multiple tools
- Easier to test and maintain

---

### 4. AWS MCP Servers (Pre-installed)

**Servers:** iam, lambda, redshift, cloudtrail, etc.

**Location:** Managed by Claude Code (internal node_modules/)

**Type:** NPM packages from `@modelcontextprotocol/server-aws-*`

**Configuration:** Not in your project, configured in Claude Code settings

**How they work:**
- Claude Code downloads them from npm automatically
- Spawns them as local processes
- Uses your AWS credentials from `~/.aws/credentials`

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                       YOUR LOCAL MACHINE                         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ CLAUDE CODE (Client Process)                              │ │
│  │                                                            │ │
│  │  1. Reads ~/.mcp.json on startup                          │ │
│  │  2. Spawns MCP server subprocesses                        │ │
│  │  3. Communicates via stdin/stdout (JSON-RPC)              │ │
│  │  4. Translates your natural language → MCP tool calls     │ │
│  └────────┬───────────────────────────────────────────────────┘ │
│           │ spawns & manages                                    │
│           ▼                                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ MCP SERVER SUBPROCESSES (Running in background)           │ │
│  │                                                            │ │
│  │ ┌──────────────────────────────────────────────────────┐  │ │
│  │ │ PII Detection Server (Custom)                        │  │ │
│  │ │ Process: python3 server.py                           │  │ │
│  │ │ Location: mcp-servers/pii-detection-server/          │  │ │
│  │ │ Tools: 6 (detect_pii_in_table, scan_database, etc.) │  │ │
│  │ │ Uses: shared/utils/pii_detection_and_tagging.py      │  │ │
│  │ └──────────────────────────────────────────────────────┘  │ │
│  │                                                            │ │
│  │ ┌──────────────────────────────────────────────────────┐  │ │
│  │ │ IAM Server (AWS)                                     │  │ │
│  │ │ Process: npx @modelcontextprotocol/server-aws-iam    │  │ │
│  │ │ Tools: 20+ (create_user, attach_policy, etc.)       │  │ │
│  │ └──────────────────────────────────────────────────────┘  │ │
│  │                                                            │ │
│  │ ┌──────────────────────────────────────────────────────┐  │ │
│  │ │ Lambda Server (AWS)                                  │  │ │
│  │ │ Process: npx @modelcontextprotocol/server-aws-lambda │  │ │
│  │ │ Tools: 10+ (invoke, list_functions, etc.)           │  │ │
│  │ └──────────────────────────────────────────────────────┘  │ │
│  │                                                            │ │
│  │ ┌──────────────────────────────────────────────────────┐  │ │
│  │ │ Redshift Server (AWS)                                │  │ │
│  │ │ Process: npx @modelcontextprotocol/server-aws-redshift│ │ │
│  │ │ Tools: 6 (execute_query, list_clusters, etc.)       │  │ │
│  │ └──────────────────────────────────────────────────────┘  │ │
│  │                                                            │ │
│  └────────┬──────────────────────────────────────────────────┘ │
│           │ uses credentials                                    │
│           ▼                                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ AWS CREDENTIALS                                            │ │
│  │ Location: ~/.aws/credentials                               │ │
│  │ Profile: [default] or specified profile                    │ │
│  └────────┬──────────────────────────────────────────────────┘ │
└───────────┼────────────────────────────────────────────────────┘
            │ network calls (HTTPS)
            ▼
┌──────────────────────────────────────────────────────────────────┐
│                         AWS CLOUD                                │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐   │
│  │ Lake Formation │  │      IAM       │  │    Lambda      │   │
│  └────────────────┘  └────────────────┘  └────────────────┘   │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐   │
│  │     Glue       │  │    Athena      │  │   Redshift     │   │
│  └────────────────┘  └────────────────┘  └────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Communication Flow

### Example: "Detect PII in finsights_silver.funds_clean"

```
STEP 1: User types command
─────────────────────────────
You: "Detect PII in finsights_silver.funds_clean"

STEP 2: Claude Code processes natural language
───────────────────────────────────────────────
Claude Code:
  • Understands intent: PII detection
  • Identifies MCP tool: detect_pii_in_table
  • Extracts parameters: database=finsights_silver, table=funds_clean
  • Prepares JSON-RPC message

STEP 3: Claude Code → PII Detection Server (via stdin)
───────────────────────────────────────────────────────
stdin → {
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "detect_pii_in_table",
    "arguments": {
      "database": "finsights_silver",
      "table": "funds_clean",
      "content_detection": true,
      "apply_tags": true
    }
  }
}

STEP 4: PII Detection Server executes
──────────────────────────────────────
server.py:
  • Receives JSON-RPC on stdin
  • Calls async execute_tool("detect_pii_in_table", args)
  • Imports shared/utils/pii_detection_and_tagging.py
  • Calls AWS Glue: get_table() → schema
  • Calls AWS Athena: sample 100 rows → data
  • Analyzes column names (name-based detection)
  • Analyzes data values (content-based detection)
  • Calls AWS Lake Formation: add_lf_tags_to_resource()

STEP 5: PII Detection Server → Claude Code (via stdout)
────────────────────────────────────────────────────────
stdout → {
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{
      "type": "text",
      "text": "{
        \"database\": \"finsights_silver\",
        \"table\": \"funds_clean\",
        \"pii_detected\": true,
        \"pii_columns\": 1,
        \"columns\": {
          \"fund_name\": {
            \"pii_types\": [\"NAME\"],
            \"sensitivity\": \"MEDIUM\",
            \"confidence_scores\": {\"NAME\": 1.0}
          }
        }
      }"
    }]
  }
}

STEP 6: Claude Code presents result to you
───────────────────────────────────────────
Claude Code:
  "I detected 1 PII column:
    • fund_name → NAME (MEDIUM sensitivity)

  Sample values:
    - 'Vanguard Total Stock Market Index Fund'
    - 'Fidelity Growth Company Fund'

  These look like fund product names, not personal names.
  Confirm this is NOT PII?"
```

---

## Why This Architecture?

### Advantages of Local MCP Servers

| Benefit | Explanation |
|---------|-------------|
| **Zero Latency** | No network calls between Claude Code and MCP server (same machine) |
| **Secure** | No credentials sent over network, uses local AWS credentials |
| **Free** | No hosting costs, no cloud infrastructure |
| **Simple** | Just copy files, no deployment process |
| **Offline-capable** | MCP logic runs locally, only AWS calls go over network |
| **Easy to debug** | Can run `python3 server.py` manually to test |
| **No firewall config** | Uses stdio pipes, not network ports |

### Comparison to Remote APIs

```
TRADITIONAL API ARCHITECTURE:
─────────────────────────────
Your Machine → HTTP → Remote Server → AWS
  • Network latency: 50-200ms
  • Requires hosting ($)
  • Firewall/security configuration
  • API keys to manage
  • Server maintenance

MCP ARCHITECTURE:
─────────────────
Your Machine (local process) → AWS
  • Local latency: <1ms
  • Free (no hosting)
  • No firewall needed
  • Uses local AWS creds
  • No server to maintain
```

---

## Lifecycle Management

### When Servers Start
- Claude Code launches → reads `~/.mcp.json`
- For each server: spawns subprocess with specified command
- Servers initialize and wait for JSON-RPC messages
- Takes ~1-2 seconds total

### While Running
- Servers run as background processes
- Idle (waiting on stdin) when not in use
- Respond instantly when called
- No manual management needed

### When Servers Stop
- Claude Code exits → all MCP server subprocesses terminate
- Servers are ephemeral (no persistent state)
- Next Claude Code launch = fresh servers

### No Manual Management Required
✅ Claude Code handles start/stop automatically
✅ No `systemctl`, no `pm2`, no service managers
✅ No port conflicts (doesn't use network ports)
✅ No process monitoring needed

---

## Testing MCP Servers

### Test Manually (Without Claude Code)

```bash
# Test PII Detection server directly
cd /path/to/claude-data-operations/mcp-servers/pii-detection-server

# Send initialize message
echo '{"method":"initialize","params":{}}' | python3 server.py

# Expected output:
# {"protocolVersion":"2024-11-05","serverInfo":{"name":"pii-detection-server","version":"1.0.0"},...}

# List available tools
echo '{"method":"tools/list","params":{}}' | python3 server.py

# Expected output:
# {"tools":[{"name":"detect_pii_in_table",...},{...}]}
```

### Test Through Claude Code

After restart:
```
"List available MCP tools"
→ Claude shows all loaded tools

"Detect PII in finsights_silver.funds_clean"
→ Invokes detect_pii_in_table tool
```

---

## Troubleshooting

### Issue: MCP Server Not Loading

**Symptom:** Claude Code says "Tool not available" or doesn't list your tool

**Check:**
1. `~/.mcp.json` exists and is valid JSON
   ```bash
   cat ~/.mcp.json | python3 -m json.tool
   ```

2. Server path is correct
   ```bash
   # Should show the server.py file
   ls -l /path/to/claude-data-operations/mcp-servers/pii-detection-server/server.py
   ```

3. Server is executable
   ```bash
   python3 /path/to/claude-data-operations/mcp-servers/pii-detection-server/server.py
   # Should wait for input (not error)
   ```

4. Restart Claude Code (required after changing `~/.mcp.json`)

### Issue: Server Starts But Tool Fails

**Symptom:** Tool is listed but errors when called

**Check:**
1. AWS credentials are configured
   ```bash
   aws sts get-caller-identity
   ```

2. Required permissions exist
   ```bash
   aws glue get-table --database-name finsights_silver --name funds_clean
   ```

3. Symlink is valid
   ```bash
   ls -L /path/to/claude-data-operations/mcp-servers/pii-detection-server/pii_detection_and_tagging.py
   ```

4. Python dependencies installed
   ```bash
   python3 -c "import boto3; print('boto3 OK')"
   ```

### Issue: Server Process Not Terminating

**Symptom:** `ps aux | grep server.py` shows orphaned processes

**Solution:**
```bash
# Kill orphaned MCP servers
pkill -f "server.py"

# Or specific server
kill $(ps aux | grep "pii-detection-server/server.py" | grep -v grep | awk '{print $2}')
```

---

## Creating More Custom MCP Servers

### Template Structure

```
mcp-servers/
└── my-new-server/
    ├── server.py           # MCP protocol implementation
    ├── README.md           # Documentation
    ├── setup.sh            # Setup script
    └── requirements.txt    # Python dependencies
```

### Minimal server.py

```python
#!/usr/bin/env python3
import json
import sys
import asyncio

class MCPServer:
    def __init__(self):
        self.tools = {
            'my_tool': {
                'description': 'Does something useful',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'param1': {'type': 'string'}
                    },
                    'required': ['param1']
                }
            }
        }

    async def handle_message(self, message):
        method = message.get('method')
        if method == 'initialize':
            return {
                'protocolVersion': '2024-11-05',
                'serverInfo': {'name': 'my-server', 'version': '1.0.0'},
                'capabilities': {'tools': {}}
            }
        elif method == 'tools/list':
            return {'tools': [
                {
                    'name': name,
                    'description': tool['description'],
                    'inputSchema': tool['inputSchema']
                }
                for name, tool in self.tools.items()
            ]}
        elif method == 'tools/call':
            tool_name = message['params']['name']
            arguments = message['params']['arguments']
            result = await self.execute_tool(tool_name, arguments)
            return {'content': [{'type': 'text', 'text': json.dumps(result)}]}

    async def execute_tool(self, tool_name, arguments):
        # Your tool logic here
        return {'result': 'success', 'data': arguments}

    async def run(self):
        while True:
            line = await asyncio.get_event_loop().run_in_executor(
                None, sys.stdin.readline
            )
            if not line:
                break
            message = json.loads(line)
            response = await self.handle_message(message)
            print(json.dumps(response), flush=True)

if __name__ == '__main__':
    server = MCPServer()
    asyncio.run(server.run())
```

### Register in ~/.mcp.json

```json
{
  "mcpServers": {
    "my-new-server": {
      "command": "python3",
      "args": ["/path/to/my-new-server/server.py"],
      "env": {}
    }
  }
}
```

---

## Summary

**MCP servers are:**
- ✅ Local Python/Node.js scripts on your machine
- ✅ Spawned automatically by Claude Code
- ✅ Communicate via stdin/stdout (not HTTP)
- ✅ Use your local AWS credentials
- ✅ Ephemeral (exist only while Claude Code runs)

**Not:**
- ❌ Hosted in the cloud
- ❌ Remote APIs with URLs
- ❌ Persistent services
- ❌ Managed infrastructure

**Key files:**
- `~/.mcp.json` → Server registry
- `mcp-servers/pii-detection-server/` → Custom server code
- `shared/utils/pii_detection_and_tagging.py` → Detection logic

**To use:**
1. Add server to `~/.mcp.json`
2. Restart Claude Code
3. Use natural language to invoke tools

No hosting, no deployment, no infrastructure management. Just local processes that Claude Code manages for you.
