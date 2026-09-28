#!/bin/bash
# ADOP hook launcher for Kiro.
#
# Solves two incompatibilities between Claude Code and Kiro:
#
#  1. PATH RESOLUTION. Claude Code hooks use ${CLAUDE_PLUGIN_ROOT} to locate bundled
#     scripts. Kiro documents no bundle-root variable and does not path-resolve hook
#     commands. This script locates the bundle from its OWN path, so it works whether
#     Kiro invokes it relatively or absolutely, from any cwd.
#
#  2. BLOCK CONTRACT. Claude Code signals a block with JSON on STDOUT + exit 0:
#       {"hookSpecificOutput":{"permissionDecision":"deny","permissionDecisionReason":"..."}}
#       {"decision":"block","reason":"..."}                      (PostToolUse form)
#     Kiro signals a block with EXIT CODE 2 and the reason on STDERR, and ignores that
#     JSON entirely. Ported verbatim, every gate would exit 0 and Kiro would allow the
#     write -- the gate would silently stop working.
#
# Usage: adop-hook.sh <script-name-in-hooks-dir>
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
HOOK="$HOOK_DIR/${1:-}"

if [ -z "${1:-}" ] || [ ! -f "$HOOK" ]; then
  echo "adop-hook: cannot locate hook '${1:-<none>}' under $HOOK_DIR" >&2
  exit 0   # fail open: never wedge the user's session on a launcher bug
fi

INPUT=$(cat)

# 3. KEY NORMALISATION. Measured from a live Kiro IDE PreToolUse payload:
#      {"tool_name":"fs_write","tool_input":{"path":"/abs/path","text":"..."}}
#    The upstream hooks were written against Claude Code's names:
#      file_path / content / new_string
#    block_credentials reads content|new_string only, so given Kiro's "text" it saw
#    empty content and allowed writes carrying credentials -- exit 0, no complaint.
#    Normalise additively here rather than editing the vendored scripts, so upstream
#    stays cheap to re-sync and one change covers every hook.
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

# 4. CONTEXT-INJECTION TRANSLATION. Claude Code returns session context as
#    {"hookSpecificOutput":{"additionalContext":"..."}} on stdout. Kiro's SessionStart and
#    UserPromptSubmit contract is simpler: exit 0 and whatever is on STDOUT is added to the
#    agent's context. So unwrap the field and emit it as plain text, or the agent receives a
#    JSON blob it has to interpret instead of usable context.
if command -v jq >/dev/null 2>&1; then
  CTX=$(printf '%s' "$OUT" | jq -r '.hookSpecificOutput.additionalContext // .additionalContext // empty' 2>/dev/null)
  if [ -n "$CTX" ]; then
    printf '%s\n' "$CTX"
    exit 0
  fi
fi

# Translate both Claude Code block dialects into Kiro's.
if printf '%s' "$OUT" | grep -qE '"(permissionDecision"[[:space:]]*:[[:space:]]*"deny|decision"[[:space:]]*:[[:space:]]*"block)"'; then
  REASON=$(printf '%s' "$OUT" | jq -r '.hookSpecificOutput.permissionDecisionReason // .reason // empty' 2>/dev/null)
  [ -z "$REASON" ] && REASON="Blocked by ADOP policy gate."
  printf '%s\n' "$REASON" >&2
  exit 2
fi

exit 0
