"""The requirements audit is a hard gate on deployment, on every platform.

The audit itself is covered by test_requirements_auditor.py. These tests cover
enforcement: that a missing, failing, mismatched or stale audit blocks the
Phase 5 deploy path, and that the PreToolUse hook blocks the AWS calls that
would otherwise go around it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.utils import deployment_checks as dc  # noqa: E402
from shared.utils.deployment_guardrails import DeploymentGuardrailError  # noqa: E402

HOOK = ROOT / ".claude" / "hooks" / "deploy_gate.py"
AUDIT_PASS = {"status": "pass", "run_id": "run-1", "audit_id": "audit-1"}
AWS_GLUE_CREATE = "aws" + " glue create-job"  # split so the hook's own matcher ignores this file


def _workload(tmp_path: Path, audit: dict | None = AUDIT_PASS) -> Path:
    """A minimal workload tree with its own fake repo root."""
    workload = tmp_path / "workloads" / "orders"
    (workload / "run").mkdir(parents=True)
    (workload / "config").mkdir()
    (workload / "config" / "source.yaml").write_text("name: orders\n", encoding="utf-8")
    (workload / "run" / "context.json").write_text(
        json.dumps({"run_id": "run-1", "workload_name": "orders"}), encoding="utf-8"
    )
    if audit is not None:
        (workload / "run" / "requirements_audit.json").write_text(
            json.dumps(audit), encoding="utf-8"
        )
    # Real shared/ so the hook loads the real gate, with fixture workloads.
    shared = tmp_path / "shared"
    if not shared.exists():
        shared.symlink_to(ROOT / "shared")
    return workload


# ── require_passing_audit ───────────────────────────────────────────────────


def test_missing_audit_blocks(tmp_path: Path) -> None:
    with pytest.raises(DeploymentGuardrailError, match="run the requirements-auditor"):
        dc.require_passing_audit(_workload(tmp_path, audit=None))


def test_blocked_audit_blocks_and_counts_issues(tmp_path: Path) -> None:
    workload = _workload(
        tmp_path, audit={"status": "blocked", "run_id": "run-1", "blocking_issues": ["x", "y"]}
    )
    with pytest.raises(DeploymentGuardrailError, match="2 blocking issue"):
        dc.require_passing_audit(workload)


def test_audit_from_a_different_run_blocks(tmp_path: Path) -> None:
    workload = _workload(tmp_path, audit={"status": "pass", "run_id": "run-OLD"})
    with pytest.raises(DeploymentGuardrailError, match="current run is 'run-1'"):
        dc.require_passing_audit(workload)


def test_passing_current_audit_is_accepted(tmp_path: Path) -> None:
    assert dc.require_passing_audit(_workload(tmp_path))["audit_id"] == "audit-1"


def test_artifact_changed_after_the_audit_makes_it_stale(tmp_path: Path) -> None:
    workload = _workload(tmp_path)
    report = workload / "run" / "requirements_audit.json"
    changed = workload / "config" / "source.yaml"
    changed.write_text("name: orders\nextra: smuggled\n", encoding="utf-8")
    newer = report.stat().st_mtime + 10
    os.utime(changed, (newer, newer))
    with pytest.raises(DeploymentGuardrailError, match="stale"):
        dc.require_passing_audit(workload)


def test_appending_to_the_ledger_does_not_make_the_audit_stale(tmp_path: Path) -> None:
    """The auditor appends to decisions/traces itself; that must not self-invalidate."""
    workload = _workload(tmp_path)
    report = workload / "run" / "requirements_audit.json"
    newer = report.stat().st_mtime + 10
    for name in ("requirements.jsonl", "decisions.jsonl"):
        path = workload / "run" / name
        path.write_text("{}\n", encoding="utf-8")
        os.utime(path, (newer, newer))
    assert dc.require_passing_audit(workload)["status"] == "pass"


# ── deploy gate record ──────────────────────────────────────────────────────


def test_deploy_gate_requires_preflight_and_tracks_the_audit(tmp_path: Path) -> None:
    workload = _workload(tmp_path)
    assert "no passing deploy gate" in (dc.deploy_gate_open(workload) or "")

    dc.write_deploy_gate(workload, dc.require_passing_audit(workload))
    assert dc.deploy_gate_open(workload) is None

    (workload / "run" / "requirements_audit.json").write_text(
        json.dumps({"status": "pass", "run_id": "run-1", "audit_id": "audit-2"}),
        encoding="utf-8",
    )
    assert "predates the latest audit" in (dc.deploy_gate_open(workload) or "")


def test_preflight_cli_blocks_without_an_audit_and_writes_no_gate(tmp_path: Path) -> None:
    workload = _workload(tmp_path, audit=None)
    code = dc.main(["preflight", "--context", str(workload / "run" / "context.json")])
    assert code == 2
    assert not (workload / "run" / "deploy_gate.json").exists()


# ── PreToolUse hook ─────────────────────────────────────────────────────────


def _hook(tool_name: str, tool_input: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": tool_name, "tool_input": tool_input, "cwd": str(cwd)}),
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )


@pytest.mark.parametrize(
    "tool_name,tool_input",
    [
        ("mcp__glue-athena__create_job", {"job_name": "orders_silver"}),
        ("mcp__glue-athena__start_job_run", {"job_name": "orders_silver"}),
        ("mcp__glue-athena__create_table", {"database": "orders_db"}),
        ("mcp__iam__put_role_policy", {"role_name": "orders-glue-service-role"}),
        ("mcp__lakeformation__grant_permissions", {"database": "orders_db"}),
        ("mcp__lakeformation__add_lf_tags_to_resource", {"database": "orders_db"}),
        ("Bash", {"command": AWS_GLUE_CREATE + " --name orders_silver"}),
        ("Bash", {"command": "set -e && " + AWS_GLUE_CREATE + " --name orders_silver"}),
        ("Bash", {"command": "aws" + " s3 cp dags/orders_dag.py s3://mwaa-env/dags/"}),
        ("call_aws", {"command": "glue create-job --name orders_silver"}),
        ("mcp__aws-mcp__call_aws", {"service": "s3", "operation": "put_object",
                                     "key": "dags/orders_dag.py", "workload": "orders"}),
        ("mcp__aws-mcp__run_script",
         {"script": "aws s3 cp dags/orders_dag.py s3://mwaa-env/dags/orders_dag.py",
          "workload": "orders"}),
        ("Bash", {"command": "aws s3api put-object --bucket mwaa-env "
                            "--key dags/orders_dag.py --body dag.py"}),
        ("mcp__lakeformation__revoke_permissions", {"database": "orders_db"}),
        ("mcp__lakeformation__create_lf_tag", {"tag_key": "PII_Type", "workload": "orders"}),
        ("use_aws", {"service_name": "glue", "operation_name": "create_job",
                     "workload": "orders"}),
    ],
)
def test_hook_denies_deploy_calls_without_a_gate(
    tmp_path: Path, tool_name: str, tool_input: dict
) -> None:
    _workload(tmp_path)
    result = _hook(tool_name, tool_input, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "requirements audit must pass" in result.stdout
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize(
    "tool_name,tool_input",
    [
        ("Read", {"file_path": "workloads/orders/config/source.yaml"}),
        ("Write", {"file_path": "workloads/orders/config/source.yaml", "content": "x"}),
        ("Bash", {"command": "aws" + " glue get-job --job-name orders_silver"}),
        ("Bash", {"command": "aws" + " glue get-job-runs --job-name orders_silver"}),
        ("Bash", {"command": "python3 -m pytest core/tests"}),
        ("Bash", {"command": "aws" + " s3 cp scripts/transform/x.py s3://artifacts/"}),
        ("mcp__glue-athena__get_table", {"database": "orders_db", "table": "silver"}),
        ("mcp__iam__simulate_principal_policy", {"role": "orders-glue-service-role"}),
        ("mcp__glue-athena__get_job_runs", {"job_name": "orders_silver"}),
    ],
)
def test_hook_allows_reads_and_non_deploy_calls(
    tmp_path: Path, tool_name: str, tool_input: dict
) -> None:
    _workload(tmp_path)
    result = _hook(tool_name, tool_input, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "command",
    [
        # Writing a deploy string into a file is data, not a deploy call.
        "cat > notes.md <<'EOF'\n" + AWS_GLUE_CREATE + " --name x\nEOF",
        "grep -rn '" + AWS_GLUE_CREATE + "' docs/",
        "echo 'run " + AWS_GLUE_CREATE + " later' >> TODO.md",
    ],
)
def test_hook_does_not_fire_on_deploy_strings_that_are_only_data(
    tmp_path: Path, command: str
) -> None:
    _workload(tmp_path)
    result = _hook("Bash", {"command": command}, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_hook_allows_the_deploy_call_once_the_gate_is_written(tmp_path: Path) -> None:
    workload = _workload(tmp_path)
    dc.write_deploy_gate(workload, dc.require_passing_audit(workload))
    result = _hook("mcp__glue-athena__create_job", {"job_name": "orders_silver"}, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_hook_requires_a_workload_match_even_when_another_gate_is_open(tmp_path: Path) -> None:
    workload = _workload(tmp_path)
    dc.write_deploy_gate(workload, dc.require_passing_audit(workload))
    result = _hook(
        "mcp__glue-athena__create_job",
        {"job_name": "unrelated_job"},
        tmp_path,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "cannot identify a workload" in result.stdout


def test_hook_fails_closed_when_the_shared_module_is_unreachable(tmp_path: Path) -> None:
    """A gate that cannot reach its own implementation must deny, not allow."""
    bare = tmp_path / "nowhere"
    bare.mkdir()
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(
            {
                "tool_name": "mcp__glue-athena__create_job",
                "tool_input": {"job_name": "x"},
                "cwd": str(bare),
            }
        ),
        text=True,
        capture_output=True,
        cwd=bare,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr


def test_hook_is_identical_across_platforms() -> None:
    expected = HOOK.read_bytes()
    copies = [
        ROOT / ".codex" / "hooks" / "deploy_gate.py",
        ROOT / ".kiro" / "hooks" / "deploy_gate.py",
        ROOT / "adapters" / "codex" / ".codex" / "hooks" / "deploy_gate.py",
        ROOT / "adapters" / "kiro" / ".kiro" / "hooks" / "deploy_gate.py",
        ROOT / "adapters" / "claude-code" / ".claude" / "hooks" / "deploy_gate.py",
    ]
    for copy in copies:
        assert copy.is_file(), copy
        assert copy.read_bytes() == expected, f"{copy} has drifted from .claude/hooks"


def test_every_platform_registers_the_hook() -> None:
    claude = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert any(
        "deploy_gate.py" in str(entry)
        for entry in claude["hooks"]["PreToolUse"]
    ), "Claude Code does not register deploy_gate.py"

    codex = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    assert any(
        "deploy_gate.py" in str(entry) for entry in codex["hooks"]["PreToolUse"]
    ), "Codex does not register deploy_gate.py"

    kiro = json.loads((ROOT / ".kiro" / "hooks" / "adop-gates.json").read_text(encoding="utf-8"))
    gate = [h for h in kiro["hooks"] if "deploy_gate.py" in str(h.get("action", {}))]
    assert gate, "Kiro does not register deploy_gate.py"
    assert gate[0]["trigger"] == "PreToolUse" and gate[0]["enabled"] is True

    # No matcher anywhere: the hook classifies the call itself, so a deploy path
    # arriving as an MCP tool or a new AWS tool spelling still reaches the gate.
    for entry in (
        *claude["hooks"]["PreToolUse"],
        *codex["hooks"]["PreToolUse"],
    ):
        if "deploy_gate.py" in str(entry):
            assert "matcher" not in entry, f"deploy gate must not be matcher-scoped: {entry}"
    assert "matcher" not in gate[0], "deploy gate must not be matcher-scoped in Kiro"


# ── the auditor path fix ────────────────────────────────────────────────────


def test_auditor_accepts_repo_relative_target_paths(tmp_path: Path) -> None:
    """The ledger records repo-relative targets; both forms name the same file."""
    from shared.requirements.auditor import RequirementAuditor

    workload = tmp_path / "workloads" / "orders"
    (workload / "config").mkdir(parents=True)
    (workload / "config" / "source.yaml").write_text("name: orders\n", encoding="utf-8")
    auditor = RequirementAuditor(workload)

    for raw in ("config/source.yaml", "workloads/orders/config/source.yaml"):
        evidence, reason = auditor._path_evidence([raw], [])
        assert reason is None, f"{raw}: {reason}"
        assert evidence == [raw]
