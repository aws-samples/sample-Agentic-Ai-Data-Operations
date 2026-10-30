"""Strands runtime obeys the same Cedar policies as Claude Code, Codex and Kiro."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtimes" / "strands"))

pytest.importorskip("strands", reason="needs the optional strands extra")
pytest.importorskip("cedarpy")

from strands.hooks import BeforeToolCallEvent, HookRegistry  # noqa: E402

import shared.utils.cedar_gate as gate  # noqa: E402
from adop_strands.cedar_hook import CedarToolGate  # noqa: E402

W = "workloads/orders"


@pytest.fixture(autouse=True)
def enforce(tmp_path, monkeypatch):
    mode = tmp_path / "enforcement.json"
    mode.write_text(json.dumps({"mode": "enforce"}))
    monkeypatch.setattr(gate, "MODE_FILE", mode)
    monkeypatch.setattr(gate, "DECISION_LOG", tmp_path / "decisions.jsonl")


def _fire(agent_name: str, tool: str, tool_input: dict) -> BeforeToolCallEvent:
    registry = HookRegistry()
    registry.add_hook(CedarToolGate(ROOT, agent_name))
    event = BeforeToolCallEvent(
        agent=None, selected_tool=None,
        tool_use={"toolUseId": "t1", "name": tool, "input": tool_input},
        invocation_state={},
    )
    registry.invoke_callbacks(event)
    return event


@pytest.mark.parametrize(
    "agent,path",
    [
        ("adop-build-metadata", f"{W}/config/source.yaml"),
        ("adop-build-transform", f"{W}/config/transformations.yaml"),
        ("adop-build-quality", f"{W}/tests/unit/test_quality.py"),
        ("adop-build-dag", f"{W}/config/dag_spec.json"),
    ],
)
def test_documented_outputs_proceed(agent: str, path: str) -> None:
    event = _fire(agent, "fs_write", {"path": path, "file_text": "a: 1\n"})
    assert event.cancel_tool is False


@pytest.mark.parametrize(
    "agent,tool,tool_input",
    [
        ("adop-build-metadata", "fs_write", {"path": f"{W}/dags/x.py", "file_text": "x"}),
        ("adop-build-metadata", "fs_write", {"path": "shared/policies/x.cedar", "file_text": "x"}),
        ("adop-build-quality", "fs_write", {"path": f"{W}/run/context.json", "file_text": "{}"}),
        ("adop-build-metadata", "render_artifact",
         {"spec_path": f"{W}/config/dag.yaml", "spec_type": "dag", "template_id": "airflow_dag",
          "output_path": f"{W}/dags/orders_dag.py"}),
        ("adop-build-transform", "fs_write",
         {"path": f"{W}/config/source.yaml", "file_text": "key: " + "AKIA" + "ABCDEFGHIJKLMNOP"}),
    ],
)
def test_policy_violations_are_cancelled(agent: str, tool: str, tool_input: dict) -> None:
    event = _fire(agent, tool, tool_input)
    assert isinstance(event.cancel_tool, str) and "Cedar policy denies" in event.cancel_tool


def test_render_artifact_is_governed_by_output_path() -> None:
    allowed = _fire("adop-build-dag", "render_artifact",
                    {"spec_path": f"{W}/config/dag.yaml", "spec_type": "dag",
                     "template_id": "airflow_dag", "output_path": f"{W}/dags/orders_dag.py"})
    assert allowed.cancel_tool is False


def test_reads_and_test_gates_are_not_blocked() -> None:
    assert _fire("adop-build-metadata", "fs_read", {"path": "shared/policies/schema.cedarschema"}).cancel_tool is False
    assert _fire("adop-build-metadata", "run_pytest_gate", {"selector": f"{W}/tests"}).cancel_tool is False


def test_gate_failure_cancels_instead_of_allowing() -> None:
    def broken(*_):
        raise RuntimeError("engine down")

    registry = HookRegistry()
    registry.add_hook(CedarToolGate(ROOT, "adop-build-metadata", decider=broken))
    event = BeforeToolCallEvent(agent=None, selected_tool=None,
                                tool_use={"toolUseId": "t", "name": "fs_write",
                                          "input": {"path": f"{W}/config/a.yaml", "file_text": "a"}},
                                invocation_state={})
    registry.invoke_callbacks(event)
    assert "Cedar gate failed" in str(event.cancel_tool)


def test_every_strands_agent_maps_to_a_cedar_principal() -> None:
    for path in sorted((ROOT / ".amazonq" / "cli-agents").glob("adop-*.json")):
        principal, _ = gate.resolve_principal({}, path.stem)
        expected_general = path.stem in {"adop-reviewer"}
        assert (principal == "general") == expected_general, f"{path.stem} -> {principal}"


def test_runner_attaches_the_gate_to_every_agent() -> None:
    source = (ROOT / "runtimes/strands/adop_strands/runner.py").read_text()
    assert "hooks=[CedarToolGate(self.repo_root, invocation.agent)]" in source
