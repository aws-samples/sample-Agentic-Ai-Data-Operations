#!/usr/bin/env python3
"""Append one explicit user turn to a workload's requirements ledger."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.requirements.capture import capture_turn


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workload", default=os.environ.get("ADOP_WORKLOAD", "unknown"))
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--response", default="")
    parser.add_argument("--phase", default=os.environ.get("ADOP_PHASE"))
    parser.add_argument("--thread-id")
    args = parser.parse_args()

    turn_id = capture_turn(
        workload=args.workload,
        prompt=args.prompt,
        response=args.response,
        phase=args.phase,
        cwd=PROJECT_ROOT,
        thread_id=args.thread_id,
    )
    if not turn_id:
        print(
            json.dumps(
                {
                    "captured": False,
                    "reason": "workload run directory does not exist or prompt is empty",
                }
            ),
            file=sys.stderr,
        )
        return 2

    print(json.dumps({"captured": True, "turn_id": turn_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
