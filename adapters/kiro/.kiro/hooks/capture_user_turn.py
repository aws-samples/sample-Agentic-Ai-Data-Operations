#!/usr/bin/env python3
"""Capture a Kiro UserPromptSubmit event into the requirements ledger."""

from pathlib import Path
import sys

def _project_root() -> Path:
    """Find the bundle root in both a full checkout and an adapter snapshot."""

    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "shared" / "requirements" / "capture.py").is_file():
            return candidate
    # Keep the error actionable if somebody copied only the hook file.
    return here.parents[2]


PROJECT_ROOT = _project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.requirements.capture import capture_json_stdin


if __name__ == "__main__":
    capture_json_stdin(cwd=PROJECT_ROOT)
