#!/usr/bin/env python3
"""PostToolUse hook: captures AskUserQuestion interactions.

Translation of `.claude/hooks/log_conversation.py`. It writes to the active
workload's `logs/conversation_events.jsonl` and captures the same exchange in
the requirements ledger. The stand-down guard is needed because hooks are not
namespaced.

Why the plugin needs this: the plugin ships `skills/observability/`, carrying
`.claude/rules/07-error-logging.md`, which requires every run to produce a trace and
every Q&A exchange to be captured. Nothing else captures the exchanges automatically,
so without this hook the plugin states a logging requirement it provides no means to
meet.

## Two discrepancies in the original, preserved rather than quietly fixed

The docstring says it logs "to the active workload's trace_events.jsonl via AgentTracer
conversation flow methods". Neither half holds:

  - it writes `logs/conversation_events.jsonl`, not `trace_events.jsonl`
  - it writes the JSON lines itself; AgentTracer is never imported

The workload-aware path is intentional: the requirements auditor reads evidence
from the workload, not from an unrelated project-root logs directory. When no
active workload run exists, the hook falls back to project-root `logs/`.

Hook receives JSON on stdin with:
  {"tool_name": "AskUserQuestion", "tool_input": {...}, "tool_result": {...}}

Always exits 0 (pass-through, never blocks).
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
LIB_ROOT = PLUGIN_ROOT / "lib"
sys.path.insert(0, str(LIB_ROOT))
sys.path.insert(1, str(Path(__file__).resolve().parent))
from _stand_down import stand_down_if_project_owns  # noqa: E402
from shared.requirements.capture import capture_event  # noqa: E402


def _detect_workload() -> str:
    """Try to detect active workload from env or CWD."""
    return os.environ.get("ADOP_WORKLOAD", "unknown")


def _detect_phase() -> int | None:
    """Try to detect active phase from env."""
    phase = os.environ.get("ADOP_PHASE")
    return int(phase) if phase else None


def _conversation_log_path(workload: str) -> Path:
    workload_root = Path.cwd() / "workloads" / workload
    if workload != "unknown" and (workload_root / "run").is_dir():
        return workload_root / "logs" / "conversation_events.jsonl"
    return Path.cwd() / "logs" / "conversation_events.jsonl"


def _generate_thread_id() -> str:
    import uuid
    return f"thr-{uuid.uuid4().hex[:8]}"


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, IOError):
        return 0

    tool_name = event.get("tool_name", "")

    if tool_name != "AskUserQuestion":
        return 0

    tool_input = event.get("tool_input", {})
    tool_result = event.get("tool_result", {})

    capture_event(event, cwd=Path.cwd())

    workload = _detect_workload()
    phase = _detect_phase()
    hook_log_path = _conversation_log_path(workload)
    thread_id = _generate_thread_id()
    ts = datetime.now(timezone.utc).isoformat()

    questions = tool_input.get("questions", [])
    answers = tool_result.get("answers", {})

    entries = []

    for q in questions:
        question_text = q.get("question", "")
        options = [opt.get("label", "") for opt in q.get("options", [])]

        entries.append({
            "timestamp": ts,
            "workload_name": workload,
            "phase": phase,
            "thread_id": thread_id,
            "surface": "contextual",
            "event_type": "question_asked",
            "agent_name": "orchestrator",
            "payload": {
                "question_text": question_text,
                "options": options,
                "header": q.get("header", ""),
            },
        })

        answer_text = answers.get(question_text, "")
        if answer_text:
            selected = [answer_text] if answer_text in options else []
            entries.append({
                "timestamp": ts,
                "workload_name": workload,
                "phase": phase,
                "thread_id": thread_id,
                "surface": "contextual",
                "event_type": "user_responded",
                "agent_name": "orchestrator",
                "payload": {
                    "answer_text": answer_text,
                    "selected_options": selected,
                },
            })

    if entries:
        try:
            hook_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(hook_log_path, "a") as f:
                for entry in entries:
                    f.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    if stand_down_if_project_owns("log_conversation.py"):
        raise SystemExit(0)
    sys.exit(main())
