#!/bin/bash
# Phase 1 Discovery Gate (Amazon Q Developer CLI preToolUse hook)
# Blocks pipeline file creation if discovery is not complete.
#
# Ported from .claude/hooks/check-discovery-gate.sh. The block MECHANISM changed:
# the Claude Code original printed a `hookSpecificOutput` JSON blob on STDOUT and
# exited 0. Q Developer CLI ignores hook STDOUT and blocks only on exit code 2 +
# STDERR, so the block path is rebuilt as `echo >&2; exit 2`. Gate LOGIC is
# unchanged.
#
# Wire per-agent, matcher "fs_write":
#   "preToolUse": [{ "matcher": "fs_write",
#                    "command": ".amazonq/hooks/check-discovery-gate.sh" }]
#
# Tool-input shape: reads the write target from top-level .tool_input.path,
# falling back to an operations[] array and the legacy .file_path. Validate
# against the running CLI and prune once fs_write's schema is confirmed.
INPUT=$(cat)

FILE=$(echo "$INPUT" | jq -r '.tool_input.path // .tool_input.operations[0].path // .tool_input.file_path // empty')
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
    echo "BLOCKED: Phase 1 discovery not complete for workload \"${WORKLOAD}\". You MUST ask the user about: (1) source details, (2) PK + PII columns, (3) cleaning/transformation rules, (4) quality thresholds, (5) schedule. After user confirms all 5, create workloads/${WORKLOAD}/.discovery_complete to proceed." >&2
    exit 2
  fi
fi

# Allow everything else
exit 0
