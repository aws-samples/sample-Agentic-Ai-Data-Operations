from __future__ import annotations

import json
from pathlib import Path

import pytest

import shared.utils.cedar_gate as cedar_gate
from shared.control_plane.workspace_context import (
    available_workspaces,
    authorize,
    current_context,
    login,
    main,
    select_workspace,
)


def test_project_user_can_select_only_their_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session_path = tmp_path / "session.json"
    monkeypatch.setenv("ADOP_WORKSPACE_SESSION", str(session_path))

    session = login("oliver.orders@example.com", "project/orders")
    assert session["workspace"] == {"level": "project", "name": "orders"}
    assert [item["name"] for item in available_workspaces(session["identity"])] == ["orders"]

    with pytest.raises(PermissionError, match="do not have access"):
        select_workspace("project/claims")


def test_hcherian_alias_has_organization_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADOP_WORKSPACE_SESSION", str(tmp_path / "session.json"))

    session = login("hcherian", "organization/default")

    assert session["identity"]["email"] == "hcherian@example.com"
    assert session["identity"]["role"] == "org-admin"
    assert session["workspace"] == {"level": "organization", "name": "default"}


def test_domain_owner_can_select_domain_and_projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADOP_WORKSPACE_SESSION", str(tmp_path / "session.json"))
    session = login("sara.sales@example.com")

    assert {item["name"] for item in available_workspaces(session["identity"])} == {
        "sales",
        "orders",
        "claims",
        "sales_daily",
    }
    assert authorize(session, workload="customer_orders") == (
        False,
        "No workspace selected. Ask the user to choose an ADOP workspace first.",
    )

    selected = select_workspace("domain/sales")
    assert authorize(selected, workload="customer_orders") == (True, "")
    assert authorize(selected, workload="claims") == (True, "")


def test_scoped_agent_actions_require_an_identity():
    assert authorize({}, workload="customer_orders") == (
        False,
        "No ADOP identity is active. Run `adop login` and select a workspace.",
    )
    assert authorize({}, scope={"level": "project", "name": "orders"}) == (
        False,
        "No ADOP identity is active. Run `adop login` and select a workspace.",
    )


def test_workspace_session_is_outside_repository_and_has_no_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    session_path = tmp_path / "session.json"
    monkeypatch.setenv("ADOP_WORKSPACE_SESSION", str(session_path))
    session = login("oliver.orders@example.com", "project/orders")
    session["access_token"] = "must-not-persist"
    session_path.write_text(json.dumps(session), encoding="utf-8")

    loaded = current_context()
    assert loaded["workspace"] == {"level": "project", "name": "orders"}
    assert "access_token" not in loaded


def test_cedar_gate_blocks_cross_project_workload_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    session_path = tmp_path / "session.json"
    monkeypatch.setenv("ADOP_WORKSPACE_SESSION", str(session_path))
    login("oliver.orders@example.com", "project/orders")
    monkeypatch.setattr(cedar_gate, "MODE_FILE", tmp_path / "enforcement.json")
    cedar_gate.MODE_FILE.write_text('{"mode":"audit"}', encoding="utf-8")
    monkeypatch.setattr(cedar_gate, "DECISION_LOG", tmp_path / "cedar.jsonl")

    event = {
        "tool_name": "fs_write",
        "tool_input": {
            "path": "workloads/claims/config/source.yaml",
            "file_text": "dataset_name: claims\n",
        },
        "cwd": str(Path(__file__).resolve().parents[3]),
    }
    allowed, reason, record = cedar_gate.decide(event)

    assert allowed is False
    assert "workspace isolation" in reason
    assert record["workspace_denied"] is True
    assert record["workspace"] == {"level": "project", "name": "orders"}


def test_cedar_gate_allows_selected_project_workload_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ADOP_WORKSPACE_SESSION", str(tmp_path / "session.json"))
    login("oliver.orders@example.com", "project/orders")
    monkeypatch.setattr(cedar_gate, "MODE_FILE", tmp_path / "enforcement.json")
    cedar_gate.MODE_FILE.write_text('{"mode":"audit"}', encoding="utf-8")
    monkeypatch.setattr(cedar_gate, "DECISION_LOG", tmp_path / "cedar.jsonl")

    event = {
        "tool_name": "fs_write",
        "tool_input": {
            "path": "workloads/customer_orders/config/source.yaml",
            "file_text": "dataset_name: customer_orders\n",
        },
        "cwd": str(Path(__file__).resolve().parents[3]),
    }
    allowed, reason, record = cedar_gate.decide(event)

    assert allowed is True
    assert "workspace isolation" not in reason
    assert record["workspace_denied"] is False


def test_cedar_gate_blocks_cross_project_read_and_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ADOP_WORKSPACE_SESSION", str(tmp_path / "session.json"))
    login("oliver.orders@example.com", "project/orders")
    monkeypatch.setattr(cedar_gate, "MODE_FILE", tmp_path / "enforcement.json")
    cedar_gate.MODE_FILE.write_text('{"mode":"audit"}', encoding="utf-8")
    monkeypatch.setattr(cedar_gate, "DECISION_LOG", tmp_path / "cedar.jsonl")

    event = {
        "tool_name": "grep",
        "tool_input": {
            "path": "workloads/claims",
            "pattern": "customer_id",
        },
        "cwd": str(Path(__file__).resolve().parents[3]),
    }
    allowed, reason, record = cedar_gate.decide(event)

    assert allowed is False
    assert "workspace isolation" in reason
    assert record["workspace_denied"] is True


def test_session_hook_explains_selection_and_is_machine_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setenv("ADOP_WORKSPACE_SESSION", str(tmp_path / "session.json"))
    login("oliver.orders@example.com", "project/orders")

    assert main(["hook-session", "--cwd", str(Path(__file__).resolve().parents[3])]) == 0
    payload = json.loads(capsys.readouterr().out)
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert "project/orders" in context
    assert "isolation" in context
