#!/usr/bin/env python3
"""Repository-root launcher for the optional ADOP Strands runtime."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtimes.strands.adop_strands.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
