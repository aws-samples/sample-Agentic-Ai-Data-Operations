"""Clone-ready platform surface regression tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_platform_surface_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/sync_platforms.py", "check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_active_client_profiles_are_identical() -> None:
    canonical = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    profiles = (
        ".amazonq/mcp.json",
        ".kiro/settings/mcp.json",
        "plugins/claude-code/.mcp.json",
        "adapters/amazon-q/.amazonq/mcp.json",
        "adapters/kiro/.kiro/settings/mcp.json",
        "adapters/claude-code/plugins/claude-code/.mcp.json",
    )
    for relative in profiles:
        assert json.loads((ROOT / relative).read_text(encoding="utf-8")) == canonical


def test_third_party_profiles_are_disabled() -> None:
    for name in ("snowflake", "databricks", "teradata"):
        profile = json.loads(
            (ROOT / f"mcp-profiles/third-party/{name}.json").read_text(
                encoding="utf-8"
            )
        )
        assert profile["enabled"] is False


def test_clone_ready_client_entrypoints_exist() -> None:
    expected = (
        "AGENTS.md",
        "CLAUDE.md",
        "AmazonQ.md",
        ".claude/settings.json",
        ".codex/config.toml",
        ".amazonq/mcp.json",
        ".kiro/settings/mcp.json",
        ".mcp.json",
        "scripts/start_codex.py",
    )
    assert all((ROOT / path).exists() for path in expected)
