#!/usr/bin/env python3
"""ADOP hook launcher for Kiro — payload adaptation and exit-contract translation.

`adop-hook.sh` execs this. The gate scripts under this directory are shared with the
other ADOP editions, so they read and write a slightly different hook contract than
Kiro uses. This launcher sits in front of them and adapts both directions.

Why this is Python rather than shell
------------------------------------
The previous shell implementation did its JSON work with `jq`. When `jq` was absent it
skipped normalisation, printed a warning to STDERR on an exit-0 path (where Kiro
discards it) and allowed the write — so `block_credentials.py` read `content` from a
payload that only carries `text`, saw an empty body, and let writes carrying AWS keys
through with no sign anything was wrong. python3 is already a hard dependency of every
gate in this directory, so using it here removes a dependency instead of adding one.

What the adaptation involves
----------------------------

1. PATH RESOLUTION. Kiro does not path-resolve hook commands and documents no
   bundle-root variable, so the gate is located relative to this file rather than to
   the working directory.

2. KEY NORMALISATION. A live Kiro PreToolUse payload looks like::

       {"tool_name": "fs_write", "tool_input": {"path": "/abs/path", "text": "..."}}

   The gate scripts expect `file_path` / `content` / `new_string`. Keys are *added*
   here rather than renamed in the scripts, so the shared implementation stays shared
   and one change covers every gate. Both the snake_case (CLI) and camelCase (IDE)
   spellings are accepted.

3. PATH-ONLY EVENTS. `PostFileSave` carries a file path and no `tool_input`. A
   synthetic `tool_input` is built from it so the same gates run unmodified; they fall
   back to reading the file from disk when no pending content is present.

4. BLOCK CONTRACT. Kiro blocks a tool call when a hook exits 2, and shows the reason
   from STDERR. The gate scripts instead print a JSON decision on STDOUT and exit 0::

       {"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "..."}}
       {"decision": "block", "reason": "..."}

   Kiro ignores that JSON. Without translation every gate would exit 0, Kiro would
   allow the write, and the gate would silently stop working while appearing healthy.

5. CONTEXT AND ADVISORY PASS-THROUGH. For `SessionStart` / `AgentSpawn` /
   `UserPromptSubmit`, Kiro adds a hook's STDOUT to the agent's context. Two shapes are
   unwrapped so the agent receives usable text rather than a JSON blob to interpret:
   `hookSpecificOutput.additionalContext` (the run-context hook) and `systemMessage`
   (the non-blocking findings from `validate_artifacts.py`, which the shell version
   dropped on the floor entirely).

6. FAIL CLOSED, BUT ONLY WHERE IT IS SAFE TO. If a gate crashes or prints something
   unparseable on a tool-gating event (`PreToolUse`), this exits 2: a gate that cannot
   deliver a verdict must not resolve to "allow". On every other event it exits 0 with
   a warning, because a broken capture or context hook must never wedge the user's
   session or block their prompt.

Usage: adop_launcher.py <script-name-in-this-directory>
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

HOOK_DIR = Path(__file__).resolve().parent

# Events where exit 2 actually denies the action, and where a gate that cannot answer
# must therefore fail closed rather than fall through to allow.
GATING_EVENTS = ("pretooluse", "pretaskexec")

# tool_input key aliases: (canonical key the shared gates read, source spellings Kiro sends)
KEY_ALIASES = (
    ("content", ("text", "fileText", "file_text")),
    ("file_path", ("path", "filePath")),
    ("new_string", ("new_str", "newStr")),
    ("old_string", ("old_str", "oldStr")),
)

# Top-level path keys used by the file-event triggers, which carry no tool_input.
PATH_KEYS = ("path", "file_path", "filePath", "filepath")


def _is_gating(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    event = str(payload.get("hook_event_name") or payload.get("hookEventName") or "")
    return event.replace("_", "").replace("-", "").lower() in GATING_EVENTS


def _normalise(payload: Any) -> Any:
    """Add the key spellings the shared gates read, without removing Kiro's."""
    if not isinstance(payload, dict):
        return payload

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = payload.get("toolInput") if isinstance(payload.get("toolInput"), dict) else None

    if tool_input is None:
        # Path-only event (PostFileSave / PostFileCreate / PostFileDelete): synthesise
        # a tool_input so the gates need no special case for it.
        for key in PATH_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value:
                tool_input = {"path": value}
                break

    if not isinstance(tool_input, dict):
        return payload

    tool_input = dict(tool_input)
    for canonical, sources in KEY_ALIASES:
        if canonical in tool_input:
            continue
        for source in sources:
            value = tool_input.get(source)
            if isinstance(value, str):
                tool_input[canonical] = value
                break

    payload = dict(payload)
    payload["tool_input"] = tool_input
    return payload


def _as_json(text: str) -> dict | None:
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _deny_reason(decision: dict) -> str | None:
    """Return the reason when `decision` denies, else None."""
    specific = decision.get("hookSpecificOutput")
    specific = specific if isinstance(specific, dict) else {}
    if specific.get("permissionDecision") == "deny":
        return str(
            specific.get("permissionDecisionReason") or "Blocked by ADOP policy gate."
        )
    if decision.get("permissionDecision") == "deny":
        return str(
            decision.get("permissionDecisionReason") or "Blocked by ADOP policy gate."
        )
    if decision.get("decision") == "block":
        return str(decision.get("reason") or "Blocked by ADOP policy gate.")
    return None


def _additional_context(decision: dict) -> str | None:
    specific = decision.get("hookSpecificOutput")
    specific = specific if isinstance(specific, dict) else {}
    for value in (specific.get("additionalContext"), decision.get("additionalContext")):
        if isinstance(value, str) and value.strip():
            return value
    return None


def main(argv: list[str]) -> int:
    raw = sys.stdin.read()

    if len(argv) < 2 or not argv[1]:
        print("adop-hook: no hook script named", file=sys.stderr)
        return 0  # launcher misuse must not wedge the session
    hook = HOOK_DIR / argv[1]
    if not hook.is_file():
        print(f"adop-hook: cannot locate hook '{argv[1]}' under {HOOK_DIR}", file=sys.stderr)
        return 0

    payload = _as_json(raw)
    gating = _is_gating(payload)
    stdin_text = raw if payload is None else json.dumps(_normalise(payload))

    try:
        completed = subprocess.run(
            [sys.executable, str(hook)],
            input=stdin_text,
            text=True,
            capture_output=True,
            timeout=25,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"adop-hook: {hook.name} could not run: {exc}", file=sys.stderr)
        return 2 if gating else 0

    # Upstream already speaks Kiro's dialect: pass the denial straight through.
    if completed.returncode == 2:
        print((completed.stderr or completed.stdout).strip(), file=sys.stderr)
        return 2

    decision = _as_json(completed.stdout)

    if decision is None:
        # A gate that produced nothing parseable has not delivered a verdict.
        detail = (completed.stderr or completed.stdout).strip()
        if completed.returncode != 0 or not completed.stdout.strip():
            message = f"adop-hook: {hook.name} exited {completed.returncode}"
            if detail:
                message += f": {detail}"
            print(message, file=sys.stderr)
            return 2 if gating else 0
        return 0

    context = _additional_context(decision)
    if context is not None:
        print(context)
        return 0

    reason = _deny_reason(decision)
    if reason is not None:
        print(reason, file=sys.stderr)
        return 2

    # An explicit "ask" is a shape Kiro reads directly from STDOUT on exit 0.
    specific = decision.get("hookSpecificOutput")
    if isinstance(specific, dict) and specific.get("permissionDecision") == "ask":
        print(json.dumps(decision))
        return 0

    advisory = decision.get("systemMessage")
    if isinstance(advisory, str) and advisory.strip():
        print(advisory)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
