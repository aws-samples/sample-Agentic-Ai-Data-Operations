#!/usr/bin/env python3
"""PreToolUse hook: enforce the Cedar policies in shared/policies/.

Byte-identical in .claude/hooks, .codex/hooks and .kiro/hooks (and the adapter
copies); `scripts/sync_platforms.py check` enforces that. All logic lives in
shared/utils/cedar_gate.py; this file only finds it and a Python that has
cedarpy.

Usage: cedar_gate.py [--principal <cedar-principal-id>]
  Claude Code and Codex: no argument; the principal comes from `agent_type`.
  Kiro: each agent's own hook passes its principal (Kiro sends no agent_type).

Fails closed: if the engine cannot be located or run, the call is denied.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Tools that never produce a Cedar request (reads, search, planning). Skipping
# them keeps the hook off the hot path for most calls.
_NEVER_GOVERNED = {
    "read", "glob", "grep", "ls", "todowrite", "todoread", "webfetch", "websearch",
    "fs_read", "fsread", "readfile", "fs_list", "list_directory", "listdirectory",
    "grep_search", "file_search", "grepsearch", "filesearch", "view_image",
    "update_plan", "knowledge", "web_fetch", "web_search", "toolsearch",
}


def _deny(reason: str) -> int:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    print(reason, file=sys.stderr)
    return 2


def _root(event: dict) -> Path | None:
    for start in (Path(event.get("cwd") or os.getcwd()), Path(__file__).resolve()):
        for candidate in (start.resolve(), *start.resolve().parents):
            if (candidate / "shared" / "utils" / "cedar_gate.py").is_file():
                return candidate
    return None


def main() -> int:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return _deny("Cedar gate received an unparseable hook payload.")
    tool = str(event.get("tool_name") or event.get("toolName") or "").strip().lower()
    if tool in _NEVER_GOVERNED:
        return 0

    root = _root(event)
    if root is None:
        return _deny("Cedar gate cannot locate shared/utils/cedar_gate.py; denying.")
    engine = root / "shared" / "utils" / "cedar_gate.py"

    # Prefer an interpreter that has cedarpy: this one, else the repo venv.
    python = sys.executable
    try:
        import cedarpy  # noqa: F401
    except ImportError:
        venv = root / ".venv" / "bin" / "python"
        if venv.is_file():
            python = str(venv)
    try:
        completed = subprocess.run([python, str(engine), *sys.argv[1:]], input=raw,
                                   text=True, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return _deny(f"Cedar gate could not run: {exc}")
    if completed.returncode == 0:
        return 0
    if completed.returncode == 2:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        return 2
    return _deny(f"Cedar gate crashed (exit {completed.returncode}): "
                 f"{(completed.stderr or completed.stdout).strip()[-400:]}")


if __name__ == "__main__":
    raise SystemExit(main())
