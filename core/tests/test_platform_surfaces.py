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


def _demo_tree(tmp_path: Path, monkeypatch):
    """Write an exact demo activation into tmp_path and point mcp_demo at it."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import mcp_demo

    contents = mcp_demo.target_contents("us-east-1", "default")
    for relative, content in contents.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    monkeypatch.setattr(mcp_demo, "ROOT", tmp_path)
    monkeypatch.setattr(mcp_demo, "DEFAULT_CONFIG", tmp_path / ".mcp.json")
    return mcp_demo, contents


def test_exact_demo_activation_is_recognised(tmp_path: Path, monkeypatch) -> None:
    mcp_demo, _ = _demo_tree(tmp_path, monkeypatch)
    assert mcp_demo.active_profile_mode() == "demo"


def test_partial_demo_activation_is_not_demo(tmp_path: Path, monkeypatch) -> None:
    """One client left on the default profile must still fail validation."""
    mcp_demo, _ = _demo_tree(tmp_path, monkeypatch)
    (tmp_path / ".kiro" / "settings" / "mcp.json").write_text(
        json.dumps({"mcpServers": {"aws-mcp": {}}}, indent=2) + "\n", encoding="utf-8"
    )
    assert mcp_demo.active_profile_mode() == "default"


def test_hand_edited_demo_server_list_is_not_demo(tmp_path: Path, monkeypatch) -> None:
    """An extra server added by hand is drift, not the demo profile."""
    mcp_demo, contents = _demo_tree(tmp_path, monkeypatch)
    path = tmp_path / ".mcp.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["mcpServers"]["unvetted"] = {"command": "uvx", "args": ["something"]}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    assert mcp_demo.active_profile_mode() == "default"
