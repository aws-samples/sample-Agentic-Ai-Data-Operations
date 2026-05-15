#!/usr/bin/env python3
"""Validates tool-registry/ YAML against .mcp.json and Markdown docs.

Checks:
1. Every server in .mcp.json exists in servers.yaml and vice versa
2. No stale server names referenced in Markdown files
3. All invariant IDs are referenced in at least one Markdown file
4. Server count consistency
"""

import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_DIR = ROOT / "tool-registry"
MCP_JSON = ROOT / ".mcp.json"
MARKDOWN_FILES = [
    ROOT / "TOOL_ROUTING.md",
    ROOT / "MCP_GUARDRAILS.md",
    ROOT / "CLAUDE.md",
]
STALE_NAMES = ["aws-dataprocessing", "verified-permissions", "aws.dp-mcp"]


def load_mcp_json() -> set[str]:
    with open(MCP_JSON) as f:
        data = json.load(f)
    return set(data.get("mcpServers", {}).keys())


def load_servers_yaml() -> tuple[list[dict], set[str]]:
    with open(REGISTRY_DIR / "servers.yaml") as f:
        data = yaml.safe_load(f)
    servers = data.get("servers", [])
    names = {s["name"] for s in servers}
    return servers, names


def load_invariants_yaml() -> list[dict]:
    with open(REGISTRY_DIR / "invariants.yaml") as f:
        data = yaml.safe_load(f)
    return data.get("rules", [])


def read_markdown_content() -> str:
    content = ""
    for md_file in MARKDOWN_FILES:
        if md_file.exists():
            content += md_file.read_text()
    return content


def check_server_sync(mcp_names: set[str], yaml_names: set[str]) -> list[str]:
    errors = []
    in_mcp_not_yaml = mcp_names - yaml_names
    in_yaml_not_mcp = yaml_names - mcp_names

    if in_mcp_not_yaml:
        errors.append(
            f"Servers in .mcp.json but NOT in servers.yaml: {sorted(in_mcp_not_yaml)}"
        )
    if in_yaml_not_mcp:
        errors.append(
            f"Servers in servers.yaml but NOT in .mcp.json: {sorted(in_yaml_not_mcp)}"
        )
    return errors


def check_stale_references(md_content: str) -> list[str]:
    errors = []
    for name in STALE_NAMES:
        if name in md_content:
            for md_file in MARKDOWN_FILES:
                if md_file.exists() and name in md_file.read_text():
                    errors.append(
                        f"Stale server name '{name}' found in {md_file.name}"
                    )
    return errors


def check_invariants_referenced(invariants: list[dict], md_content: str) -> list[str]:
    warnings = []
    for rule in invariants:
        rule_id = rule["id"]
        if rule_id not in md_content:
            keywords = rule["rule"].split()[:4]
            keyword_match = any(kw.lower() in md_content.lower() for kw in keywords if len(kw) > 4)
            if not keyword_match:
                warnings.append(
                    f"Invariant '{rule_id}' not referenced in any Markdown file"
                )
    return warnings


def check_server_count(servers: list[dict], mcp_names: set[str]) -> list[str]:
    errors = []
    if len(servers) != len(mcp_names):
        errors.append(
            f"Server count mismatch: servers.yaml has {len(servers)}, "
            f".mcp.json has {len(mcp_names)}"
        )
    return errors


def check_categories(servers: list[dict]) -> list[str]:
    errors = []
    valid_categories = {"REQUIRED", "WARN", "OPTIONAL"}
    for s in servers:
        if s.get("category") not in valid_categories:
            errors.append(
                f"Server '{s['name']}' has invalid category: {s.get('category')}"
            )
    return errors


def check_types(servers: list[dict]) -> list[str]:
    errors = []
    valid_types = {"custom", "pypi"}
    for s in servers:
        if s.get("type") not in valid_types:
            errors.append(
                f"Server '{s['name']}' has invalid type: {s.get('type')}"
            )
        if s.get("type") == "pypi" and not s.get("package"):
            errors.append(
                f"Server '{s['name']}' is type=pypi but missing 'package' field"
            )
        if s.get("type") == "custom" and not s.get("location"):
            errors.append(
                f"Server '{s['name']}' is type=custom but missing 'location' field"
            )
    return errors


def main() -> int:
    errors = []
    warnings = []

    mcp_names = load_mcp_json()
    servers, yaml_names = load_servers_yaml()
    invariants = load_invariants_yaml()
    md_content = read_markdown_content()

    errors.extend(check_server_sync(mcp_names, yaml_names))
    errors.extend(check_server_count(servers, mcp_names))
    errors.extend(check_categories(servers))
    errors.extend(check_types(servers))
    errors.extend(check_stale_references(md_content))
    warnings.extend(check_invariants_referenced(invariants, md_content))

    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠ {w}")

    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors:
            print(f"  ✗ {e}")
        return 1

    server_count = len(servers)
    invariant_count = len(invariants)
    categories = {}
    for s in servers:
        cat = s["category"]
        categories[cat] = categories.get(cat, 0) + 1

    print(f"OK: {server_count} servers ({categories}), {invariant_count} invariants")
    if warnings:
        print(f"   ({len(warnings)} warnings — see above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
