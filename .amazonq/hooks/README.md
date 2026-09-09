# .amazonq/hooks — ADOP hooks ported to Amazon Q Developer CLI

Phase 2 of the ADOP → Amazon Q Developer CLI migration (see
`ADOP-to-AmazonQ-Migration-Design.md`, Sections 5.2 and 5.4). These are the four
Claude Code hooks, ported. Logic is preserved; the **block/output mechanism** and
the **wiring model** changed.

## What changed from the Claude Code originals

| Hook | Trigger (was → now) | Block mechanism (was → now) | Other change |
|---|---|---|---|
| `enforce_template_codegen.py` | PreToolUse `Write\|Edit\|MultiEdit` → `preToolUse` matcher `fs_write` | `hookSpecificOutput` JSON **+** stderr + exit 2 → **stderr + exit 2 only** (JSON dropped) | Session env var `CLAUDE_SESSION_ID` → `ADOP_SESSION_ID` |
| `check-discovery-gate.sh` | PreToolUse `Edit\|Write` → `preToolUse` matcher `fs_write` | `hookSpecificOutput` JSON + **exit 0** → **stderr + exit 2** (block path rebuilt — the original never used exit 2) | — |
| `check-logging.sh` | PreToolUse `Edit\|Write` → `preToolUse` matcher `fs_write` | same rebuild as above | Check 4 scans for `q chat --agent` (external spawn) in addition to the legacy `Agent(`; exclusion list adds `AmazonQ.md` and `.amazonq/` |
| `log_conversation.py` | PostToolUse `AskUserQuestion` → `postToolUse` matcher `fs_write` | passive (exit 0) — unchanged | Re-anchored to the `.discovery_complete` marker write; full Q&A capture now comes from `AgentTracer.log_exchange()` (see `rules/00-zone-questions.md`) |

## Wiring — per agent (this is the key structural difference)

Claude Code wired all four hooks **once**, globally, in `.claude/settings.json`.
Amazon Q Developer CLI has **no global hook file** — hooks live in each agent's
`cli-agents/*.json` under a `hooks` field. So the three `preToolUse` gates must be
attached to **every agent that can write files** (the orchestrator plus every
build sub-agent). Miss one agent and that agent bypasses a BLOCK-severity
guardrail silently. The `cli-agents/*.json` profiles are built in **Phase 3**;
paste this block into each write-capable agent then:

```json
{
  "hooks": {
    "preToolUse": [
      { "matcher": "fs_write", "command": ".amazonq/hooks/check-discovery-gate.sh", "timeout_ms": 5000 },
      { "matcher": "fs_write", "command": ".amazonq/hooks/check-logging.sh", "timeout_ms": 5000 },
      { "matcher": "fs_write", "command": "python3 .amazonq/hooks/enforce_template_codegen.py", "timeout_ms": 5000 }
    ],
    "postToolUse": [
      { "matcher": "fs_write", "command": "python3 .amazonq/hooks/log_conversation.py", "timeout_ms": 3000 }
    ]
  }
}
```

Read-only sub-agents (no `fs_write` in their `tools` array) don't need the
`preToolUse` gates, but attaching them is harmless (they no-op when no path
matches).

## Assumptions to validate against the running CLI

1. **`fs_write` tool_input shape.** Public docs pin `fs_read` (`operations[].path`)
   but not the full `fs_write` input. Every script extracts the target path
   defensively: top-level `.tool_input.path`, then `operations[].path`, then the
   legacy `.file_path`; content from `.tool_input.file_text`, then `new_str`, then
   `content`. Confirm the real keys once and prune the fallbacks.
2. **Fail-open on unparseable input.** If stdin isn't valid JSON, every hook
   exits 0 (allow). This matches the Claude Code originals exactly — it is
   preserved behavior, not new risk — but note that these are security gates that
   fail open, so keep the input contract stable.

## Verification

All four hooks were smoke-tested against simulated `preToolUse`/`postToolUse`
events: protected-path block vs. token/allow, discovery-gate block vs. marker/
existing-workload allow, all three `check-logging` checks, the `q chat --agent`
spawn detection, `.discovery_complete` milestone logging, and fail-open on
malformed JSON. `python3 -m py_compile` and `bash -n` both pass.
