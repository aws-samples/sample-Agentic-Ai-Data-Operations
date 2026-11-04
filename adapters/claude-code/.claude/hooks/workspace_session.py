#!/usr/bin/env python3
"""Adapter Claude Code entry point for the shared ADOP workspace hook."""

from __future__ import annotations

import sys
from pathlib import Path


def _root() -> Path:
    starts = (Path.cwd().resolve(), Path(__file__).resolve())
    for start in starts:
        for candidate in (start, *start.parents):
            if (candidate / "shared" / "control_plane" / "workspace_context.py").is_file():
                return candidate
    return Path(__file__).resolve().parents[4]


ROOT = _root()
sys.path.insert(0, str(ROOT))

from shared.control_plane.workspace_context import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["hook-session", "--cwd", str(ROOT)]))
