"""Deploy-phase checks shared by Claude Code, Codex and Kiro."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.utils import deployment_checks as dc  # noqa: E402
from shared.utils.deployment_guardrails import DeploymentGuardrailError  # noqa: E402

GLUE_ROLE = "arn:aws:iam::111122223333:role/orders-glue-service-role"
MWAA_ROLE = "arn:aws:iam::111122223333:role/mwaa-exec"


class FakeIam:
    """Allows everything except the (action, resource) pairs in ``deny``."""

    def __init__(self, deny: set[tuple[str, str]] | None = None) -> None:
        self.deny = deny or set()
        self.requests: list[dict[str, Any]] = []

    def get_paginator(self, name: str) -> "FakeIam":
        assert name == "simulate_principal_policy"
        return self

    def paginate(self, **request: Any):
        self.requests.append(request)
        results = []
        for action in request["ActionNames"]:
            results.append(
                {
                    "EvalActionName": action,
                    "ResourceSpecificResults": [
                        {
                            "EvalResourceName": resource,
                            "EvalResourceDecision": "implicitDeny"
                            if (action, resource) in self.deny
                            else "allowed",
                        }
                        for resource in request["ResourceArns"]
                    ],
                }
            )
        yield {"EvaluationResults": results}


class FakeGlue:
    def __init__(self, runs: dict[str, list[dict[str, str]]]) -> None:
        self.runs = runs

    def get_job_runs(self, JobName: str, MaxResults: int) -> dict[str, Any]:
        return {"JobRuns": self.runs.get(JobName, [])}


def test_mwaa_requirements_cover_getjob_startjobrun_and_passrole() -> None:
    groups = dc.mwaa_role_requirements(
        region="us-east-1", glue_role_arn=GLUE_ROLE, job_names=["orders_silver"]
    )
    actions = {a for g in groups for a in g["actions"]}
    assert {"glue:GetJob", "glue:StartJobRun", "glue:GetJobRun", "iam:PassRole"} <= actions
    assert groups[0]["resources"] == [
        "arn:aws:glue:us-east-1:111122223333:job/orders_silver"
    ]
    passrole = groups[1]
    assert passrole["resources"] == [GLUE_ROLE]
    assert passrole["context"][0]["ContextKeyValues"] == ["glue.amazonaws.com"]


def test_glue_requirements_include_default_database_and_kms() -> None:
    groups = dc.glue_role_requirements(
        region="us-east-1",
        glue_role_arn=GLUE_ROLE,
        databases=["orders_db"],
        kms_key_arn="arn:aws:kms:us-east-1:111122223333:key/abc",
    )
    resources = groups[0]["resources"]
    assert "arn:aws:glue:us-east-1:111122223333:database/default" in resources
    assert "arn:aws:glue:us-east-1:111122223333:database/orders_db" in resources
    assert groups[1]["actions"] == ["kms:Decrypt", "kms:GenerateDataKey"]


def test_simulate_role_reports_missing_getjob() -> None:
    job_arn = "arn:aws:glue:us-east-1:111122223333:job/orders_silver"
    iam = FakeIam(deny={("glue:GetJob", job_arn)})
    denied = dc.simulate_role(
        iam,
        MWAA_ROLE,
        dc.mwaa_role_requirements(
            region="us-east-1", glue_role_arn=GLUE_ROLE, job_names=["orders_silver"]
        ),
    )
    assert denied == [
        {
            "role_arn": MWAA_ROLE,
            "action": "glue:GetJob",
            "resource": job_arn,
            "decision": "implicitDeny",
        }
    ]
    assert iam.requests[1]["ContextEntries"][0]["ContextKeyName"] == "iam:PassedToService"


def test_simulate_role_passes_when_all_allowed() -> None:
    assert dc.simulate_role(
        FakeIam(),
        GLUE_ROLE,
        dc.glue_role_requirements(
            region="us-east-1", glue_role_arn=GLUE_ROLE, databases=["orders_db"]
        ),
    ) == []


def test_require_no_active_runs_blocks_overlapping_start() -> None:
    glue = FakeGlue(
        {
            "orders_silver": [
                {"Id": "jr_1", "JobRunState": "RUNNING"},
                {"Id": "jr_0", "JobRunState": "SUCCEEDED"},
            ],
            "orders_gold": [{"Id": "jr_2", "JobRunState": "FAILED"}],
        }
    )
    assert dc.active_job_runs(glue, ["orders_silver", "orders_gold"]) == {
        "orders_silver": ["jr_1"]
    }
    with pytest.raises(DeploymentGuardrailError, match="jr_1"):
        dc.require_no_active_runs(glue, ["orders_silver", "orders_gold"])
    dc.require_no_active_runs(glue, ["orders_gold"])


def test_role_arn_is_required_to_derive_account() -> None:
    with pytest.raises(DeploymentGuardrailError):
        dc.mwaa_role_requirements(
            region="us-east-1", glue_role_arn="orders-glue-service-role", job_names=["j"]
        )


def _verifier(monkeypatch: pytest.MonkeyPatch, mwaa_environment: str | None = "env"):
    pytest.importorskip("boto3")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    from shared.utils.post_deployment_verifier import PostDeploymentVerifier

    return PostDeploymentVerifier(
        workload="orders", database="orders_db", mwaa_environment=mwaa_environment
    )


def test_mwaa_check_fails_on_import_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = _verifier(monkeypatch)
    responses = {
        "dags list-import-errors -o json": [
            {"filepath": "/usr/local/airflow/dags/orders_dag.py", "error": "boom"}
        ],
        "dags list -o json": [{"dag_id": "orders_dag", "is_paused": False}],
    }
    monkeypatch.setattr(verifier, "_mwaa_cli", lambda command: responses[command])
    result = verifier.check_mwaa_dag("orders_dag")
    assert not result.passed
    assert result.details["import_errors"][0]["error"] == "boom"


def test_mwaa_check_passes_when_listed_without_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = _verifier(monkeypatch)
    responses = {
        "dags list-import-errors -o json": [
            {"filepath": "/usr/local/airflow/dags/other_dag.py", "error": "unrelated"}
        ],
        "dags list -o json": [{"dag_id": "orders_dag", "is_paused": True}],
    }
    monkeypatch.setattr(verifier, "_mwaa_cli", lambda command: responses[command])
    assert verifier.check_mwaa_dag("orders_dag").passed


def test_mwaa_check_fails_closed_without_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = _verifier(monkeypatch, mwaa_environment=None)
    assert not verifier.check_mwaa_dag("orders_dag").passed


def test_mwaa_role_check_requires_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = _verifier(monkeypatch)
    result = verifier.check_mwaa_role_permissions(None, GLUE_ROLE, ["orders_silver"])
    assert not result.passed and result.step == "5.9i"


def test_mwaa_role_check_reports_denied_passrole(monkeypatch: pytest.MonkeyPatch) -> None:
    import shared.utils.post_deployment_verifier as pdv

    verifier = _verifier(monkeypatch)
    iam = FakeIam(deny={("iam:PassRole", GLUE_ROLE)})
    monkeypatch.setattr(pdv.boto3, "client", lambda *a, **k: iam)
    result = verifier.check_mwaa_role_permissions(MWAA_ROLE, GLUE_ROLE, ["orders_silver"])
    assert not result.passed
    assert result.details["denied"][0]["action"] == "iam:PassRole"


def test_kiro_deploy_check_blocks_before_audit_passes() -> None:
    import subprocess

    result = subprocess.run(
        [sys.executable, "scripts/kiro_workflow.py", "deploy-check",
         "--workload", "zz_no_such_workload", "preflight"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "requirements-auditor" in result.stdout
    assert not (ROOT / "workloads" / "zz_no_such_workload").exists()


def test_platform_check_flags_surface_missing_deploy_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import sync_platforms

    relative = ".codex/skills/command-onboard-workflow/SKILL.md"
    stripped = tmp_path / relative
    stripped.parent.mkdir(parents=True)
    stripped.write_text("## Step 9: Post-Deployment Sequence\n", encoding="utf-8")
    monkeypatch.setattr(sync_platforms, "ROOT", tmp_path)
    monkeypatch.setattr(sync_platforms, "DEPLOY_PHASE_SURFACES",
                        {relative: ("simulate", "active-runs")})
    errors: list[str] = []
    sync_platforms.check_deploy_phase(errors)
    assert any("does not call shared.utils.deployment_checks" in e for e in errors)
    assert any("'active-runs'" in e for e in errors)
