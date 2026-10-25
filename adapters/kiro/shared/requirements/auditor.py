"""Minimal portable ledger writer used by the standalone Kiro hook."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_user_turn(
    run_dir: str | Path,
    *,
    prompt: str,
    response: str,
    phase: int | str | None = None,
    thread_id: str | None = None,
    turn_id: str | None = None,
) -> str:
    """Append an unclassified user turn to the authoritative ledger."""

    turn_id = turn_id or f"turn-{uuid.uuid4().hex[:12]}"
    path = Path(run_dir) / "requirements.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.open("a", encoding="utf-8").write(
        json.dumps(
            {
                "record_type": "user_turn",
                "turn_id": turn_id,
                "timestamp": _now(),
                "phase": phase,
                "thread_id": thread_id,
                "prompt": prompt,
                "response": response,
                "requirement_ids": [],
            },
            sort_keys=True,
        )
        + "\n"
    )
    return turn_id
