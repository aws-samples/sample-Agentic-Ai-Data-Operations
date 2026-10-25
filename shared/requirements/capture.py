"""Cross-client capture helpers for user-to-agent conversations.

Client hooks have different payload shapes, but they all need to create the
same append-only user-turn record. This module deliberately does not classify
requirements; classification remains an explicit orchestrator decision.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping

from shared.requirements.auditor import append_user_turn


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("text", "content", "message", "prompt", "value"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
    return ""


def detect_workload(event: Mapping[str, Any], cwd: str | Path = ".") -> str:
    explicit = (
        event.get("workload_name")
        or event.get("workload")
        or os.environ.get("ADOP_WORKLOAD")
    )
    if isinstance(explicit, str) and explicit:
        return explicit

    for value in (
        event.get("file_path"),
        event.get("path"),
        event.get("cwd"),
        str(cwd),
    ):
        if not isinstance(value, str):
            continue
        parts = Path(value).parts
        if "workloads" in parts:
            index = parts.index("workloads")
            if index + 1 < len(parts):
                return parts[index + 1]
    return "unknown"


def _run_dir(workload: str, cwd: str | Path = ".") -> Path | None:
    if workload == "unknown":
        return None
    candidate = Path(cwd).resolve() / "workloads" / workload / "run"
    return candidate if candidate.is_dir() else None


def _pending_dir(workload: str, cwd: str | Path = ".") -> Path | None:
    if workload == "unknown":
        return None
    return Path(cwd).resolve() / "workloads" / workload / ".requirements_pending"


def capture_turn(
    *,
    workload: str,
    prompt: str,
    response: str = "",
    phase: int | str | None = None,
    cwd: str | Path = ".",
    thread_id: str | None = None,
) -> str | None:
    """Append one user turn, buffering it until the run directory exists."""

    prompt = prompt.strip()
    if not prompt:
        return None
    destination = _run_dir(workload, cwd) or _pending_dir(workload, cwd)
    if destination is None:
        return None
    return append_user_turn(
        destination,
        prompt=prompt,
        response=response,
        phase=phase,
        thread_id=thread_id or f"thr-{uuid.uuid4().hex[:8]}",
    )


def capture_event(
    event: Mapping[str, Any],
    *,
    cwd: str | Path = ".",
) -> list[str]:
    """Capture supported Claude/Kiro hook payloads.

    AskUserQuestion payloads produce one turn per question. Generic prompt
    payloads produce one turn. Unknown payloads are ignored safely.
    """

    workload = detect_workload(event, cwd)
    phase = event.get("phase") or os.environ.get("ADOP_PHASE")
    thread_id = event.get("thread_id")
    tool_input = event.get("tool_input")
    tool_result = event.get("tool_result")
    captured: list[str] = []

    if event.get("tool_name") == "AskUserQuestion" and isinstance(tool_input, Mapping):
        questions = tool_input.get("questions", [])
        answers = tool_result.get("answers", {}) if isinstance(tool_result, Mapping) else {}
        for question in questions if isinstance(questions, list) else []:
            if not isinstance(question, Mapping):
                continue
            prompt = _text(question.get("question"))
            response = ""
            if isinstance(answers, Mapping):
                response = _text(answers.get(prompt))
            turn_id = capture_turn(
                workload=workload,
                prompt=prompt,
                response=response,
                phase=phase,
                cwd=cwd,
                thread_id=thread_id,
            )
            if turn_id:
                captured.append(turn_id)
        return captured

    prompt = _text(
        event.get("user_prompt")
        or event.get("prompt")
        or event.get("message")
        or event.get("text")
        or event.get("content")
    )
    response = _text(event.get("response") or event.get("tool_result"))
    turn_id = capture_turn(
        workload=workload,
        prompt=prompt,
        response=response,
        phase=phase,
        cwd=cwd,
        thread_id=thread_id,
    )
    if turn_id:
        captured.append(turn_id)
    return captured


def capture_json_stdin(*, cwd: str | Path = ".") -> list[str]:
    try:
        event = json.loads(__import__("sys").stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(event, Mapping):
        return []
    return capture_event(event, cwd=cwd)
