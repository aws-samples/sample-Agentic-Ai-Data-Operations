#!/usr/bin/env python3
"""Block direct edits to generated pipeline artifacts.

Protected workload artifacts must be produced by ``shared.codegen.renderer``.
The renderer sets ADOP_RENDERER_TOKEN while it writes the generated files.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from patch_paths import patch_targets, relative_path


PROTECTED_PATTERN = re.compile(r"^workloads/[^/]+/(scripts|dags|sql)/")
TOKEN_ENV = "ADOP_RENDERER_TOKEN"
HOOK_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "hook_blocks.jsonl"


def deny(reason: str) -> int:
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


def log_block(path: str, reason: str) -> None:
    try:
        HOOK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with HOOK_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "cwd": os.getcwd(),
                        "attempted_path": path,
                        "reason": reason,
                    }
                )
                + "\n"
            )
    except OSError:
        pass


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        return 0

    if event.get("tool_name") not in {None, "apply_patch"}:
        return 0
    if os.environ.get(TOKEN_ENV):
        return 0

    for raw_path in patch_targets(event):
        path = relative_path(event, raw_path)
        if PROTECTED_PATTERN.search(path):
            reason = (
                f"Direct write to '{path}' is blocked. Artifacts under "
                "workloads/*/scripts/, dags/, and sql/ must be produced by "
                "shared.codegen.renderer.render(). Modify the spec and re-render."
            )
            log_block(path, reason)
            return deny(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
