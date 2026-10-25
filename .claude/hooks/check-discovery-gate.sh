#!/bin/bash
# Phase 1 Discovery Gate — blocks pipeline file creation if discovery not complete
INPUT=$(cat)

FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[ -z "$FILE" ] && exit 0

# Normalize to relative path
FILE=$(echo "$FILE" | sed "s|$(pwd)/||")

# Only gate pipeline artifacts in workloads/
if echo "$FILE" | grep -qE '^workloads/[^/]+/(config|scripts|dags|sql)/'; then
  WORKLOAD=$(echo "$FILE" | sed 's|workloads/||' | cut -d/ -f1)

  # Skip gate for existing workloads (already have source.yaml = already discovered)
  if [ -f "workloads/${WORKLOAD}/config/source.yaml" ]; then
    exit 0
  fi

  # For new workloads: check discovery marker
  if [ ! -f "workloads/${WORKLOAD}/.discovery_complete" ]; then
    jq -n --arg wl "$WORKLOAD" '{
      "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": ("BLOCKED: Phase 1 discovery not complete for workload \"" + $wl + "\". The user MUST be asked about: (1) source details, (2) PK + PII columns, (3) cleaning/transformation rules, (4) quality thresholds, (5) schedule. The ORCHESTRATOR asks those questions and then creates workloads/" + $wl + "/.discovery_complete. If you are a sub-agent you cannot satisfy this gate — you have no AskUserQuestion tool, so you cannot have asked. Do NOT create the marker to unblock yourself; return status \"blocked\" naming this gate in blocking_issues.")
      }
    }'
    exit 0
  fi
fi

# Allow everything else
exit 0
