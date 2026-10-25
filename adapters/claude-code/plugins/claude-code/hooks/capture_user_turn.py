#!/usr/bin/env python3
"""Capture a Claude UserPromptSubmit event into the active workload ledger."""

from pathlib import Path
import sys

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path.cwd()
LIB_ROOT = PLUGIN_ROOT / "lib"
if str(LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(LIB_ROOT))

from shared.requirements.capture import capture_json_stdin


if __name__ == "__main__":
    capture_json_stdin(cwd=PROJECT_ROOT)
