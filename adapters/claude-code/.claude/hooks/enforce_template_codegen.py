#!/usr/bin/env python3
"""
PreToolUse hook: blocks Write/Edit/MultiEdit to workloads/*/scripts/**, dags/**, sql/**
unless the ADOP_RENDERER_TOKEN env var is set (meaning the renderer is writing).

Exit codes:
  0 = allow (silent)
  2 = block (prints reason to stderr, outputs hookSpecificOutput JSON)
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROTECTED_PATTERN = re.compile(
    r"workloads/[^/]+/(scripts|dags|sql)/"
)

TOKEN_ENV = "ADOP_RENDERER_TOKEN"

HOOK_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "hook_blocks.jsonl"


def extract_file_paths(event: dict) -> list[str]:
    """Extract target file paths from the tool input."""
    tool_input = event.get("tool_input", {})
    paths = []

    # Write and Edit have file_path
    if "file_path" in tool_input:
        paths.append(tool_input["file_path"])

    # MultiEdit has edits array
    if "edits" in tool_input:
        for edit in tool_input["edits"]:
            if "file_path" in edit:
                paths.append(edit["file_path"])

    return paths


def is_protected_path(file_path: str) -> bool:
    """Check if the path matches the protected artifact directories."""
    return bool(PROTECTED_PATTERN.search(file_path))


def log_block(file_path: str, reason: str) -> None:
    """Append block event to hook_blocks.jsonl."""
    try:
        HOOK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
            "cwd": os.getcwd(),
            "attempted_path": file_path,
            "reason": reason,
        }
        with open(HOOK_LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, IOError):
        return 0

    file_paths = extract_file_paths(event)
    if not file_paths:
        return 0

    token = os.environ.get(TOKEN_ENV, "")

    for file_path in file_paths:
        if is_protected_path(file_path) and not token:
            reason = (
                f"Direct write to '{file_path}' is blocked. "
                f"Artifacts under workloads/*/scripts/, dags/, sql/ must be produced "
                f"by shared.codegen.renderer.render(). "
                f"Modify the spec config and re-render instead."
            )
            print(json.dumps({
                "hookSpecificOutput": {
                    "permissionDecision": "deny",
                    "reason": reason,
                }
            }))
            print(reason, file=sys.stderr)
            log_block(file_path, reason)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
