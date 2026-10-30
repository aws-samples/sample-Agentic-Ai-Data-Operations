"""Codex workflow routing must use the declared ADOP specialist contracts."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ONBOARDING = ROOT / ".codex/skills/command-onboard-workflow/SKILL.md"
DEVOPS = ROOT / ".codex/skills/command-devops-workflow/SKILL.md"
AGENTS = ROOT / ".codex/agents"


SPECIALISTS = {
    "metadata-agent",
    "quality-agent",
    "transformation-agent",
    "dag-agent",
    "ontology-agent",
    "iac-agent",
    "requirements-auditor",
}


def test_named_specialist_contracts_exist() -> None:
    for name in SPECIALISTS:
        assert (AGENTS / f"{name}.toml").is_file(), name


def test_onboarding_routes_build_responsibilities_to_named_specialists() -> None:
    text = ONBOARDING.read_text(encoding="utf-8")

    assert "Never use `default` for metadata" in text
    assert "### Named specialist routing" in text
    for name in SPECIALISTS:
        assert f"`{name}`" in text

    expected_labels = {
        "metadata-agent": r"Metadata \(`metadata-agent`\)",
        "quality-agent": r"Quality \(`quality-agent`\)",
        "transformation-agent": r"Transformation \(`transformation-agent`\)",
        "dag-agent": r"DAG \(`dag-agent`\)",
        "ontology-agent": r"Ontology \(`ontology-agent`\)",
        "requirements-auditor": (
            r"Requirements Conformance Audit "
            r"\(`requirements-auditor`, sequential, `high`\)"
        ),
    }
    for name, label in expected_labels.items():
        assert re.search(label, text), name


def test_devops_preserves_named_iac_routing() -> None:
    text = DEVOPS.read_text(encoding="utf-8")

    assert "The named role is mandatory" in text
    assert '**IaC Generator(s)** — after the audit passes' in text
    assert 'spawn one `iac-agent` per selected format' in text


def test_devops_gates_iac_on_audit_and_human_format_selection() -> None:
    text = DEVOPS.read_text(encoding="utf-8")

    assert "Step 2.1: Requirements Audit and Product Inventory" in text
    assert "If the audit is not `pass`, stop" in text
    assert "iac_target_frameworks" in text
    assert "deployment_target_products" in text
    assert "Do not create resources for products outside target_products" in text
