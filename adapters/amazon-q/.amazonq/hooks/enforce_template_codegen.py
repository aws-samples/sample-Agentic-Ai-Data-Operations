#!/usr/bin/env python3
"""
preToolUse hook (Amazon Q Developer CLI): blocks fs_write to
workloads/*/scripts/**, dags/**, sql/** unless the ADOP_RENDERER_TOKEN env var
is set (meaning the deterministic renderer is doing the write).

Ported from .claude/hooks/enforce_template_codegen.py. Logic is unchanged; only
the OUTPUT layer differs from the Claude Code original:
  - Claude Code emitted a `hookSpecificOutput` JSON blob on STDOUT *and* exit 2.
  - Q Developer CLI reads only exit code 2 + STDERR (STDOUT on a hook is captured
    but never shown/acted on). The JSON blob is therefore removed.

Wire this per-agent on every agent that can write files (orchestrator + build
sub-agents), matcher "fs_write":
  "preToolUse": [{ "matcher": "fs_write",
                   "command": "python3 .amazonq/hooks/enforce_template_codegen.py",
                   "timeout_ms": 5000 }]

Exit codes:
  0 = allow (silent)
  2 = block (reason to STDERR, returned to the LLM)

Tool-input shape assumption: Q Developer CLI's fs_write parameters are not fully
pinned in public docs. extract_file_paths() reads the target path from every
shape observed across fs_read/fs_write (top-level `path`, an `operations[].path`
array, and the legacy `file_path`/`edits[].file_path`). Validate against the
running CLI and prune once the exact schema is confirmed.
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
    """Extract target file paths from the tool input across known shapes."""
    tool_input = event.get("tool_input", {})
    paths = []

    # Q Developer CLI fs_write: single top-level path
    if isinstance(tool_input.get("path"), str):
        paths.append(tool_input["path"])

    # fs_read-style operations array (defensive; some tools batch paths)
    for op in tool_input.get("operations", []) or []:
        if isinstance(op, dict) and "path" in op:
            paths.append(op["path"])

    # Legacy Claude Code shapes (Write/Edit/MultiEdit)
    if "file_path" in tool_input:
        paths.append(tool_input["file_path"])
    for edit in tool_input.get("edits", []) or []:
        if isinstance(edit, dict) and "file_path" in edit:
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
            "session_id": os.environ.get("ADOP_SESSION_ID", "unknown"),
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
            # Q Developer CLI contract: STDERR + exit 2 is the entire block signal.
            print(reason, file=sys.stderr)
            log_block(file_path, reason)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
