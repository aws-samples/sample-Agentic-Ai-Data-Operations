#!/usr/bin/env python3
"""PostToolUse hook: automatically captures AskUserQuestion interactions.

Logs every question asked and user response to the active workload's
trace_events.jsonl via AgentTracer conversation flow methods.

Hook receives JSON on stdin with:
  {"tool_name": "AskUserQuestion", "tool_input": {...}, "tool_result": {...}}

Always exits 0 (pass-through, never blocks).
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


TRACE_LOG_DIR = Path("logs")
HOOK_LOG_PATH = TRACE_LOG_DIR / "conversation_events.jsonl"


def _detect_workload() -> str:
    """Try to detect active workload from env or CWD."""
    return os.environ.get("ADOP_WORKLOAD", "unknown")


def _detect_phase() -> int | None:
    """Try to detect active phase from env."""
    phase = os.environ.get("ADOP_PHASE")
    return int(phase) if phase else None


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

    workload = _detect_workload()
    phase = _detect_phase()
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
            HOOK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(HOOK_LOG_PATH, "a") as f:
                for entry in entries:
                    f.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
