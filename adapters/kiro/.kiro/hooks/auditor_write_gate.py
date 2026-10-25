#!/usr/bin/env python3
"""Restrict requirements-auditor writes to its three append/report outputs."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping


ALLOWED_SUFFIXES = (
    "/run/requirements_audit.json",
    "/run/decisions.jsonl",
    "/logs/trace_events.jsonl",
)


def _paths(tool_input: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            values.append(value)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, Mapping):
                value = edit.get("file_path") or edit.get("path")
                if isinstance(value, str):
                    values.append(value)
    return values


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, Mapping):
        payload = {}
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, Mapping) else {}
    actor = (
        os.environ.get("ADOP_AGENT_NAME")
        or payload.get("agent_name")
        or tool_input.get("agent_name")
        or ""
    )
    if str(actor).lower().replace("_", "-") != "requirements-auditor":
        print("{}")
        return
    paths = _paths(tool_input)
    disallowed = [
        path
        for path in paths
        if not any(path.replace("\\", "/").endswith(suffix) for suffix in ALLOWED_SUFFIXES)
    ]
    if disallowed:
        reason = (
            "BLOCKED: requirements-auditor may write only run/requirements_audit.json, "
            "run/decisions.jsonl, or logs/trace_events.jsonl; attempted: "
            + ", ".join(disallowed)
        )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }
            )
        )
        return
    print("{}")


if __name__ == "__main__":
    main()
