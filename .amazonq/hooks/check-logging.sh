#!/bin/bash
# Logging Gate (Amazon Q Developer CLI preToolUse hook)
# Ensures StructuredLogger, logs/, and the decisions-array requirement.
#
# Ported from .claude/hooks/check-logging.sh. The block MECHANISM changed from
# `hookSpecificOutput` JSON on STDOUT + exit 0 to STDERR + exit 2 (Q Developer
# CLI's only block contract). Check LOGIC is unchanged EXCEPT Check 4:
#   - Claude Code spawned sub-agents in-model via an `Agent(` tool call, so the
#     hook scanned written content for the literal string "Agent(".
#   - On Q Developer CLI, spawning is EXTERNAL: the orchestrator shells out via
#     execute_bash to `q chat --agent <name> --no-interactive ...`. Check 4 now
#     scans for that invocation pattern instead. The PURPOSE (require a decisions
#     array documented near a spawn call site) is unchanged.
#
# Wire per-agent, matcher "fs_write":
#   "preToolUse": [{ "matcher": "fs_write",
#                    "command": ".amazonq/hooks/check-logging.sh" }]
#
# Tool-input shape: reads path from .tool_input.path (fallback operations[]/
# file_path) and content from .tool_input.file_text (fallback new_str/content).
# Validate against the running CLI and prune once fs_write's schema is confirmed.
INPUT=$(cat)

FILE=$(echo "$INPUT" | jq -r '.tool_input.path // .tool_input.operations[0].path // .tool_input.file_path // empty')
[ -z "$FILE" ] && exit 0

# Normalize to relative path
FILE=$(echo "$FILE" | sed "s|$(pwd)/||")

# Helper: pull written content from the known fs_write shapes
get_content() {
  echo "$INPUT" | jq -r '.tool_input.file_text // .tool_input.new_str // .tool_input.content // empty'
}
has_content() {
  echo "$INPUT" | jq -e '.tool_input.file_text // .tool_input.new_str // .tool_input.content' >/dev/null 2>&1
}

# --- Check 1: ETL scripts must import StructuredLogger ---
if echo "$FILE" | grep -qE '^workloads/[^/]+/scripts/(transform|quality|extract|load)/.*\.py$'; then
  if has_content; then
    CONTENT=$(get_content)
    if ! echo "$CONTENT" | grep -q "StructuredLogger\|structured_logger\|ScriptTracer\|script_tracer"; then
      echo "BLOCKED: ${FILE} is an ETL script but does not import StructuredLogger. All ETL scripts MUST use shared.utils.structured_logger for structured log output. Add: from shared.utils.structured_logger import StructuredLogger" >&2
      exit 2
    fi
  fi
fi

# --- Check 2: Workload must have logs/ directory before DAG creation ---
if echo "$FILE" | grep -qE '^workloads/[^/]+/dags/.*\.py$'; then
  WORKLOAD=$(echo "$FILE" | sed 's|workloads/||' | cut -d/ -f1)

  if [ ! -d "workloads/${WORKLOAD}/logs" ]; then
    echo "BLOCKED: workloads/${WORKLOAD}/logs/ directory does not exist. Every workload MUST have a logs/ directory for trace_events.jsonl and run traces. Create it before writing the DAG." >&2
    exit 2
  fi
fi

# --- Check 3: Block post-deploy artifacts until trace_events.jsonl exists ---
if echo "$FILE" | grep -qE '^workloads/[^/]+/README\.md$'; then
  WORKLOAD=$(echo "$FILE" | sed 's|workloads/||' | cut -d/ -f1)

  if [ -d "workloads/${WORKLOAD}/logs" ] && [ ! -f "workloads/${WORKLOAD}/logs/trace_events.jsonl" ]; then
    echo "BLOCKED: workloads/${WORKLOAD}/logs/trace_events.jsonl does not exist. Every workflow run MUST produce a structured trace before post-deployment steps. Write the trace log first." >&2
    exit 2
  fi
fi

# --- Check 4: Sub-agent spawns must include the decisions requirement ---
# Skip docs/config/rules files — they may reference spawn patterns without decisions.
if echo "$FILE" | grep -qE '^(SKILLS|CLAUDE|AmazonQ)\.md$|^\.claude/|^\.amazonq/'; then
  exit 0
fi

# For any file that spawns a sub-agent — check for the decisions requirement.
# On Q Developer CLI, spawning is `q chat --agent <name> ...` (via execute_bash);
# the legacy in-model "Agent(" call is also matched for backward compatibility.
if has_content; then
  CONTENT=$(get_content)
  if echo "$CONTENT" | grep -qE 'q chat --agent|q chat -a |Agent\('; then
    if ! echo "$CONTENT" | grep -q "decisions"; then
      echo "BLOCKED: File spawns a sub-agent (q chat --agent / Agent()) but does not mention the decisions array requirement. Every sub-agent MUST include a decisions array in its AgentOutput. Add the decisions requirement to the spawn prompt." >&2
      exit 2
    fi
  fi
fi

# Allow everything else
exit 0
