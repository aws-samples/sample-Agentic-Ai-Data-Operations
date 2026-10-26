#!/usr/bin/env python3
"""Restrict requirements-auditor writes to its three append/report outputs.

THIS HOOK IS DEFENCE IN DEPTH, NOT THE PRIMARY ENFORCEMENT.

Kiro's PreToolUse payload is `{"tool_name": ..., "tool_input": {...}}` — it does not
identify which agent is making the call, and a hook subprocess inherits Kiro's
environment rather than the agent's. So this gate can only recognise the auditor when
the process that spawned it exported ADOP_AGENT_NAME, or when the surface in use adds
an agent name to the payload. When it cannot tell who is calling, it allows: a gate
that denied every unattributed write would block the orchestrator and all six build
agents.

The enforceable version of this rule lives in the agent definition, where Kiro applies
it directly and no payload introspection is needed
(`.kiro/agents/requirements-auditor.json`)::

    "permissions": {"rules": [
      {"capability": "fs_write", "match": ["**"],
       "exclude": ["workloads/*/run/requirements_audit.json", ...], "effect": "deny"}
    ]}

Keep the two in sync. If you widen ALLOWED_SUFFIXES here, widen the `exclude` list
there, or the auditor will be denied by the harness while this hook allows it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping


ALLOWED_SUFFIXES = (
    "/run/requirements_audit.json",
    "/run/decisions.jsonl",
    "/logs/trace_events.jsonl",
)

# Spellings the different Kiro surfaces and the ADOP orchestrator may use for the
# calling agent's identity. None is guaranteed to be present; see the module docstring.
ACTOR_KEYS = ("agent_name", "agentName", "agent", "subagent", "subagent_name")


def _paths(tool_input: Mapping[str, Any]) -> list[str]:
    """Every path this tool call would write to, de-duplicated, order preserved.

    The launcher adds `file_path` as an alias of Kiro's `path`, so both keys are
    normally present and identical — collecting them naively reported each target
    twice in the denial message.
    """
    values: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value and value not in values:
            values.append(value)

    for key in ("file_path", "path"):
        add(tool_input.get(key))
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, Mapping):
                add(edit.get("file_path") or edit.get("path"))
    return values


def _actor(payload: Mapping[str, Any], tool_input: Mapping[str, Any]) -> str:
    candidates = [os.environ.get("ADOP_AGENT_NAME")]
    for key in ACTOR_KEYS:
        candidates.append(payload.get(key))
        candidates.append(tool_input.get(key))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip().lower().replace("_", "-")
    return ""


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, Mapping):
        payload = {}
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, Mapping) else {}

    if _actor(payload, tool_input) != "requirements-auditor":
        print("{}")
        return

    paths = _paths(tool_input)
    disallowed = [
        path
        for path in paths
        if not any(path.replace("\\", "/").endswith(suffix) for suffix in ALLOWED_SUFFIXES)
    ]
    if disallowed:
        reason = (
            "BLOCKED: requirements-auditor may write only run/requirements_audit.json, "
            "run/decisions.jsonl, or logs/trace_events.jsonl; attempted: "
            + ", ".join(disallowed)
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
        return
    print("{}")


if __name__ == "__main__":
    main()
