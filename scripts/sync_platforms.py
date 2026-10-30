#!/usr/bin/env python3
"""Check and synchronize the clone-ready platform surfaces.

The repository keeps native client entry points at the root so a user can
clone the repository and start Claude Code, Codex, Amazon Q, or Kiro from the
repository root.  Adapter and plugin copies remain distribution surfaces.

This command deliberately does not install clients, enable optional MCP
servers, call an LLM, or deploy a workload.

Usage:
    python3 scripts/sync_platforms.py check
    python3 scripts/sync_platforms.py sync --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mcp_demo import active_profile_mode  # noqa: E402

ACTIVE_JSON_PROFILES = (
    Path(".mcp.json"),
    Path(".amazonq/mcp.json"),
    Path(".kiro/settings/mcp.json"),
    Path("plugins/claude-code/.mcp.json"),
    Path("adapters/amazon-q/.amazonq/mcp.json"),
    Path("adapters/kiro/.kiro/settings/mcp.json"),
    Path("adapters/claude-code/plugins/claude-code/.mcp.json"),
)

ACTIVE_CODEX_PROFILES = (
    Path(".codex/config.toml"),
    Path("adapters/codex/.codex/config.toml"),
)

OPTIONAL_JSON_PROFILES = (
    Path(".mcp.optional.json"),
    Path(".amazonq/mcp.optional.json"),
    Path(".kiro/settings/mcp.optional.json"),
    Path("plugins/claude-code/.mcp.optional.json"),
    Path("adapters/amazon-q/.amazonq/mcp.optional.json"),
    Path("adapters/kiro/.kiro/settings/mcp.optional.json"),
    Path("adapters/claude-code/plugins/claude-code/.mcp.optional.json"),
)

OPTIONAL_CODEX_PROFILES = (
    Path(".codex/config.optional.toml"),
    Path("adapters/codex/.codex/config.optional.toml"),
)

PLATFORM_SURFACES: dict[str, tuple[str, ...]] = {
    "claude-code": (
        "CLAUDE.md",
        ".claude/settings.json",
        ".claude/agents",
        ".claude/hooks",
        ".claude/commands",
        ".mcp.json",
        "adapters/claude-code/CLAUDE.md",
        "adapters/claude-code/.claude/settings.json",
        "plugins/claude-code/.claude-plugin/plugin.json",
        "plugins/claude-code/commands",
    ),
    "codex": (
        "AGENTS.md",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".codex/agents",
        ".codex/skills",
        ".codex/hooks",
        "adapters/codex/AGENTS.md",
        "adapters/codex/.codex/config.toml",
        "adapters/codex/.codex/hooks.json",
    ),
    "amazon-q": (
        "AmazonQ.md",
        ".amazonq/mcp.json",
        ".amazonq/cli-agents",
        ".amazonq/hooks",
        ".amazonq/rules",
        "adapters/amazon-q/AmazonQ.md",
        "adapters/amazon-q/.amazonq/mcp.json",
    ),
    "kiro": (
        ".kiro/settings/mcp.json",
        ".kiro/agents",
        ".kiro/hooks",
        ".kiro/steering",
        ".kiro/adop",
        "adapters/kiro/.kiro/settings/mcp.json",
        "adapters/kiro/.kiro/agents",
        "adapters/kiro/.kiro/hooks",
    ),
}

REQUIRED_SHARED_PATHS = (
    "shared/requirements/auditor.py",
    "shared/requirements/capture.py",
    "shared/codegen/renderer.py",
    "shared/logging/agent_tracer.py",
    "shared/utils/structured_logger.py",
    "shared/utils/deployment_checks.py",
    "shared/utils/post_deployment_verifier.py",
    "shared/policies/schema.cedarschema",
    "contracts/v1/run_context.schema.json",
    "runbooks/data-onboarding-agent",
    "mcp-profiles/demo/profile.json",
    "mcp-servers/README.md",
    "tool-registry/servers.yaml",
    "scripts/start_codex.py",
)

# Every platform's onboarding flow must carry the Phase 5 Deploy gates.  The
# workflow text is hand-maintained per platform, so this is what stops one of
# them silently losing the deploy step again.
DEPLOY_PHASE_SURFACES = {
    ".claude/commands/onboard-workflow.md": ("simulate", "active-runs", "Step 5.9"),
    "adapters/claude-code/.claude/commands/onboard-workflow.md": ("simulate", "active-runs", "Step 5.9"),
    "plugins/claude-code/commands/onboard-workflow.md": ("simulate", "active-runs", "Step 5.9"),
    "adapters/claude-code/plugins/claude-code/commands/onboard-workflow.md": (
        "simulate", "active-runs", "Step 5.9",
    ),
    ".codex/skills/command-onboard-workflow/SKILL.md": ("simulate", "active-runs", "Step 5.9"),
    "adapters/codex/.codex/skills/command-onboard-workflow/SKILL.md": (
        "simulate", "active-runs", "Step 5.9",
    ),
    ".kiro/steering/13-workflow-orchestrator.md": ("deploy-check", "simulate", "active-runs", "verify"),
    "adapters/kiro/.kiro/steering/13-workflow-orchestrator.md": (
        "deploy-check", "simulate", "active-runs", "verify",
    ),
}

# The audit-before-deploy hook. One implementation, copied per platform; the
# copies must stay byte-identical and each platform must register it.
DEPLOY_GATE_HOOK = ".claude/hooks/deploy_gate.py"
DEPLOY_GATE_COPIES = (
    ".codex/hooks/deploy_gate.py",
    ".kiro/hooks/deploy_gate.py",
    "adapters/codex/.codex/hooks/deploy_gate.py",
    "adapters/kiro/.kiro/hooks/deploy_gate.py",
    "adapters/claude-code/.claude/hooks/deploy_gate.py",
)

THIRD_PARTY_PROFILES = {
    "snowflake.json": "snowflake-native",
    "databricks.json": "databricks-native",
    "teradata.json": "teradata",
}


def load_json(relative: Path, errors: list[str]) -> dict[str, Any]:
    path = ROOT / relative
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing JSON: {relative}")
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON {relative}: {exc}")
    return {}


def load_toml(relative: Path, errors: list[str]) -> dict[str, Any]:
    path = ROOT / relative
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing TOML: {relative}")
    except tomllib.TOMLDecodeError as exc:
        errors.append(f"invalid TOML {relative}: {exc}")
    return {}


def check_paths(errors: list[str]) -> None:
    for platform, paths in PLATFORM_SURFACES.items():
        for relative in paths:
            if not (ROOT / relative).exists():
                errors.append(f"{platform}: missing surface {relative}")

    for relative in REQUIRED_SHARED_PATHS:
        if not (ROOT / relative).exists():
            errors.append(f"missing shared path {relative}")


def check_active_mcp_profiles(errors: list[str]) -> None:
    canonical = load_json(Path(".mcp.json"), errors)
    servers = canonical.get("mcpServers", {})
    # An exact `mcp_demo.py activate` result is a supported mode; drift checks
    # below still require every client file to agree with .mcp.json.
    demo = active_profile_mode() == "demo"
    if list(servers) != ["aws-mcp"] and not demo:
        errors.append(f".mcp.json must enable only aws-mcp; found {list(servers)}")

    for relative in ACTIVE_JSON_PROFILES:
        profile = load_json(relative, errors)
        if profile != canonical:
            errors.append(f"active JSON MCP profile drift: {relative}")

    canonical_server = servers.get("aws-mcp", {})
    for relative in ACTIVE_CODEX_PROFILES:
        config = load_toml(relative, errors)
        mcp_servers = config.get("mcp_servers", {})
        enabled = [
            name for name, value in mcp_servers.items() if value.get("enabled") is True
        ]
        if enabled != (list(servers) if demo else ["aws-mcp"]):
            errors.append(f"{relative} must enable only aws-mcp; found {enabled}")
        aws_mcp = mcp_servers.get("aws-mcp", {})
        expected_args = canonical_server.get("args", [])
        if aws_mcp.get("command") != canonical_server.get("command"):
            errors.append(f"{relative}: aws-mcp command drift")
        if aws_mcp.get("args") != expected_args:
            errors.append(f"{relative}: aws-mcp args drift")


def check_optional_profiles(errors: list[str]) -> None:
    for relative in OPTIONAL_JSON_PROFILES:
        profile = load_json(relative, errors)
        servers = profile.get("mcpServers", {})
        missing = {"snowflake-native", "databricks-native", "teradata"} - set(servers)
        if missing:
            errors.append(f"{relative}: missing optional providers {sorted(missing)}")

    for relative in OPTIONAL_CODEX_PROFILES:
        profile = load_toml(relative, errors)
        servers = profile.get("mcp_servers", {})
        for name in ("snowflake-native", "databricks-native", "teradata"):
            if name not in servers:
                errors.append(f"{relative}: missing optional provider {name}")
            elif servers[name].get("enabled") is True:
                errors.append(f"{relative}: optional provider enabled: {name}")

    for filename, expected_name in THIRD_PARTY_PROFILES.items():
        relative = Path("mcp-profiles/third-party") / filename
        profile = load_json(relative, errors)
        if profile.get("name") != expected_name:
            errors.append(f"{relative}: profile name is not {expected_name}")
        if profile.get("enabled") is not False:
            errors.append(f"{relative}: profile must remain disabled")
        if set(profile.get("mcpServers", {})) != {expected_name}:
            errors.append(f"{relative}: unexpected server set")


def check_workloads(errors: list[str]) -> None:
    workloads = ROOT / "workloads"
    for workload in sorted(path for path in workloads.iterdir() if path.is_dir()):
        required = ("config", "tests", "run", "logs", "README.md")
        for name in required:
            if not (workload / name).exists():
                errors.append(f"{workload.name}: missing workload surface {name}")


def check_deploy_phase(errors: list[str]) -> None:
    for relative, anchors in DEPLOY_PHASE_SURFACES.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"deploy phase: missing {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        if "deployment_checks" not in text and "deploy-check" not in text:
            errors.append(f"deploy phase: {relative} does not call shared.utils.deployment_checks")
        for anchor in anchors:
            if anchor not in text:
                errors.append(f"deploy phase: {relative} is missing {anchor!r}")


CEDAR_GATE_HOOK = ".claude/hooks/cedar_gate.py"
CEDAR_GATE_COPIES = tuple(path.replace("deploy_gate", "cedar_gate") for path in DEPLOY_GATE_COPIES)
KIRO_CEDAR_PRINCIPALS = {
    "metadata-agent": "metadata",
    "transformation-agent": "transformation",
    "quality-agent": "quality",
    "dag-agent": "dag",
    "ontology-agent": "ontology_staging",
    "requirements-auditor": "requirements_auditor",
    "iac-agent": "iac",
}


def check_cedar_gate(errors: list[str]) -> None:
    """Cedar enforcement: identical hook everywhere, registered, Kiro per-agent principals."""
    source = ROOT / CEDAR_GATE_HOOK
    if not source.is_file():
        errors.append(f"cedar gate: missing {CEDAR_GATE_HOOK}")
        return
    expected = source.read_bytes()
    for relative in CEDAR_GATE_COPIES:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"cedar gate: missing {relative}")
        elif path.read_bytes() != expected:
            errors.append(f"cedar gate: {relative} has drifted from {CEDAR_GATE_HOOK}")
    for relative in (".claude/settings.json", ".codex/hooks.json"):
        config = load_json(Path(relative), errors)
        entries = config.get("hooks", {}).get("PreToolUse", []) if config else []
        if not any("cedar_gate.py" in str(e) and "matcher" not in e for e in entries):
            errors.append(f"cedar gate: {relative} must register cedar_gate.py with no matcher")
    for base in (".kiro/agents", "adapters/kiro/.kiro/agents"):
        for name, principal in KIRO_CEDAR_PRINCIPALS.items():
            config = load_json(Path(base) / f"{name}.json", errors)
            commands = [str(h.get("action", {}).get("command", "")) for h in config.get("hooks", []) or []]
            if f"cedar_gate.py --principal {principal}" not in " ".join(commands):
                errors.append(f"cedar gate: {base}/{name}.json lacks --principal {principal}")
    mode = load_json(Path("shared/policies/enforcement.json"), errors).get("mode")
    if mode not in ("audit", "enforce"):
        errors.append("cedar gate: shared/policies/enforcement.json mode must be audit or enforce")


def check_deploy_gate_hook(errors: list[str]) -> None:
    source = ROOT / DEPLOY_GATE_HOOK
    if not source.is_file():
        errors.append(f"deploy gate: missing {DEPLOY_GATE_HOOK}")
        return
    expected = source.read_bytes()
    for relative in DEPLOY_GATE_COPIES:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"deploy gate: missing {relative}")
        elif path.read_bytes() != expected:
            errors.append(f"deploy gate: {relative} has drifted from {DEPLOY_GATE_HOOK}")

    registrations = {
        ".claude/settings.json": lambda d: any(
            "deploy_gate.py" in str(e) for e in d.get("hooks", {}).get("PreToolUse", [])
        ),
        ".codex/hooks.json": lambda d: any(
            "deploy_gate.py" in str(e) for e in d.get("hooks", {}).get("PreToolUse", [])
        ),
        ".kiro/hooks/adop-gates.json": lambda d: any(
            "deploy_gate.py" in str(h.get("action", {})) and h.get("enabled") is True
            for h in d.get("hooks", [])
        ),
    }
    for relative, registered in registrations.items():
        config = load_json(Path(relative), errors)
        if config and not registered(config):
            errors.append(f"deploy gate: {relative} does not register deploy_gate.py")


def check() -> list[str]:
    errors: list[str] = []
    check_paths(errors)
    check_deploy_phase(errors)
    check_deploy_gate_hook(errors)
    check_cedar_gate(errors)
    check_active_mcp_profiles(errors)
    check_optional_profiles(errors)
    check_workloads(errors)
    return errors


def sync_active_json_profiles() -> list[str]:
    """Make clone-ready JSON profiles identical to the root canonical profile."""

    errors: list[str] = []
    canonical = load_json(Path(".mcp.json"), errors)
    if errors:
        return errors
    rendered = json.dumps(canonical, indent=2) + "\n"
    for relative in ACTIVE_JSON_PROFILES:
        path = ROOT / relative
        if path.read_text(encoding="utf-8") != rendered:
            path.write_text(rendered, encoding="utf-8")
            print(f"updated {relative}")
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "sync"))
    parser.add_argument(
        "--apply",
        action="store_true",
        help="For sync, update clone-ready JSON MCP profiles.",
    )
    args = parser.parse_args()

    if args.command == "sync":
        if not args.apply:
            print("DRY RUN: use --apply to synchronize active JSON MCP profiles")
        else:
            errors = sync_active_json_profiles()
            if errors:
                for error in errors:
                    print(f"FAIL: {error}")
                return 1

    errors = check()
    if errors:
        print(f"FAIL: {len(errors)} platform structure problem(s)")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("PASS: clone-ready Claude Code, Codex, Amazon Q, and Kiro surfaces are aligned")
    print("PASS: active MCP profiles are AWS-only; optional providers remain disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
