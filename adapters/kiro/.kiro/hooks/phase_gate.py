#!/usr/bin/env python3
"""Block Kiro agent spawning until the human discovery gate is complete."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "scripts").is_dir() and (candidate / "adapters").is_dir():
            return candidate
    return here.parents[4]


ROOT = _project_root()
WORKLOAD_RE = re.compile(r"(?:^|/|\\)workloads[\/\\]([a-z][a-z0-9_]{1,40})(?:[\/\\]|$)")
COMMON = (
    "pii_columns",
    "compliance",
    "quality_thresholds",
    "schedule",
    "schedule_timezone",
    "ontology_opt_in",
    "transformations",
)
ZONE_FIELDS = {
    "bronze": ("source_path", "credentials", "ingestion_pattern", "retention"),
    "silver": ("primary_key", "dedup_strategy", "null_handling"),
    "gold": ("business_outcome", "kpis", "aggregation_grain", "gold_schema_choice"),
}


def _deny(reason: str) -> None:
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


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _nonempty(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def _workload(payload: Mapping[str, Any]) -> str | None:
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, Mapping) else {}
    # Kiro's built-in spawn tool is `subagent`; its tool_input carries the target agent
    # name and the task prompt. The workload is not a first-class field, so it is read
    # from an explicit key when the orchestrator supplies one, then from the environment,
    # then recovered from the prompt text as a last resort.
    for value in (
        tool_input.get("workload_name"),
        tool_input.get("workloadName"),
        payload.get("workload_name"),
        os.environ.get("ADOP_WORKLOAD"),
        tool_input.get("prompt"),
        tool_input.get("message"),
        tool_input.get("task"),
        payload.get("prompt"),
    ):
        if not isinstance(value, str):
            continue
        match = WORKLOAD_RE.search(value)
        if match:
            return match.group(1)
        if re.fullmatch(r"[a-z][a-z0-9_]{1,40}", value):
            return value
    return None


def _blockers(workload: str) -> list[str]:
    run = ROOT / "workloads" / workload / "run"
    blockers: list[str] = []
    context_path = run / "context.json"
    marker_path = run / "discovery_complete.json"
    if not context_path.is_file():
        blockers.append("run/context.json is missing")
        return blockers
    if not marker_path.is_file():
        blockers.append("run/discovery_complete.json is missing")
    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"run/context.json is unreadable: {exc}"]
    answers = context.get("human_answers", {}) if isinstance(context, dict) else {}
    if not isinstance(answers, Mapping):
        return ["context.json human_answers must be an object"]
    zones = answers.get("zones")
    if not isinstance(zones, list) or not zones:
        blockers.append("human_answers.zones is missing")
    else:
        for zone in zones:
            for field in ZONE_FIELDS.get(str(zone), ()):
                if not _nonempty(answers.get(field)):
                    blockers.append(f"human_answers.{field} is missing for {zone}")
    for field in COMMON:
        # ontology_opt_in is a boolean, so a legitimate opt-out (`false`) must satisfy the
        # gate. Running it through _nonempty() treats false as "unanswered" and deadlocks
        # every workload that declined the ontology step. Kept identical to the same
        # branch in scripts/kiro_workflow.py: the two must agree or the hook blocks runs
        # the driver passes.
        if field == "ontology_opt_in":
            if not isinstance(answers.get(field), bool):
                blockers.append(
                    "human_answers.ontology_opt_in is missing and must be boolean"
                )
        elif not _nonempty(answers.get(field)):
            blockers.append(f"human_answers.{field} is missing")
    if answers.get("ontology_opt_in") is True and not _nonempty(
        answers.get("ontology_use_cases")
    ):
        blockers.append("human_answers.ontology_use_cases is missing")
    return blockers


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, Mapping):
        payload = {}
    workload = _workload(payload)
    if not workload:
        _deny(
            "BLOCKED: agent invocation has no workload_name. Initialize an ADOP run "
            "and identify workloads/<name> before spawning agents."
        )
        return
    blockers = _blockers(workload)
    if blockers:
        _deny(
            "BLOCKED: Phase 1 human discovery gate is incomplete for "
            f"workloads/{workload}: " + "; ".join(sorted(set(blockers)))
        )
        return
    print("{}")


if __name__ == "__main__":
    main()
