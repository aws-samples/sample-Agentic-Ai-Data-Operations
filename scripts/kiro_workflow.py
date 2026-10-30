#!/usr/bin/env python3
"""Small, deterministic Kiro driver for ADOP run state and phase gates.

Kiro's conversation remains human-facing; this driver owns the filesystem
contract that must not depend on model memory. It never invents discovery
answers and it never renders a pipeline artifact directly.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.requirements.auditor import audit_workload  # noqa: E402
from shared.codegen.contract_resolver import (  # noqa: E402
    ContractPolicyError,
    resolve_effective_policy,
)
from shared.utils import deployment_checks  # noqa: E402


WORKLOAD_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
COMMON = (
    "pii_columns",
    "compliance",
    "quality_thresholds",
    "schedule",
    "schedule_timezone",
    "ontology_opt_in",
    "transformations",
)
ZONE_FIELDS = {
    "bronze": ("source_path", "credentials", "ingestion_pattern", "retention"),
    "silver": ("primary_key", "dedup_strategy", "null_handling"),
    "gold": ("business_outcome", "kpis", "aggregation_grain", "gold_schema_choice"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_dir(workload: str) -> Path:
    return ROOT / "workloads" / workload / "run"


def _append_trace(run_dir: Path, event_type: str, payload: Mapping[str, Any]) -> None:
    path = run_dir.parent / "logs" / "trace_events.jsonl"
    if not run_dir.parent.is_dir():
        # Never materialise a workload tree from a trace write; `init` owns that.
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    current = 0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                current = max(current, int(json.loads(line).get("sequence_number", 0)))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
    event = {
        "timestamp": _now(),
        "run_id": payload.get("run_id", ""),
        "trace_id": f"kiro-{uuid.uuid4().hex[:12]}",
        "span_id": uuid.uuid4().hex[:16],
        "parent_span_id": None,
        "sequence_number": current + 1,
        "thread_id": None,
        "surface": "operational",
        "event_type": event_type,
        "agent_name": "kiro-orchestrator",
        "workload_name": run_dir.parent.name,
        "phase": payload.get("phase", "orchestration"),
        "data_zone": "",
        "status": payload.get("status", "ok"),
        "duration_ms": None,
        "payload": dict(payload),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _require_workload(value: str) -> str:
    if not WORKLOAD_RE.fullmatch(value):
        raise SystemExit(
            "error: workload must match ^[a-z][a-z0-9_]{1,40}$; no path traversal"
        )
    return value


def init_run(workload: str, run_id: str | None) -> int:
    workload = _require_workload(workload)
    run_dir = _run_dir(workload)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir.parent / "logs").mkdir(parents=True, exist_ok=True)
    ledger = run_dir / "requirements.jsonl"
    ledger.touch(exist_ok=True)
    pending = run_dir.parent / ".requirements_pending" / "requirements.jsonl"
    migrated = run_dir / ".requirements_pending_migrated"
    if pending.is_file() and not migrated.exists():
        pending_text = pending.read_text(encoding="utf-8")
        if pending_text:
            with ledger.open("a", encoding="utf-8") as handle:
                handle.write(pending_text)
        migrated.write_text(_now() + "\n", encoding="utf-8")
    chosen_run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
    _append_trace(
        run_dir,
        "workflow_start",
        {"run_id": chosen_run_id, "phase": "discovery", "status": "started"},
    )
    print(f"initialized {run_dir.relative_to(ROOT)}")
    print(f"run_id={chosen_run_id}")
    print("Next: capture the complete human Q&A, then write context.json and discovery_complete.json.")
    return 0


def _nonempty(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def discovery_gate(workload: str) -> int:
    workload = _require_workload(workload)
    run_dir = _run_dir(workload)
    context_path = run_dir / "context.json"
    marker_path = run_dir / "discovery_complete.json"
    blockers: list[str] = []
    context: dict[str, Any] = {}
    if not context_path.is_file():
        blockers.append(f"missing {context_path.relative_to(ROOT)}")
    else:
        try:
            loaded = json.loads(context_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                context = loaded
            else:
                blockers.append("context.json must contain an object")
        except json.JSONDecodeError as exc:
            blockers.append(f"context.json is invalid JSON: {exc.msg}")
    if not marker_path.is_file():
        blockers.append(
            "missing run/discovery_complete.json; the orchestrator must record that "
            "the human answered every Phase 1 question"
        )
    answers = context.get("human_answers", {})
    if not isinstance(answers, Mapping):
        blockers.append("context.json human_answers must be an object")
        answers = {}
    zones = answers.get("zones")
    if not isinstance(zones, list) or not zones:
        blockers.append("human_answers.zones is required")
    else:
        for zone in zones:
            for field in ZONE_FIELDS.get(str(zone), ()):
                if not _nonempty(answers.get(field)):
                    blockers.append(f"human_answers.{field} is missing for {zone}")
    for field in COMMON:
        if field == "ontology_opt_in":
            if not isinstance(answers.get(field), bool):
                blockers.append("human_answers.ontology_opt_in is required and must be boolean")
        elif not _nonempty(answers.get(field)):
            blockers.append(f"human_answers.{field} is required")
    if answers.get("ontology_opt_in") is True and not _nonempty(
        answers.get("ontology_use_cases")
    ):
        blockers.append(
            "human_answers.ontology_use_cases is required when ontology_opt_in is true"
        )
    try:
        effective_contract = resolve_effective_policy(run_dir.parent)
    except ContractPolicyError as exc:
        blockers.append(f"effective zone contract is invalid: {exc}")
        effective_contract = None
    if blockers:
        print("PHASE 1 BLOCKED")
        for blocker in sorted(set(blockers)):
            print(f"- {blocker}")
        return 2
    run_id = str(context.get("run_id", ""))
    _append_trace(
        run_dir,
        "phase_complete",
        {"run_id": run_id, "phase": "discovery", "status": "pass"},
    )
    print(f"PHASE 1 PASS: {workload}")
    if effective_contract:
        print(f"effective_contract_hash={effective_contract['effective_hash']}")
    return 0


def audit(workload: str) -> int:
    workload = _require_workload(workload)
    report = audit_workload(_run_dir(workload).parent)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "pass" else 2


def status(workload: str) -> int:
    workload = _require_workload(workload)
    run_dir = _run_dir(workload)
    for relative in ("requirements.jsonl", "context.json", "discovery_complete.json"):
        print(f"{relative}: {'present' if (run_dir / relative).exists() else 'missing'}")
    report = run_dir / "requirements_audit.json"
    if report.is_file():
        try:
            print(f"audit: {json.loads(report.read_text()).get('status', 'unknown')}")
        except json.JSONDecodeError:
            print("audit: invalid JSON")
    else:
        print("audit: not-run")
    return 0


def deploy_check(workload: str, check_args: list[str]) -> int:
    """Phase 5 gates: the same shared checks Claude Code and Codex run.

    ``preflight`` and ``simulate`` require a passing, current requirements audit
    (enforced inside ``deployment_checks``); ``active-runs`` is allowed at any
    time because every manual Glue job start must pass it first.
    """
    workload = _require_workload(workload)
    run_dir = _run_dir(workload)
    if not check_args:
        print("error: deploy-check needs one of: preflight, simulate, active-runs", file=sys.stderr)
        return 2
    check = check_args[0]
    if check == "preflight" and "--context" not in check_args:
        check_args = [*check_args, "--context", str(run_dir / "context.json")]
    if check == "simulate" and "--workload-dir" not in check_args:
        check_args = [*check_args, "--workload-dir", str(run_dir.parent)]
    code = deployment_checks.main(check_args)
    _append_trace(
        run_dir,
        "deployment_step",
        {
            "run_id": _run_id(run_dir),
            "phase": "deploy",
            "check": check,
            "status": "pass" if code == 0 else "blocked",
        },
    )
    return code


def verify(workload: str, verifier_args: list[str]) -> int:
    """Step 5.9: run the shared post-deployment verifier and trace the outcome."""
    workload = _require_workload(workload)
    run_dir = _run_dir(workload)
    code = subprocess.call(
        [
            sys.executable,
            str(ROOT / "shared" / "utils" / "post_deployment_verifier.py"),
            "--workload",
            workload,
            *verifier_args,
        ],
        cwd=ROOT,
    )
    _append_trace(
        run_dir,
        "deployment_verification",
        {"run_id": _run_id(run_dir), "phase": "deploy", "status": "pass" if code == 0 else "failed"},
    )
    return code


def _run_id(run_dir: Path) -> str:
    try:
        return str(json.loads((run_dir / "context.json").read_text(encoding="utf-8")).get("run_id", ""))
    except (OSError, json.JSONDecodeError):
        return ""


def render(args: list[str]) -> int:
    # The live Kiro surface comes first: it is the path the codegen gate's denial message
    # tells the agent to run, so the driver and the gate must not disagree about which
    # renderer is "the" renderer. adapters/ is the portable snapshot and only a fallback.
    candidates = (
        ROOT / ".kiro" / "adop" / "render.sh",
        ROOT / "adapters" / "kiro" / ".kiro" / "adop" / "render.sh",
    )
    renderer = next((path for path in candidates if path.is_file()), None)
    if renderer is None:
        print(
            "error: missing Kiro renderer; looked for "
            + ", ".join(str(path.relative_to(ROOT)) for path in candidates),
            file=sys.stderr,
        )
        return 2
    return subprocess.call([str(renderer), *args], cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(prog="kiro_workflow")
    sub = parser.add_subparsers(dest="command", required=True)
    init_parser = sub.add_parser("init")
    init_parser.add_argument("--workload", required=True)
    init_parser.add_argument("--run-id")
    gate_parser = sub.add_parser("gate")
    gate_parser.add_argument("--workload", required=True)
    audit_parser = sub.add_parser("audit")
    audit_parser.add_argument("--workload", required=True)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--workload", required=True)
    render_parser = sub.add_parser("render")
    render_parser.add_argument("renderer_args", nargs=argparse.REMAINDER)
    deploy_parser = sub.add_parser("deploy-check")
    deploy_parser.add_argument("--workload", required=True)
    deploy_parser.add_argument("check_args", nargs=argparse.REMAINDER)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--workload", required=True)
    verify_parser.add_argument("verifier_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "init":
        return init_run(args.workload, args.run_id)
    if args.command == "gate":
        return discovery_gate(args.workload)
    if args.command == "audit":
        return audit(args.workload)
    if args.command == "status":
        return status(args.workload)
    if args.command == "deploy-check":
        return deploy_check(args.workload, args.check_args)
    if args.command == "verify":
        return verify(args.workload, args.verifier_args)
    return render(args.renderer_args)


if __name__ == "__main__":
    raise SystemExit(main())
