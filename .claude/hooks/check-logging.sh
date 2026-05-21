#!/bin/bash
# Logging Gate — ensures StructuredLogger, logs/, and decisions array
INPUT=$(cat)

FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[ -z "$FILE" ] && exit 0

# Normalize to relative path
FILE=$(echo "$FILE" | sed "s|$(pwd)/||")

# --- Check 1: ETL scripts must import StructuredLogger ---
if echo "$FILE" | grep -qE '^workloads/[^/]+/scripts/(transform|quality|extract|load)/.*\.py$'; then
  # Only check on Write (full content) — skip Edit (partial changes)
  if echo "$INPUT" | jq -e '.tool_input.content' >/dev/null 2>&1; then
    CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')
    if ! echo "$CONTENT" | grep -q "StructuredLogger\|structured_logger\|ScriptTracer\|script_tracer"; then
      jq -n --arg file "$FILE" '{
        "hookSpecificOutput": {
          "hookEventName": "PreToolUse",
          "permissionDecision": "deny",
          "permissionDecisionReason": ("BLOCKED: " + $file + " is an ETL script but does not import StructuredLogger. All ETL scripts MUST use shared.utils.structured_logger for structured log output. Add: from shared.utils.structured_logger import StructuredLogger")
        }
      }'
      exit 0
    fi
  fi
fi

# --- Check 2: Workload must have logs/ directory before DAG creation ---
if echo "$FILE" | grep -qE '^workloads/[^/]+/dags/.*\.py$'; then
  WORKLOAD=$(echo "$FILE" | sed 's|workloads/||' | cut -d/ -f1)

  if [ ! -d "workloads/${WORKLOAD}/logs" ]; then
    jq -n --arg wl "$WORKLOAD" '{
      "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": ("BLOCKED: workloads/" + $wl + "/logs/ directory does not exist. Every workload MUST have a logs/ directory for trace_events.jsonl and run traces. Create it before writing the DAG.")
      }
    }'
    exit 0
  fi
fi

# --- Check 3: Agent tool spawns must include decisions requirement ---
# Skip config/rules files — they're allowed to mention Agent( without decisions
if echo "$FILE" | grep -qE '^(SKILLS|CLAUDE)\.md$|^\.claude/'; then
  exit 0
fi

# For any file that contains Agent( spawn calls — check for decisions
if echo "$INPUT" | jq -e '.tool_input.content' >/dev/null 2>&1; then
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')
  if echo "$CONTENT" | grep -q "Agent("; then
    if ! echo "$CONTENT" | grep -q "decisions"; then
      jq -n '{
        "hookSpecificOutput": {
          "hookEventName": "PreToolUse",
          "permissionDecision": "deny",
          "permissionDecisionReason": "BLOCKED: File contains Agent() spawn but does not mention decisions array requirement. Every sub-agent MUST include a decisions array in its AgentOutput. Add decisions requirement to the spawn prompt."
        }
      }'
      exit 0
    fi
  fi
fi

# Allow everything else
exit 0
