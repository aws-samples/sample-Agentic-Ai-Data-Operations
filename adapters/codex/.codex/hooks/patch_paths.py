#!/usr/bin/env python3
"""Helpers for inspecting Codex apply_patch hook events."""

from __future__ import annotations

import re
from pathlib import Path


PATCH_FILE_HEADER = re.compile(r"^\*\*\* (Add|Update|Delete) File: (.+)$")
PATCH_MOVE_HEADER = re.compile(r"^\*\*\* Move to: (.+)$")


def patch_text(event: dict) -> str:
    tool_input = event.get("tool_input") or {}
    return str(tool_input.get("command") or tool_input.get("input") or "")


def patch_targets(event: dict) -> list[str]:
    """Return the relative paths touched by an apply_patch event."""
    tool_input = event.get("tool_input") or {}
    if tool_input.get("file_path"):
        return [str(tool_input["file_path"])]
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        return [
            str(edit["file_path"])
            for edit in edits
            if isinstance(edit, dict) and edit.get("file_path")
        ]

    targets: list[str] = []
    for line in patch_text(event).splitlines():
        match = PATCH_FILE_HEADER.match(line)
        if match:
            targets.append(match.group(2).strip())
            continue
        move = PATCH_MOVE_HEADER.match(line)
        if move:
            targets.append(move.group(1).strip())
    return targets


def relative_path(event: dict, path: str) -> str:
    """Normalize an absolute or relative patch path against the event cwd."""
    cwd = Path(event.get("cwd") or ".").resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    try:
        return candidate.resolve().relative_to(cwd).as_posix()
    except ValueError:
        return candidate.as_posix()
