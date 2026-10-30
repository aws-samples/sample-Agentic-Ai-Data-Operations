"""Offline structure and parity checks for the four ADOP agent adapters."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mcp_demo import active_profile_mode  # noqa: E402

REQUIRED = {
    "claude-code": (
        "adapters/claude-code/CLAUDE.md",
        "adapters/claude-code/.claude/settings.json",
        "adapters/claude-code/.claude/agents/requirements-auditor.md",
        "adapters/claude-code/.claude/hooks/capture_user_turn.py",
        "adapters/claude-code/.claude-plugin/marketplace.json",
        "adapters/claude-code/plugins/claude-code/agents/requirements-auditor.md",
        "adapters/claude-code/plugins/claude-code/hooks/capture_user_turn.py",
        "adapters/claude-code/plugins/claude-code/lib/shared/requirements/auditor.py",
        "adapters/claude-code/plugins/claude-code/lib/shared/requirements/capture.py",
        "adapters/claude-code/plugins/claude-code/requirements-auditor.md",
    ),
    "codex": (
        "adapters/codex/AGENTS.md",
        "adapters/codex/.codex/config.toml",
        "adapters/codex/.codex/agents/requirements-auditor.toml",
        "adapters/codex/.codex/hooks.json",
    ),
    "amazon-q": (
        "adapters/amazon-q/AmazonQ.md",
        "adapters/amazon-q/.amazonq/mcp.json",
        "adapters/amazon-q/.amazonq/cli-agents/adop-requirements-auditor.json",
    ),
    "kiro": (
        "adapters/kiro/.kiro/settings/mcp.json",
        "adapters/kiro/.kiro/agents/requirements-auditor.json",
        "adapters/kiro/.kiro/hooks/adop-gates.json",
        "adapters/kiro/.kiro/hooks/capture_user_turn.py",
        "adapters/kiro/.kiro/hooks/phase_gate.py",
        "adapters/kiro/.kiro/hooks/auditor_write_gate.py",
        "adapters/kiro/.kiro/adop/render.py",
        "adapters/kiro/.kiro/adop/render.sh",
        "adapters/kiro/.kiro/steering/13-workflow-orchestrator.md",
        "adapters/kiro/shared/requirements/capture.py",
        "adapters/kiro/shared/requirements/auditor.py",
    ),
}


def check_file(path: Path, errors: list[str]) -> str:
    if not path.is_file():
        errors.append(f"missing file: {path.relative_to(ROOT)}")
        return ""
    return path.read_text(encoding="utf-8")


def check_json(path: Path, errors: list[str]) -> None:
    text = check_file(path, errors)
    if not text:
        return
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def check_default_mcp_profiles(errors: list[str]) -> None:
    """Keep the low-noise AWS MCP profile enabled across every client.

    An exact ``scripts/mcp_demo.py activate`` result is also accepted; the
    proxy pin below is still enforced in that mode.
    """
    demo = active_profile_mode() == "demo"

    json_profiles = (
        ".mcp.json",
        ".amazonq/mcp.json",
        ".kiro/settings/mcp.json",
        "plugins/claude-code/.mcp.json",
        "adapters/amazon-q/.amazonq/mcp.json",
        "adapters/kiro/.kiro/settings/mcp.json",
        "adapters/claude-code/plugins/claude-code/.mcp.json",
    )
    for relative in json_profiles:
        path = ROOT / relative
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            names = list(data.get("mcpServers", {}))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"cannot inspect active MCP profile {relative}: {exc}")
            continue
        if names != ["aws-mcp"] and not demo:
            errors.append(
                f"{relative} must enable only aws-mcp by default; found {names}"
            )
        server = data.get("mcpServers", {}).get("aws-mcp", {})
        if server.get("command") != "uvx" or "mcp-proxy-for-aws==1.6.0" not in server.get(
            "args", []
        ):
            errors.append(f"{relative} does not use the pinned AWS Agent Toolkit proxy")

    for relative in (".codex/config.toml", "adapters/codex/.codex/config.toml"):
        path = ROOT / relative
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            enabled = [
                name
                for name, value in data.get("mcp_servers", {}).items()
                if value.get("enabled") is True
            ]
        except (OSError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"cannot inspect active Codex MCP profile {relative}: {exc}")
            continue
        if enabled != ["aws-mcp"] and not demo:
            errors.append(
                f"{relative} must enable only aws-mcp by default; found {enabled}"
            )

    optional_profiles = (
        ".mcp.optional.json",
        ".amazonq/mcp.optional.json",
        ".kiro/settings/mcp.optional.json",
        ".codex/config.optional.toml",
        "plugins/claude-code/.mcp.optional.json",
        "adapters/amazon-q/.amazonq/mcp.optional.json",
        "adapters/kiro/.kiro/settings/mcp.optional.json",
        "adapters/codex/.codex/config.optional.toml",
        "adapters/claude-code/plugins/claude-code/.mcp.optional.json",
    )
    for relative in optional_profiles:
        check_file(ROOT / relative, errors)

    provider_servers = {"snowflake-native", "databricks-native", "teradata"}
    for relative in optional_profiles:
        path = ROOT / relative
        try:
            if path.suffix == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                names = set(data.get("mcpServers", {}))
            else:
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                names = set(data.get("mcp_servers", {}))
        except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"cannot inspect optional provider profile {relative}: {exc}")
            continue
        missing = provider_servers - names
        if missing:
            errors.append(
                f"{relative} is missing disabled provider MCP entries: {sorted(missing)}"
            )
        if path.suffix == ".toml":
            enabled = [
                name
                for name in provider_servers
                if data.get("mcp_servers", {}).get(name, {}).get("enabled") is True
            ]
            if enabled:
                errors.append(
                    f"{relative} enables provider MCP entries by default: {sorted(enabled)}"
                )


def check_demo_profile(errors: list[str]) -> None:
    profile_path = ROOT / "mcp-profiles/demo/profile.json"
    script_path = ROOT / "scripts/mcp_demo.py"
    text = check_file(profile_path, errors)
    check_file(script_path, errors)
    if not text:
        return
    try:
        profile = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"invalid demo profile JSON: {exc}")
        return
    known = {
        "aws-mcp",
        "glue-athena",
        "lakeformation",
        "iam",
        "pii-detection",
        "cloudtrail",
    }
    # A server may be switched off only by naming it, with a reason, in
    # `excluded_servers`; anything else missing from `servers` is drift.
    excluded = profile.get("excluded_servers", {})
    for name, reason in excluded.items():
        if name not in known or name == "aws-mcp":
            errors.append(f"demo profile cannot exclude {name!r}")
        elif not str(reason).strip():
            errors.append(f"demo profile excludes {name!r} without a reason")
    expected = known - set(excluded)
    actual = set(profile.get("servers", []))
    if actual != expected:
        errors.append(
            "demo profile server set drifted: "
            f"expected {sorted(expected)}, found {sorted(actual)}"
        )
    required_methods = {
        "create_job",
        "update_job",
        "get_job",
        "get_job_run",
        "get_job_runs",
        "stop_job_run",
        "athena_query",
    }
    methods = set(profile.get("customer_methods", []))
    missing = required_methods - methods
    if missing:
        errors.append(f"demo profile missing customer methods: {sorted(missing)}")


def check_third_party_profiles(errors: list[str]) -> None:
    expected = {
        "snowflake.json": "snowflake-native",
        "databricks.json": "databricks-native",
        "teradata.json": "teradata",
    }
    for relative, expected_name in expected.items():
        path = ROOT / "mcp-profiles" / "third-party" / relative
        text = check_file(path, errors)
        if not text:
            continue
        try:
            profile = json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid third-party profile {relative}: {exc}")
            continue
        if profile.get("name") != expected_name:
            errors.append(
                f"{relative} has unexpected profile name: {profile.get('name')!r}"
            )
        if profile.get("enabled") is not False:
            errors.append(f"{relative} must remain disabled")
        servers = profile.get("mcpServers", {})
        if set(servers) != {expected_name}:
            errors.append(
                f"{relative} must define only {expected_name}; found {sorted(servers)}"
            )


def main() -> int:
    errors: list[str] = []

    for adapter, paths in REQUIRED.items():
        for relative in paths:
            path = ROOT / relative
            check_file(path, errors)

    auditor_files = (
        "adapters/claude-code/.claude/agents/requirements-auditor.md",
        "adapters/codex/.codex/agents/requirements-auditor.toml",
        "adapters/amazon-q/.amazonq/cli-agents/adop-requirements-auditor.json",
        "adapters/kiro/.kiro/agents/requirements-auditor.json",
    )
    for relative in auditor_files:
        text = check_file(ROOT / relative, errors)
        if "requirements-auditor" not in text:
            errors.append(f"auditor contract missing from {relative}")

    for relative in (
        "manifest.yaml",
        "mcp-profiles/demo/profile.json",
        "mcp-profiles/demo/README.md",
        "core/requirements-auditor.md",
        "core/shared/requirements/auditor.py",
        "core/shared/requirements/capture.py",
        "core/shared/requirements/__init__.py",
        "core/tests/test_requirements_auditor.py",
        "scripts/capture_user_turn.py",
        "scripts/kiro_workflow.py",
        "scripts/sync_platforms.py",
        "docs/platform-integration.md",
        "mcp-profiles/third-party/snowflake.json",
        "mcp-profiles/third-party/databricks.json",
        "mcp-profiles/third-party/teradata.json",
    ):
        check_file(ROOT / relative, errors)

    for relative in (
        "adapters/claude-code/.claude/settings.json",
        "adapters/claude-code/.claude-plugin/marketplace.json",
        "adapters/codex/.codex/hooks.json",
        "adapters/amazon-q/.amazonq/mcp.json",
        "adapters/amazon-q/.amazonq/cli-agents/adop-requirements-auditor.json",
        "adapters/kiro/.kiro/settings/mcp.json",
        "adapters/kiro/.kiro/agents/requirements-auditor.json",
        "adapters/kiro/.kiro/hooks/adop-gates.json",
    ):
        check_json(ROOT / relative, errors)

    check_default_mcp_profiles(errors)
    check_demo_profile(errors)
    check_third_party_profiles(errors)

    if errors:
        print(f"FAIL: {len(errors)} integration problem(s)")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("PASS: four native adapters and shared requirements auditor are present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
