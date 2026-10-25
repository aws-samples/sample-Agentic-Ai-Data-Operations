#!/usr/bin/env python3
"""Enforce workload logging prerequisites before DAG creation."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from patch_paths import patch_targets, relative_path


DAG_PATH = re.compile(r"^workloads/([^/]+)/dags/.*\.py$")


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        return 0

    cwd = Path(event.get("cwd") or ".").resolve()
    for raw_path in patch_targets(event):
        path = relative_path(event, raw_path)
        match = DAG_PATH.match(path)
        if not match:
            continue
        workload = match.group(1)
        if (cwd / "workloads" / workload / "logs").is_dir():
            continue
        reason = (
            f"workloads/{workload}/logs/ does not exist. Create the workload logs "
            "directory before writing its DAG."
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
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
