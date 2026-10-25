#!/usr/bin/env python3
"""Enforce the human discovery gate for new workloads."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from patch_paths import patch_targets, relative_path


WORKLOAD_PATH = re.compile(r"^workloads/([^/]+)/(config|scripts|dags|sql)/")


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        return 0

    cwd = Path(event.get("cwd") or ".").resolve()
    for raw_path in patch_targets(event):
        path = relative_path(event, raw_path)
        match = WORKLOAD_PATH.match(path)
        if not match:
            continue
        workload = match.group(1)
        workload_root = cwd / "workloads" / workload
        if (
            (workload_root / "config" / "source.yaml").exists()
            or (workload_root / ".discovery_complete").exists()
        ):
            continue
        reason = (
            f"Discovery is not complete for workload '{workload}'. Ask the user "
            "about source details, keys, transformations, PII, quality thresholds, "
            "schedule, and ontology before creating pipeline artifacts."
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
