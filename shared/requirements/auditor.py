"""Deterministic reconciliation of user requirements with workflow evidence.

The requirements auditor is deliberately evidence-driven. It never infers a
business rule from a column name or from an agent's prose. The orchestrator
records user turns and explicit requirements under ``run/requirements.jsonl``;
this module checks that every captured turn was classified and that every
mandatory requirement has evidence in the workload artifacts.

The resulting report is written to ``run/requirements_audit.json`` and the
audit decision is appended to ``run/decisions.jsonl``. A compact event is also
appended to ``logs/trace_events.jsonl`` so a resumed run can locate the last
conformance decision.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


LEDGER_NAME = "requirements.jsonl"
REPORT_NAME = "requirements_audit.json"

_IGNORED_HUMAN_ANSWER_KEYS = {"recorded_at"}
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _json_line(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True, default=str) + "\n")


def append_user_turn(
    run_dir: str | Path,
    *,
    prompt: str,
    response: str,
    phase: int | str | None = None,
    thread_id: str | None = None,
    turn_id: str | None = None,
) -> str:
    """Append one user-facing exchange to the authoritative requirement ledger.

    ``requirement_ids`` starts empty intentionally. The orchestrator or the
    requirements auditor must classify the turn explicitly; silently treating
    every answer as a requirement would be unsafe.
    """

    turn_id = turn_id or f"turn-{uuid.uuid4().hex[:12]}"
    _json_line(
        Path(run_dir) / LEDGER_NAME,
        {
            "record_type": "user_turn",
            "turn_id": turn_id,
            "timestamp": _now(),
            "phase": phase,
            "thread_id": thread_id,
            "prompt": prompt,
            "response": response,
            "requirement_ids": [],
        },
    )
    return turn_id


def append_requirement(
    run_dir: str | Path,
    *,
    text: str,
    source_ref: str,
    mandatory: bool = True,
    target_paths: Sequence[str] = (),
    requirement_id: str | None = None,
    source_type: str = "user_response",
    acceptance: Sequence[str] = (),
) -> str:
    """Append an explicit, auditable requirement to the ledger."""

    requirement_id = requirement_id or _stable_id(
        "req", f"{source_type}|{source_ref}|{text}"
    )
    _json_line(
        Path(run_dir) / LEDGER_NAME,
        {
            "record_type": "requirement",
            "requirement_id": requirement_id,
            "timestamp": _now(),
            "source_type": source_type,
            "source_ref": source_ref,
            "text": text,
            "mandatory": mandatory,
            "target_paths": sorted(set(target_paths)),
            "acceptance": list(acceptance),
        },
    )
    return requirement_id


@dataclass
class RequirementFinding:
    requirement_id: str
    status: str
    text: str
    source_ref: str
    mandatory: bool
    evidence: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "status": self.status,
            "text": self.text,
            "source_ref": self.source_ref,
            "mandatory": self.mandatory,
            "evidence": self.evidence,
            "reason": self.reason,
        }


class RequirementAuditor:
    """Audit one workload without calling AWS, MCP, or an LLM."""

    def __init__(self, workload_dir: str | Path):
        self.workload_dir = Path(workload_dir)
        self.run_dir = self.workload_dir / "run"
        self.logs_dir = self.workload_dir / "logs"

    @property
    def workload_name(self) -> str:
        return self.workload_dir.name

    def _load_json(self, path: Path) -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a JSON object")
        return data

    def _load_context(self) -> dict[str, Any]:
        path = self.run_dir / "context.json"
        if not path.exists():
            raise FileNotFoundError(f"missing authoritative run context: {path}")
        return self._load_json(path)

    def _load_ledger(self) -> tuple[list[dict[str, Any]], list[str]]:
        path = self.run_dir / LEDGER_NAME
        if not path.exists():
            return [], [f"missing requirement ledger: {path}"]

        records: list[dict[str, Any]] = []
        errors: list[str] = []
        for line_number, raw in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not raw.strip():
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{line_number}: invalid JSON ({exc.msg})")
                continue
            if not isinstance(value, dict):
                errors.append(f"{path}:{line_number}: record is not an object")
                continue
            records.append(value)
        return records, errors

    def _artifact_paths(self) -> list[Path]:
        roots = ("config", "scripts", "dags", "sql", "tests")
        paths: list[Path] = []
        for root in roots:
            directory = self.workload_dir / root
            if directory.exists():
                paths.extend(
                    path for path in directory.rglob("*") if path.is_file()
                )
        return sorted(paths)

    def _path_evidence(
        self, target_paths: Iterable[str], acceptance: Iterable[str]
    ) -> tuple[list[str], str | None]:
        evidence: list[str] = []
        missing: list[str] = []
        for raw_path in sorted(set(target_paths)):
            path = self.workload_dir / raw_path
            if not path.is_file():
                missing.append(raw_path)
                continue
            evidence.append(raw_path)
            if acceptance:
                content = path.read_text(encoding="utf-8", errors="replace").lower()
                absent = [
                    value
                    for value in acceptance
                    if str(value).lower() not in content
                ]
                if absent:
                    return evidence, (
                        f"acceptance text not found in {raw_path}: {absent}"
                    )
        if missing:
            return evidence, f"target artifacts are missing: {missing}"
        if not target_paths:
            return [], "no artifact targets were recorded"
        return evidence, None

    def _human_answer_refs(
        self, context: Mapping[str, Any]
    ) -> set[str]:
        answers = context.get("human_answers", {})
        if not isinstance(answers, Mapping):
            return set()
        return {
            f"context.json#human_answers.{key}"
            for key in answers
            if key not in _IGNORED_HUMAN_ANSWER_KEYS
        }

    def audit(self) -> dict[str, Any]:
        """Return a JSON-serializable audit report.

        The audit blocks on missing ledger data, malformed records, unclassified
        user turns, missing mandatory requirements, and missing evidence.
        """

        context = self._load_context()
        records, ledger_errors = self._load_ledger()
        requirements = [
            record
            for record in records
            if record.get("record_type") == "requirement"
        ]
        user_turns = [
            record for record in records if record.get("record_type") == "user_turn"
        ]

        blockers = list(ledger_errors)
        warnings: list[str] = []
        findings: list[RequirementFinding] = []

        known_requirement_ids = {
            str(record.get("requirement_id"))
            for record in requirements
            if record.get("requirement_id")
        }
        for turn in user_turns:
            linked = {
                str(value)
                for value in turn.get("requirement_ids", [])
                if value
            }
            if not linked or not linked.issubset(known_requirement_ids):
                blockers.append(
                    "unclassified user turn "
                    f"{turn.get('turn_id', '<unknown>')} has no complete requirement linkage"
                )

        recorded_refs = {
            str(record.get("source_ref"))
            for record in requirements
            if record.get("source_ref")
        }
        for source_ref in sorted(self._human_answer_refs(context)):
            if source_ref not in recorded_refs:
                blockers.append(
                    f"authoritative human answer is absent from the requirement ledger: "
                    f"{source_ref}"
                )

        for record in requirements:
            requirement_id = str(record.get("requirement_id", ""))
            text = str(record.get("text", "")).strip()
            source_ref = str(record.get("source_ref", ""))
            mandatory = bool(record.get("mandatory", True))
            evidence, reason = self._path_evidence(
                record.get("target_paths", []),
                record.get("acceptance", []),
            )
            if reason is None:
                status = "satisfied"
            elif not mandatory and reason == "no artifact targets were recorded":
                status = "accepted_without_artifact"
                warnings.append(
                    f"optional requirement {requirement_id} has no artifact target"
                )
            else:
                status = "unverified"
                if mandatory:
                    blockers.append(f"{requirement_id}: {reason}")
                else:
                    warnings.append(f"{requirement_id}: {reason}")
            findings.append(
                RequirementFinding(
                    requirement_id=requirement_id,
                    status=status,
                    text=text,
                    source_ref=source_ref,
                    mandatory=mandatory,
                    evidence=evidence,
                    reason=reason or "",
                )
            )

        if not requirements and not ledger_errors:
            blockers.append("requirement ledger contains no explicit requirements")

        satisfied = sum(
            finding.status in {"satisfied", "accepted_without_artifact"}
            for finding in findings
        )
        total = len(findings)
        report = {
            "schema_version": "v1",
            "audit_id": f"audit-{uuid.uuid4().hex[:12]}",
            "run_id": context.get("run_id", ""),
            "workload_name": context.get("workload_name", self.workload_name),
            "auditor": "requirements-auditor",
            "audited_at": _now(),
            "status": "blocked" if blockers else "pass",
            "coverage": {
                "user_turns": len(user_turns),
                "requirements": total,
                "satisfied": satisfied,
                "unverified": sum(
                    finding.status == "unverified" for finding in findings
                ),
                "ledger_errors": len(ledger_errors),
            },
            "requirements": [finding.to_dict() for finding in findings],
            "blocking_issues": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
            "artifact_count": len(self._artifact_paths()),
        }
        return report

    def persist(self, report: Mapping[str, Any]) -> Path:
        """Persist the report, decision, and trace event append-only where required."""

        self.run_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.run_dir / REPORT_NAME
        report_path.write_text(
            json.dumps(dict(report), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        decision = {
            "decision_id": f"{report.get('audit_id', 'audit')}-decision",
            "category": "requirements_conformance",
            "reasoning": (
                "Compared the authoritative run context, captured user turns, "
                "explicit requirement ledger, and workload artifacts."
            ),
            "choice_made": str(report.get("status", "blocked")).upper(),
            "alternatives_considered": ["trust_agent_prose", "skip_audit"],
            "rejection_reasons": {
                "trust_agent_prose": "User requirements require artifact evidence.",
                "skip_audit": "Mandatory conformance gate cannot be bypassed.",
            },
            "confidence": "high",
            "context": {
                "run_id": report.get("run_id", ""),
                "workload_name": report.get("workload_name", self.workload_name),
                "coverage": report.get("coverage", {}),
                "blocking_issues": report.get("blocking_issues", []),
            },
        }
        _json_line(self.run_dir / "decisions.jsonl", decision)
        self._append_trace(report)
        return report_path

    def _append_trace(self, report: Mapping[str, Any]) -> None:
        path = self.logs_dir / "trace_events.jsonl"
        sequence = 0
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    sequence = max(sequence, int(json.loads(line).get("sequence_number", 0)))
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
        event = {
            "timestamp": report.get("audited_at", _now()),
            "run_id": report.get("run_id", ""),
            "trace_id": f"requirements-audit-{report.get('audit_id', '')}",
            "span_id": uuid.uuid4().hex[:16],
            "parent_span_id": None,
            "sequence_number": sequence + 1,
            "thread_id": None,
            "surface": "operational",
            "event_type": "requirements_audit",
            "agent_name": "requirements-auditor",
            "workload_name": report.get("workload_name", self.workload_name),
            "phase": "audit",
            "data_zone": "",
            "status": report.get("status", "blocked"),
            "duration_ms": None,
            "payload": {
                "report_path": f"run/{REPORT_NAME}",
                "coverage": report.get("coverage", {}),
                "blocking_issues": report.get("blocking_issues", []),
            },
        }
        _json_line(path, event)


def audit_workload(workload_dir: str | Path) -> dict[str, Any]:
    """Audit and persist one workload; convenient for the agent/orchestrator."""

    auditor = RequirementAuditor(workload_dir)
    report = auditor.audit()
    auditor.persist(report)
    return report

