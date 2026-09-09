#!/usr/bin/env python3
"""postToolUse hook (Amazon Q Developer CLI): logs discovery-gate completion.

Ported from .claude/hooks/log_conversation.py. The TRIGGER changed:
  - The Claude Code original fired on postToolUse of the `AskUserQuestion` tool
    and logged each structured question/answer pair. That tool does not exist on
    Q Developer CLI — discovery questions are now plain free-text Q&A, which no
    tool hook can observe as structured data.
  - Per migration design Section 5.4, this hook re-anchors to the fs_write that
    creates a workload's `.discovery_complete` marker, and logs a
    `discovery_complete` milestone event. FULL per-question Q&A capture now comes
    from the orchestrator's own `AgentTracer.log_exchange()` calls (see
    .amazonq/rules/00-zone-questions.md), not from this hook.

Wire per-agent, matcher "fs_write":
  "postToolUse": [{ "matcher": "fs_write",
                    "command": "python3 .amazonq/hooks/log_conversation.py",
                    "timeout_ms": 3000 }]

Always exits 0 (passive; postToolUse cannot block and the tool has already run).

Tool-input shape: reads the written path from .tool_input.path (fallback
operations[]/file_path). Validate against the running CLI and prune once
fs_write's schema is confirmed.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


TRACE_LOG_DIR = Path("logs")
HOOK_LOG_PATH = TRACE_LOG_DIR / "conversation_events.jsonl"

MARKER_SUFFIX = ".discovery_complete"


def _detect_workload_from_path(path: str) -> str:
    """Prefer the workload inferred from the marker path; fall back to env."""
    # .../workloads/<name>/.discovery_complete
    parts = Path(path).parts
    if "workloads" in parts:
        i = parts.index("workloads")
        if i + 1 < len(parts):
            return parts[i + 1]
    return os.environ.get("ADOP_WORKLOAD", "unknown")


def _detect_phase() -> "int | None":
    phase = os.environ.get("ADOP_PHASE")
    return int(phase) if phase else None


def _generate_thread_id() -> str:
    import uuid
    return f"thr-{uuid.uuid4().hex[:8]}"


def _extract_path(tool_input: dict) -> str:
    if isinstance(tool_input.get("path"), str):
        return tool_input["path"]
    for op in tool_input.get("operations", []) or []:
        if isinstance(op, dict) and "path" in op:
            return op["path"]
    if "file_path" in tool_input:
        return tool_input["file_path"]
    return ""


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, IOError):
        return 0

    if event.get("tool_name") != "fs_write":
        return 0

    tool_input = event.get("tool_input", {})
    path = _extract_path(tool_input)
    if not path.endswith(MARKER_SUFFIX):
        return 0

    workload = _detect_workload_from_path(path)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workload_name": workload,
        "phase": _detect_phase(),
        "thread_id": _generate_thread_id(),
        "surface": "contextual",
        "event_type": "discovery_complete",
        "agent_name": "orchestrator",
        "payload": {
            "marker_path": path,
            "note": "Phase 1 discovery gate marked complete. Per-question Q&A is "
                    "captured separately via AgentTracer.log_exchange().",
        },
    }

    try:
        HOOK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(HOOK_LOG_PATH, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
