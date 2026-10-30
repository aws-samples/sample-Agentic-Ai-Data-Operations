"""Live, read-only deployment checks shared by every ADOP platform.

``deployment_guardrails`` validates deployment *inputs* without calling AWS.
This module checks the *live account* before and after the deploy mutations,
and every call it makes is read-only:

* ``preflight``   — requires a passing, current requirements audit, then runs
                    the local guardrails against ``run/context.json``. On pass it
                    writes ``run/deploy_gate.json``, which the platform
                    ``deploy_gate.py`` hooks require before any deploy mutation.
* ``simulate``    — ``iam:SimulatePrincipalPolicy`` for the MWAA execution role
                    (``glue:GetJob``, ``glue:StartJobRun``, ``glue:GetJobRun``,
                    ``iam:PassRole`` on the Glue role) and for the workload Glue
                    role (catalog reads/writes and the KMS key).
* ``active-runs`` — refuses to continue while any of the workload's Glue jobs
                    has a run in flight, so a manual start cannot collide with a
                    scheduled or catch-up run (Glue ``ConcurrentRunsExceededException``).

Claude Code, Codex and Kiro all call this one entry point from their Deploy
phase, so a fix here applies to every platform.

Usage:
    python3 -m shared.utils.deployment_checks preflight --context workloads/x/run/context.json
    python3 -m shared.utils.deployment_checks simulate --workload-dir workloads/x --region us-east-1 \\
        --mwaa-role-arn arn:aws:iam::...:role/mwaa-exec --glue-role-arn arn:aws:iam::...:role/x-glue-service-role \\
        --jobs x_silver x_gold --databases x_db --kms-key-arn arn:aws:kms:...:key/...
    python3 -m shared.utils.deployment_checks active-runs --region us-east-1 --jobs x_silver x_gold
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.deployment_guardrails import (  # noqa: E402
    DeploymentGuardrailError,
    validate_deployment_preflight,
)


# The MWAA DAG uses GlueJobOperator: it reads the job, starts it, then polls it.
MWAA_GLUE_ACTIONS = ("glue:GetJob", "glue:StartJobRun", "glue:GetJobRun")
# Glue Spark sessions with the Glue catalog resolve the `default` database on
# start-up, so it is required even when no workload table lives there.
GLUE_CATALOG_ACTIONS = (
    "glue:GetDatabase",
    "glue:GetTable",
    "glue:GetTables",
    "glue:CreateTable",
    "glue:UpdateTable",
)
KMS_ACTIONS = ("kms:Decrypt", "kms:GenerateDataKey")
ACTIVE_RUN_STATES = frozenset({"STARTING", "RUNNING", "STOPPING", "WAITING"})
AUDIT_REPORT = "requirements_audit.json"
DEPLOY_GATE = "deploy_gate.json"
# Changes here after the audit invalidate it. The ledger and decisions/trace
# logs are excluded: the auditor appends to them itself, and every new user
# turn is captured into the ledger.
_AUDITED_DIRS = ("config", "scripts", "dags", "sql")


def _load(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def require_passing_audit(workload_dir: str | Path) -> Dict[str, Any]:
    """Raise unless ``run/requirements_audit.json`` passes and is current.

    Current means: same ``run_id`` as ``run/context.json``, and no audited input
    (``context.json`` or anything under config/scripts/dags/sql) modified after
    the report was written.
    """
    workload_dir = Path(workload_dir)
    run_dir = workload_dir / "run"
    report_path = run_dir / AUDIT_REPORT
    if not report_path.is_file():
        raise DeploymentGuardrailError(
            f"{report_path} is missing; run the requirements-auditor before deploying"
        )
    report = _load(report_path)
    if report.get("status") != "pass":
        issues = report.get("blocking_issues") or []
        raise DeploymentGuardrailError(
            f"requirements audit status is {report.get('status')!r}, not 'pass' "
            f"({len(issues)} blocking issue(s)); deployment is blocked"
        )
    context_run_id = _load(run_dir / "context.json").get("run_id")
    if context_run_id and report.get("run_id") and report["run_id"] != context_run_id:
        raise DeploymentGuardrailError(
            f"requirements audit is for run {report['run_id']!r}, current run is "
            f"{context_run_id!r}; re-run the auditor"
        )
    audited_at = report_path.stat().st_mtime
    inputs = [run_dir / "context.json"]
    for name in _AUDITED_DIRS:
        directory = workload_dir / name
        if directory.is_dir():
            inputs.extend(p for p in directory.rglob("*") if p.is_file())
    stale = sorted(
        str(p.relative_to(workload_dir)) for p in inputs
        if p.is_file() and p.stat().st_mtime > audited_at
    )
    if stale:
        raise DeploymentGuardrailError(
            f"requirements audit is stale; changed after the audit: {stale[:10]}"
        )
    return report


def write_deploy_gate(workload_dir: str | Path, report: Mapping[str, Any]) -> Path:
    """Record that preflight passed against a current audit (read by deploy_gate hooks)."""
    from datetime import datetime, timezone

    path = Path(workload_dir) / "run" / DEPLOY_GATE
    path.write_text(
        json.dumps(
            {
                "status": "pass",
                "run_id": report.get("run_id", ""),
                "audit_id": report.get("audit_id", ""),
                "gated_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def deploy_gate_open(workload_dir: str | Path) -> Optional[str]:
    """Return None if deploy mutations are allowed for this workload, else the reason."""
    workload_dir = Path(workload_dir)
    gate = _load(workload_dir / "run" / DEPLOY_GATE)
    if gate.get("status") != "pass":
        return (
            f"no passing deploy gate for {workload_dir.name}; run "
            "`python3 -m shared.utils.deployment_checks preflight` after a passing audit"
        )
    try:
        report = require_passing_audit(workload_dir)
    except DeploymentGuardrailError as exc:
        return str(exc)
    if gate.get("audit_id") != report.get("audit_id"):
        return "deploy gate predates the latest audit; re-run preflight"
    return None


def _arn_parts(role_arn: str) -> tuple[str, str]:
    """Return (partition, account_id) from an IAM role ARN."""
    parts = role_arn.split(":")
    if len(parts) < 6 or parts[0] != "arn" or parts[2] != "iam" or not parts[4]:
        raise DeploymentGuardrailError(f"Not an IAM role ARN: {role_arn!r}")
    return parts[1], parts[4]


def glue_job_arn(partition: str, region: str, account_id: str, job_name: str) -> str:
    return f"arn:{partition}:glue:{region}:{account_id}:job/{job_name}"


def mwaa_role_requirements(
    *, region: str, glue_role_arn: str, job_names: Sequence[str]
) -> List[Dict[str, Any]]:
    """Action groups the MWAA execution role needs to run the workload DAG."""
    if not job_names:
        raise DeploymentGuardrailError("At least one Glue job name is required")
    partition, account_id = _arn_parts(glue_role_arn)
    return [
        {
            "actions": list(MWAA_GLUE_ACTIONS),
            "resources": [
                glue_job_arn(partition, region, account_id, job) for job in job_names
            ],
        },
        {
            "actions": ["iam:PassRole"],
            "resources": [glue_role_arn],
            "context": [
                {
                    "ContextKeyName": "iam:PassedToService",
                    "ContextKeyValues": ["glue.amazonaws.com"],
                    "ContextKeyType": "string",
                }
            ],
        },
    ]


def glue_role_requirements(
    *,
    region: str,
    glue_role_arn: str,
    databases: Sequence[str],
    kms_key_arn: Optional[str] = None,
    include_default_database: bool = True,
) -> List[Dict[str, Any]]:
    """Action groups the workload Glue role needs for catalog and KMS calls."""
    if not databases:
        raise DeploymentGuardrailError("At least one Glue database is required")
    partition, account_id = _arn_parts(glue_role_arn)
    prefix = f"arn:{partition}:glue:{region}:{account_id}"
    names = list(dict.fromkeys([*databases, *(["default"] if include_default_database else [])]))
    resources = [f"{prefix}:catalog"]
    for name in names:
        resources.append(f"{prefix}:database/{name}")
        resources.append(f"{prefix}:table/{name}/*")
    groups: List[Dict[str, Any]] = [
        {"actions": list(GLUE_CATALOG_ACTIONS), "resources": resources}
    ]
    if kms_key_arn:
        groups.append({"actions": list(KMS_ACTIONS), "resources": [kms_key_arn]})
    return groups


def simulate_role(
    iam: Any, role_arn: str, requirements: Iterable[Mapping[str, Any]]
) -> List[Dict[str, str]]:
    """Simulate each action group for ``role_arn``; return every non-allowed result."""
    denied: List[Dict[str, str]] = []
    paginator = iam.get_paginator("simulate_principal_policy")
    for group in requirements:
        request: Dict[str, Any] = {
            "PolicySourceArn": role_arn,
            "ActionNames": list(group["actions"]),
            "ResourceArns": list(group["resources"]),
        }
        if group.get("context"):
            request["ContextEntries"] = list(group["context"])
        for page in paginator.paginate(**request):
            for result in page.get("EvaluationResults", []):
                resource_results = result.get("ResourceSpecificResults") or [
                    {
                        "EvalResourceName": result.get("EvalResourceName", "*"),
                        "EvalResourceDecision": result.get("EvalDecision"),
                    }
                ]
                for item in resource_results:
                    decision = item.get("EvalResourceDecision")
                    if decision != "allowed":
                        denied.append(
                            {
                                "role_arn": role_arn,
                                "action": result.get("EvalActionName", ""),
                                "resource": item.get("EvalResourceName", ""),
                                "decision": str(decision),
                            }
                        )
    return denied


def active_job_runs(glue: Any, job_names: Sequence[str]) -> Dict[str, List[str]]:
    """Return ``{job_name: [run_id, ...]}`` for runs that have not finished."""
    active: Dict[str, List[str]] = {}
    for job in job_names:
        runs = glue.get_job_runs(JobName=job, MaxResults=50).get("JobRuns", [])
        in_flight = [r["Id"] for r in runs if r.get("JobRunState") in ACTIVE_RUN_STATES]
        if in_flight:
            active[job] = in_flight
    return active


def require_no_active_runs(glue: Any, job_names: Sequence[str]) -> None:
    """Raise before a manual job start if any workload job is still running."""
    active = active_job_runs(glue, job_names)
    if active:
        raise DeploymentGuardrailError(
            "Glue job run(s) still in flight; wait for them to finish before "
            f"starting another: {json.dumps(active, sort_keys=True)}"
        )


def _print(report: Mapping[str, Any]) -> None:
    print(json.dumps(report, indent=2, sort_keys=True))


def _cmd_preflight(args: argparse.Namespace) -> int:
    context_path = Path(args.context)
    workload_dir = context_path.resolve().parent.parent
    try:
        report = require_passing_audit(workload_dir)
        context = json.loads(context_path.read_text(encoding="utf-8"))
        result = validate_deployment_preflight(
            context,
            glue_role_name=args.glue_role,
            workload_dir=workload_dir,
        )
    except DeploymentGuardrailError as exc:
        _print({"check": "preflight", "status": "blocked", "error": str(exc)})
        return 2
    gate = write_deploy_gate(workload_dir, report)
    _print({"check": "preflight", "status": "pass", "deploy_gate": str(gate), **result})
    return 0


def _cmd_simulate(args: argparse.Namespace) -> int:
    import boto3

    iam = boto3.client("iam", region_name=args.region)
    denied: List[Dict[str, str]] = []
    try:
        require_passing_audit(args.workload_dir)
        denied += simulate_role(
            iam,
            args.mwaa_role_arn,
            mwaa_role_requirements(
                region=args.region, glue_role_arn=args.glue_role_arn, job_names=args.jobs
            ),
        )
        denied += simulate_role(
            iam,
            args.glue_role_arn,
            glue_role_requirements(
                region=args.region,
                glue_role_arn=args.glue_role_arn,
                databases=args.databases,
                kms_key_arn=args.kms_key_arn,
            ),
        )
    except DeploymentGuardrailError as exc:
        _print({"check": "simulate", "status": "blocked", "error": str(exc)})
        return 2
    _print({"check": "simulate", "status": "blocked" if denied else "pass", "denied": denied})
    return 2 if denied else 0


def _cmd_active_runs(args: argparse.Namespace) -> int:
    import boto3

    glue = boto3.client("glue", region_name=args.region)
    active = active_job_runs(glue, args.jobs)
    _print({"check": "active-runs", "status": "blocked" if active else "pass", "active": active})
    return 2 if active else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="deployment_checks")
    sub = parser.add_subparsers(dest="command", required=True)

    pre = sub.add_parser("preflight", help="local guardrails; no AWS calls")
    pre.add_argument("--context", required=True)
    pre.add_argument("--glue-role", default=None)

    sim = sub.add_parser("simulate", help="IAM policy simulation (read-only)")
    sim.add_argument("--workload-dir", required=True)
    sim.add_argument("--region", required=True)
    sim.add_argument("--mwaa-role-arn", required=True)
    sim.add_argument("--glue-role-arn", required=True)
    sim.add_argument("--jobs", nargs="+", required=True)
    sim.add_argument("--databases", nargs="+", required=True)
    sim.add_argument("--kms-key-arn", default=None)

    act = sub.add_parser("active-runs", help="block while a Glue run is in flight")
    act.add_argument("--region", required=True)
    act.add_argument("--jobs", nargs="+", required=True)

    args = parser.parse_args(argv)
    handlers = {
        "preflight": _cmd_preflight,
        "simulate": _cmd_simulate,
        "active-runs": _cmd_active_runs,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
