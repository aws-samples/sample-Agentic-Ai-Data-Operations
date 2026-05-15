"""Tests for tool-registry consistency.

Verifies:
- servers.yaml matches .mcp.json
- No stale server names in Markdown
- All invariants have valid structure
- Server categories and types are valid
"""

import json
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_DIR = ROOT / "tool-registry"
MCP_JSON = ROOT / ".mcp.json"
MARKDOWN_FILES = [
    ROOT / "TOOL_ROUTING.md",
    ROOT / "MCP_GUARDRAILS.md",
    ROOT / "CLAUDE.md",
]
STALE_NAMES = ["aws-dataprocessing", "verified-permissions", "aws.dp-mcp"]


@pytest.fixture
def mcp_server_names():
    with open(MCP_JSON) as f:
        data = json.load(f)
    return set(data.get("mcpServers", {}).keys())


@pytest.fixture
def servers_yaml():
    with open(REGISTRY_DIR / "servers.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture
def invariants_yaml():
    with open(REGISTRY_DIR / "invariants.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture
def markdown_content():
    content = ""
    for md_file in MARKDOWN_FILES:
        if md_file.exists():
            content += md_file.read_text()
    return content


class TestServerSync:
    def test_all_mcp_json_servers_in_registry(self, mcp_server_names, servers_yaml):
        yaml_names = {s["name"] for s in servers_yaml["servers"]}
        missing = mcp_server_names - yaml_names
        assert not missing, f"Servers in .mcp.json but not in servers.yaml: {missing}"

    def test_all_registry_servers_in_mcp_json(self, mcp_server_names, servers_yaml):
        yaml_names = {s["name"] for s in servers_yaml["servers"]}
        extra = yaml_names - mcp_server_names
        assert not extra, f"Servers in servers.yaml but not in .mcp.json: {extra}"

    def test_server_count_matches(self, mcp_server_names, servers_yaml):
        assert len(servers_yaml["servers"]) == len(mcp_server_names)


class TestServerStructure:
    def test_valid_categories(self, servers_yaml):
        valid = {"REQUIRED", "WARN", "OPTIONAL"}
        for server in servers_yaml["servers"]:
            assert server["category"] in valid, (
                f"{server['name']} has invalid category: {server['category']}"
            )

    def test_valid_types(self, servers_yaml):
        valid = {"custom", "pypi"}
        for server in servers_yaml["servers"]:
            assert server["type"] in valid, (
                f"{server['name']} has invalid type: {server['type']}"
            )

    def test_pypi_servers_have_package(self, servers_yaml):
        for server in servers_yaml["servers"]:
            if server["type"] == "pypi":
                assert "package" in server, (
                    f"{server['name']} is pypi but missing 'package'"
                )

    def test_custom_servers_have_location(self, servers_yaml):
        for server in servers_yaml["servers"]:
            if server["type"] == "custom":
                assert "location" in server, (
                    f"{server['name']} is custom but missing 'location'"
                )

    def test_all_servers_have_tools(self, servers_yaml):
        for server in servers_yaml["servers"]:
            assert "tools" in server and len(server["tools"]) > 0, (
                f"{server['name']} has no tools listed"
            )

    def test_all_servers_have_use_for(self, servers_yaml):
        for server in servers_yaml["servers"]:
            assert "use_for" in server and server["use_for"], (
                f"{server['name']} missing use_for description"
            )

    def test_all_servers_have_fallback(self, servers_yaml):
        for server in servers_yaml["servers"]:
            assert "fallback" in server, (
                f"{server['name']} missing fallback"
            )

    def test_no_duplicate_server_names(self, servers_yaml):
        names = [s["name"] for s in servers_yaml["servers"]]
        assert len(names) == len(set(names)), "Duplicate server names found"


class TestStaleReferences:
    @pytest.mark.parametrize("stale_name", STALE_NAMES)
    def test_no_stale_server_in_markdown(self, stale_name, markdown_content):
        assert stale_name not in markdown_content, (
            f"Stale server name '{stale_name}' found in Markdown docs"
        )


class TestInvariants:
    def test_invariants_have_required_fields(self, invariants_yaml):
        for rule in invariants_yaml["rules"]:
            assert "id" in rule, f"Rule missing 'id': {rule}"
            assert "rule" in rule, f"Rule missing 'rule': {rule.get('id')}"
            assert "severity" in rule, f"Rule missing 'severity': {rule.get('id')}"

    def test_invariant_severities_valid(self, invariants_yaml):
        valid = {"BLOCK", "WARN"}
        for rule in invariants_yaml["rules"]:
            assert rule["severity"] in valid, (
                f"Invariant '{rule['id']}' has invalid severity: {rule['severity']}"
            )

    def test_no_duplicate_invariant_ids(self, invariants_yaml):
        ids = [r["id"] for r in invariants_yaml["rules"]]
        assert len(ids) == len(set(ids)), "Duplicate invariant IDs found"

    def test_invariant_count(self, invariants_yaml):
        assert len(invariants_yaml["rules"]) == 11
