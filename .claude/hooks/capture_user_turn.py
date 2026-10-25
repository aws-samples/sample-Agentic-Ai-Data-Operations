#!/usr/bin/env python3
"""Capture a Claude Code UserPromptSubmit event into the requirements ledger."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.requirements.capture import capture_json_stdin


if __name__ == "__main__":
    capture_json_stdin(cwd=PROJECT_ROOT)
