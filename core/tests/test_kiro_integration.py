import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run(path: str, payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, path],
        cwd=ROOT,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


def test_packaged_kiro_capture_is_standalone():
    result = _run(
        "adapters/kiro/.kiro/hooks/capture_user_turn.py",
        {"workload_name": "unknown_workload", "prompt": "hello"},
    )
    assert result.returncode == 0


def test_kiro_renderer_lists_templates():
    result = subprocess.run(
        [sys.executable, "adapters/kiro/.kiro/adop/render.py", "--list"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "silver_transform" in result.stdout


def test_kiro_phase_gate_denies_missing_discovery():
    result = _run(
        "adapters/kiro/.kiro/hooks/phase_gate.py",
        {"tool_name": "Agent", "tool_input": {"workload_name": "missing_workload"}},
    )
    assert result.returncode == 0
    assert '"permissionDecision": "deny"' in result.stdout


def test_kiro_auditor_write_scope_denies_artifact_write():
    result = _run(
        "adapters/kiro/.kiro/hooks/auditor_write_gate.py",
        {
            "agent_name": "requirements-auditor",
            "tool_input": {"path": "workloads/demo/config/source.yaml"},
        },
    )
    assert result.returncode == 0
    assert '"permissionDecision": "deny"' in result.stdout
