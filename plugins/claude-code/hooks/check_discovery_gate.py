#!/usr/bin/env python3
"""PreToolUse hook: Phase 1 discovery must be complete before pipeline files are written.

A Python port of the repository's `.claude/hooks/check-discovery-gate.sh`, with identical
behaviour. Ported rather than vendored for one reason: the original shells out to `jq` in two
places, and a plugin installed into an arbitrary machine cannot assume `jq` exists. A gate that
silently fails to run is worse than no gate — that is exactly how the repository's entire
pre-commit suite sat disabled for six months behind a one-character hook-id typo.

## What it gates, and what it deliberately does not

Denies `Write`/`Edit` under `workloads/{name}/{config,scripts,dags,sql}/` for a workload that has
neither `config/source.yaml` (so it has been through discovery before) nor a
`.discovery_complete` marker.

This is the machinery behind the plugin's most emphasised rule. Without it the Phase 1 gate is
advisory prose in a command body; with it, an attempt to generate before the human has answered is
refused.

## Why sub-agents cannot satisfy it

The deny message tells the reader to create `workloads/{name}/.discovery_complete`. **That
instruction is addressed to the orchestrator**, which is the only party holding `AskUserQuestion`
and therefore the only party that could have asked the five questions. Sub-agents are launched
without it. A marker created by a sub-agent asserts a human conversation that never happened, and
converts the guardrail into a no-op for every later write in that workload — so the message says
so explicitly, and `adop:discovery-protocol` repeats it.

## It stands down inside an ADOP checkout

Hooks carry no namespace, so this would otherwise deny the same write twice alongside the
repository's own. See `_stand_down.py`.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stand_down import stand_down_if_project_owns  # noqa: E402

GATED = re.compile(r"^workloads/([^/]+)/(config|scripts|dags|sql)/")


def relative(path: str) -> str:
    """Match the shell original's normalisation of an absolute path to a repo-relative one."""
    cwd = os.getcwd().rstrip("/") + "/"
    return path[len(cwd):] if path.startswith(cwd) else path


def reason(workload: str) -> str:
    return (
        f'BLOCKED: Phase 1 discovery not complete for workload "{workload}".\n\n'
        "The user MUST be asked about: (1) source details, (2) primary key and PII columns, "
        "(3) cleaning and transformation rules, (4) quality thresholds, (5) schedule.\n\n"
        f"The ORCHESTRATOR asks those questions and then creates "
        f"workloads/{workload}/.discovery_complete.\n\n"
        "If you are a sub-agent you cannot satisfy this gate — you have no AskUserQuestion tool, "
        "so you cannot have asked. Do NOT create the marker to unblock yourself; return "
        'status "blocked" naming this gate in blocking_issues. Answers already present in '
        "run/context.json are not a substitute: the marker records that the orchestrator "
        "verified them, which is the orchestrator's call.\n\n"
        "See the adop:discovery-protocol skill for the question sets."
    )


def main() -> int:
    if stand_down_if_project_owns("check-discovery-gate.sh", "check_discovery_gate.py"):
        print("{}")
        return 0

    try:
        event = json.load(sys.stdin)
    except Exception:
        print("{}")
        return 0

    path = (event.get("tool_input") or {}).get("file_path")
    if not isinstance(path, str) or not path:
        print("{}")
        return 0

    m = GATED.match(relative(path))
    if not m:
        print("{}")
        return 0

    workload = m.group(1)
    root = Path("workloads") / workload

    # An existing workload has already been through discovery; a marker is only
    # required for a new one. Same two conditions as the shell original.
    if (root / "config" / "source.yaml").is_file() or (root / ".discovery_complete").is_file():
        print("{}")
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason(workload),
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
