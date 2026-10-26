from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.orchestration.workflow_driver import AgentInvocation, WorkflowDriver, _blocking_markers
from runtimes.strands.adop_strands.definitions import DefinitionLoader
from runtimes.strands.adop_strands.runner import StrandsRunner
from runtimes.strands.adop_strands.tools import check_write


ROOT = Path(__file__).resolve().parents[3]


def test_all_adop_definitions_are_loadable() -> None:
    loader = DefinitionLoader(ROOT)
    names = loader.names()
    assert "adop-build-metadata" in names
    assert "adop-build-quality" in names
    assert "adop-reviewer" in names
    for name in names:
        definition = loader.load(name)
        assert definition.name == name
        assert definition.prompt


def test_dry_run_returns_the_shared_agent_output_contract() -> None:
    runner = StrandsRunner(ROOT, dry_run=True)
    output = runner.invoke(
        AgentInvocation("adop-build-metadata", "test", "metadata")
    )
    assert output.status == "success"
    assert output.decisions
    assert output.can_proceed


def test_workflow_driver_accepts_a_typed_strands_backend(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    workload = "example_workload"
    driver = WorkflowDriver(
        workload,
        "run-test",
        repo_root=tmp_path,
        agent_backend=StrandsRunner(ROOT, dry_run=True).invoke,
    )
    result = driver.run_agent(
        AgentInvocation("adop-build-metadata", "test", "metadata")
    )
    assert result.can_proceed
    handoff = tmp_path / "workloads" / workload / ".handoffs" / "metadata.json"
    assert handoff.is_file()
    payload = json.loads(handoff.read_text(encoding="utf-8"))
    assert payload["status"] == "success"


def test_runner_stamps_identity_over_model_output() -> None:
    runner = StrandsRunner(ROOT, dry_run=True, workload="wl", run_id="run-42")
    output = runner._dry_output(AgentInvocation("adop-build-dag", "t", "dag"))
    output.run_id, output.agent_name = "invented-by-model", "Some Agent"
    stamped = runner._stamp(
        output, AgentInvocation("adop-build-dag", "t", "dag"), "2026-01-01T00:00:00+00:00"
    )
    assert stamped.run_id == "run-42"
    assert stamped.agent_name == "adop-build-dag"
    assert stamped.workload_name == "wl"
    assert stamped.started_at == "2026-01-01T00:00:00+00:00"


@pytest.mark.parametrize("path", [
    "workloads/wl/run/context.json",
    "workloads/wl/run/requirements.jsonl",
    "workloads/wl/run/discovery_complete.json",
    "workloads/wl/.discovery_complete",
    "workloads/wl/dags/wl_dag.py",
    "workloads/wl/scripts/transform/x.py",
    "workloads/wl/MANUAL_DAG_wl.py",
    "README.md",
])
def test_fs_write_denies_protected_paths(path: str) -> None:
    with pytest.raises(PermissionError):
        check_write(path, ("workloads/**",))


@pytest.mark.parametrize("path", [
    "workloads/wl/config/source.yaml",
    "workloads/wl/run/decisions.jsonl",
    "workloads/wl/tests/unit/test_dag.py",
])
def test_fs_write_allows_agent_paths(path: str) -> None:
    check_write(path, ("workloads/**",))


def test_reviewer_gate_matches_bold_severity_markers() -> None:
    content = "### Finding 1\n**Severity:** HIGH\n"
    assert _blocking_markers(content, ["Severity: High", "Severity: HIGH"])
    assert not _blocking_markers("**Severity:** MEDIUM", ["Severity: HIGH"])
