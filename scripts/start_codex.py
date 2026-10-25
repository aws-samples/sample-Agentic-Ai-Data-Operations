#!/usr/bin/env python3
"""Start Codex with this checkout's project MCP configuration.

Codex stores its main configuration under CODEX_HOME rather than discovering
``.codex/config.toml`` as a project file. This wrapper translates the
checkout's active MCP entries into supported ``-c`` overrides without
modifying the user's global Codex configuration.

Usage:
    python3 scripts/start_codex.py
    python3 scripts/start_codex.py --check
    python3 scripts/start_codex.py "Describe the data onboarding task"
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".codex" / "config.toml"


def toml_value(value: Any) -> str:
    """Return a JSON/TOML-compatible literal for a Codex -c override."""

    return json.dumps(value, separators=(",", ":"))


def config_overrides(config: dict[str, Any]) -> list[str]:
    overrides: list[str] = []
    for name, server in config.get("mcp_servers", {}).items():
        prefix = f'mcp_servers."{name}"'
        for field, value in server.items():
            overrides.extend(["-c", f"{prefix}.{field}={toml_value(value)}"])
    for name, value in config.get("shell_environment_policy", {}).get("set", {}).items():
        os.environ.setdefault(name, str(value))
    return overrides


def main() -> int:
    codex = shutil.which("codex")
    if not codex:
        print("ERROR: codex is not installed or is not on PATH", file=sys.stderr)
        return 127
    if not CONFIG.exists():
        print(f"ERROR: missing {CONFIG}", file=sys.stderr)
        return 2

    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    user_args = sys.argv[1:]
    if user_args[:1] == ["--check"]:
        user_args = ["mcp", "list", *user_args[1:]]

    command = [codex, *config_overrides(config), *user_args]
    return subprocess.call(command, cwd=ROOT, env=os.environ.copy())


if __name__ == "__main__":
    raise SystemExit(main())
