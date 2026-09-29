#!/bin/bash
# ADOP hook launcher for Kiro.
#
# The gate scripts under this directory are shared with the other ADOP editions, so they read
# and write a slightly different hook contract than Kiro uses. This launcher sits in front of
# them and adapts both directions. Everything below is what that adaptation involves.
#
#  1. PATH RESOLUTION. Kiro does not path-resolve hook commands and documents no bundle-root
#     variable, so this script locates its own directory from ${BASH_SOURCE[0]} and finds the
#     gates relative to that. Works whether Kiro invokes it relatively or absolutely, from any
#     working directory.
#
#  2. BLOCK CONTRACT. Kiro blocks a tool call when a hook exits 2, and shows the reason from
#     STDERR. The gate scripts instead print a JSON decision on STDOUT and exit 0:
#       {"hookSpecificOutput":{"permissionDecision":"deny","permissionDecisionReason":"..."}}
#       {"decision":"block","reason":"..."}
#     Kiro ignores that JSON. Without translation every gate would exit 0, Kiro would allow the
#     write, and the gate would silently stop working while appearing healthy.
#
# Usage: adop-hook.sh <script-name-in-this-directory>
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
HOOK="$HOOK_DIR/${1:-}"

if [ -z "${1:-}" ] || [ ! -f "$HOOK" ]; then
  echo "adop-hook: cannot locate hook '${1:-<none>}' under $HOOK_DIR" >&2
  exit 0   # fail open: never wedge the user's session on a launcher bug
fi

INPUT=$(cat)

# 3. KEY NORMALISATION. A live Kiro PreToolUse payload looks like:
#      {"tool_name":"fs_write","tool_input":{"path":"/abs/path","text":"..."}}
#    The gate scripts expect file_path / content / new_string. This is not cosmetic: the
#    credentials gate reads content|new_string, so given only "text" it saw an empty body and
#    allowed writes carrying AWS keys -- exit 0, no complaint, no sign anything was wrong.
#    Keys are added here rather than renamed in the scripts, so the shared implementation stays
#    shared and one change covers every gate.
if command -v jq >/dev/null 2>&1; then
  NORM=$(printf '%s' "$INPUT" | jq -c '
    if (.tool_input | type) == "object" then
      .tool_input |= (
          (if (has("content") | not) and has("text")        then .content    = .text    else . end)
        | (if (has("file_path") | not) and has("path")      then .file_path  = .path    else . end)
        | (if (has("new_string") | not) and has("new_str")  then .new_string = .new_str else . end)
      )
    else . end' 2>/dev/null)
  [ -n "$NORM" ] && INPUT="$NORM"
else
  echo "adop-hook: jq not found; payload not normalised, gates may not inspect content" >&2
fi

OUT=$(printf '%s' "$INPUT" | python3 "$HOOK" 2>/dev/null)
RC=$?

# Upstream already speaks Kiro's dialect (enforce_template_codegen.py): pass it through.
if [ "$RC" -eq 2 ]; then
  printf '%s' "$OUT" >&2
  exit 2
fi

# 4. CONTEXT INJECTION. For SessionStart and UserPromptSubmit, Kiro adds whatever a hook
#    prints on STDOUT to the agent's context. The run-context hook instead returns it wrapped as
#    {"hookSpecificOutput":{"additionalContext":"..."}}. Unwrap it, or the agent receives a JSON
#    blob to interpret instead of usable context.
if command -v jq >/dev/null 2>&1; then
  CTX=$(printf '%s' "$OUT" | jq -r '.hookSpecificOutput.additionalContext // .additionalContext // empty' 2>/dev/null)
  if [ -n "$CTX" ]; then
    printf '%s\n' "$CTX"
    exit 0
  fi
fi

# Translate either JSON decision form into Kiro's exit-2 + STDERR contract.
if printf '%s' "$OUT" | grep -qE '"(permissionDecision"[[:space:]]*:[[:space:]]*"deny|decision"[[:space:]]*:[[:space:]]*"block)"'; then
  REASON=$(printf '%s' "$OUT" | jq -r '.hookSpecificOutput.permissionDecisionReason // .reason // empty' 2>/dev/null)
  [ -z "$REASON" ] && REASON="Blocked by ADOP policy gate."
  printf '%s\n' "$REASON" >&2
  exit 2
fi

exit 0
