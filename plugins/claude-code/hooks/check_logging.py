#!/usr/bin/env python3
"""PreToolUse logging gate — Python port of `.claude/hooks/check-logging.sh`.

Four checks, in the shell original's order, with its wording preserved verbatim so a
user who hits a block and greps the repo finds the same sentence:

  1. an ETL script under workloads/*/scripts/{transform,quality,extract,load}/ must
     import StructuredLogger (Write only — an Edit carries partial content)
  2. workloads/{name}/logs/ must exist before the DAG is written
  3. workloads/{name}/README.md is blocked until logs/trace_events.jsonl exists
  4. any file containing `Agent(` must also mention `decisions`

## Why a port and not a copy

The original needs `jq` for every read and every reply — six invocations. `jq` is not
a Python dependency, is absent from a stock macOS, and a plugin cannot install it. The
shell version's failure mode if it is missing is the bad one: `jq` prints to stderr,
the script continues, `FILE` is empty, line 6 exits 0, and the gate is silently open.
`check_discovery_gate.py` was ported for the same reason; this is the same trade.

Behaviour is otherwise identical, including two quirks kept deliberately:

  - check 4 applies to *every* written file, not only workload artifacts. Broad, but
    narrowing it here would make the plugin enforce less than the repo.
  - check 1 fires only when `content` is present, so an Edit that strips the
    StructuredLogger import passes. That is the original's behaviour; it belongs in a
    repo fix, not in a silent divergence.

Exits 0 always — a deny is expressed in the JSON payload, never in the exit code.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stand_down import stand_down_if_project_owns  # noqa: E402

ETL_SCRIPT = re.compile(r"^workloads/[^/]+/scripts/(transform|quality|extract|load)/.*\.py$")
WORKLOAD_DAG = re.compile(r"^workloads/[^/]+/dags/.*\.py$")
WORKLOAD_README = re.compile(r"^workloads/[^/]+/README\.md$")
PROJECT_CONFIG = re.compile(r"^(SKILLS|CLAUDE)\.md$|^\.claude/")

LOGGER_MARKERS = ("StructuredLogger", "structured_logger", "ScriptTracer", "script_tracer")


def deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    raise SystemExit(0)


def main() -> None:
    try:
        event = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return  # unreadable payload — the shell version's `jq` failure also allowed

    tool_input = event.get("tool_input") or {}
    raw = tool_input.get("file_path") or ""
    if not raw:
        return

    # The shell original does `sed "s|$(pwd)/||"`. relative_to is the same idea and
    # does not mangle a path that merely contains the cwd as a substring.
    cwd = Path(os.getcwd())
    try:
        path = Path(raw).resolve().relative_to(cwd.resolve()).as_posix()
    except ValueError:
        path = raw.removeprefix(f"{cwd}/")

    # `content` present means Write (full file); absent means Edit (a fragment).
    content = tool_input.get("content")
    has_content = content is not None
    content = content or ""

    # 1 — ETL scripts must log
    if ETL_SCRIPT.match(path) and has_content:
        if not any(m in content for m in LOGGER_MARKERS):
            deny(
                f"BLOCKED: {path} is an ETL script but does not import StructuredLogger. "
                "All ETL scripts MUST use shared.utils.structured_logger for structured "
                "log output. Add: from shared.utils.structured_logger import StructuredLogger"
            )

    # 2 — logs/ must exist before the DAG
    if WORKLOAD_DAG.match(path):
        workload = path.split("/")[1]
        if not (cwd / "workloads" / workload / "logs").is_dir():
            deny(
                f"BLOCKED: workloads/{workload}/logs/ directory does not exist. Every "
                "workload MUST have a logs/ directory for trace_events.jsonl and run "
                "traces. Create it before writing the DAG."
            )

    # 3 — README waits for a trace
    if WORKLOAD_README.match(path):
        workload = path.split("/")[1]
        logs = cwd / "workloads" / workload / "logs"
        if logs.is_dir() and not (logs / "trace_events.jsonl").is_file():
            deny(
                f"BLOCKED: workloads/{workload}/logs/trace_events.jsonl does not exist. "
                "Every workflow run MUST produce a structured trace before "
                "post-deployment steps. Write the trace log first."
            )

    # 4 — an Agent() spawn must state the decisions requirement.
    # Config and rules files are allowed to mention Agent( without it.
    if PROJECT_CONFIG.search(path):
        return
    if has_content and "Agent(" in content and "decisions" not in content:
        deny(
            "BLOCKED: File contains Agent() spawn but does not mention decisions array "
            "requirement. Every sub-agent MUST include a decisions array in its "
            "AgentOutput. Add decisions requirement to the spawn prompt."
        )


if __name__ == "__main__":
    # Hooks are not namespaced. Stand down for either the shell original or a
    # same-named Python counterpart.
    if stand_down_if_project_owns("check-logging.sh", "check_logging.py"):
        raise SystemExit(0)
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # a gate must not break the session
        print(f"check_logging: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(0)
