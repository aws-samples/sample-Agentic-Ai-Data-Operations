import json
from pathlib import Path

from shared.requirements.auditor import (
    RequirementAuditor,
    append_requirement,
    append_user_turn,
)
from shared.requirements.capture import capture_turn


def _write_context(workload: Path, *, answers=None):
    run = workload / "run"
    run.mkdir(parents=True, exist_ok=True)
    (run / "context.json").write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "run_id": "run-test-001",
                "workload_name": workload.name,
                "started_at": "2026-10-23T12:00:00Z",
                "template_version": "1.0.0",
                "timestamp_mode": "fixed",
                "human_answers": {
                    "zones": ["silver"],
                    "recorded_at": "2026-10-23T12:00:00Z",
                    **(answers or {}),
                },
            }
        ),
        encoding="utf-8",
    )


def test_auditor_blocks_unclassified_user_turn(tmp_path):
    workload = tmp_path / "demo"
    _write_context(workload, answers={"schedule": "daily"})
    append_user_turn(
        workload / "run",
        prompt="What schedule should I use?",
        response="daily",
        phase=1,
    )

    report = RequirementAuditor(workload).audit()

    assert report["status"] == "blocked"
    assert any("unclassified user turn" in issue for issue in report["blocking_issues"])
    assert any("human answer is absent" in issue for issue in report["blocking_issues"])


def test_auditor_passes_with_evidence_and_persists_trace(tmp_path):
    workload = tmp_path / "demo"
    _write_context(workload, answers={"schedule": "daily"})
    logs = workload / "logs"
    logs.mkdir()
    (logs / "trace_events.jsonl").write_text(
        json.dumps({"event_type": "workflow_start", "sequence_number": 1})
        + "\n"
        + json.dumps({"event_type": "phase_complete", "sequence_number": 2})
        + "\n",
        encoding="utf-8",
    )
    (workload / "config").mkdir()
    (workload / "config" / "schedule.yaml").write_text(
        "schedule: daily\n", encoding="utf-8"
    )

    turn_id = append_user_turn(
        workload / "run",
        prompt="What schedule should I use?",
        response="daily",
        phase=1,
    )
    req_id = append_requirement(
        workload / "run",
        text="Use the daily schedule",
        source_ref="context.json#human_answers.schedule",
        target_paths=["config/schedule.yaml"],
        acceptance=["daily"],
    )
    append_requirement(
        workload / "run",
        text="Process the silver zone",
        source_ref="context.json#human_answers.zones",
        target_paths=["config/schedule.yaml"],
    )
    ledger = workload / "run" / "requirements.jsonl"
    lines = [json.loads(line) for line in ledger.read_text().splitlines()]
    lines[0]["requirement_ids"] = [req_id]
    ledger.write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8"
    )

    auditor = RequirementAuditor(workload)
    report = auditor.audit()
    report_path = auditor.persist(report)

    assert report["status"] == "pass"
    assert report["coverage"]["satisfied"] == 2
    assert report_path == workload / "run" / "requirements_audit.json"
    assert report_path.exists()
    assert (workload / "run" / "decisions.jsonl").exists()
    trace = workload / "logs" / "trace_events.jsonl"
    assert trace.exists()
    event = json.loads(trace.read_text().splitlines()[-1])
    assert event["event_type"] == "requirements_audit"
    assert event["status"] == "pass"
    assert turn_id


def test_auditor_blocks_missing_target_artifact(tmp_path):
    workload = tmp_path / "demo"
    _write_context(workload, answers={"primary_key": ["id"]})
    append_requirement(
        workload / "run",
        text="Use id as the primary key",
        source_ref="context.json#human_answers.primary_key",
        target_paths=["config/source.yaml"],
        acceptance=["id"],
    )

    report = RequirementAuditor(workload).audit()

    assert report["status"] == "blocked"
    assert report["coverage"]["unverified"] == 1
    assert any(
        "target artifacts are missing" in issue
        for issue in report["blocking_issues"]
    )


def test_auditor_blocks_conversation_event_without_ledger_turn(tmp_path):
    workload = tmp_path / "demo"
    _write_context(workload)
    logs = workload / "logs"
    logs.mkdir()
    (logs / "conversation_events.jsonl").write_text(
        json.dumps(
            {
                "event_type": "user_responded",
                "thread_id": "thr-unlinked",
                "payload": {"answer_text": "daily"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = RequirementAuditor(workload).audit()

    assert report["status"] == "blocked"
    assert report["coverage"]["conversation_events"] == 1
    assert any(
        "conversation event is not linked" in issue
        for issue in report["blocking_issues"]
    )


def test_auditor_blocks_decision_with_unknown_requirement(tmp_path):
    workload = tmp_path / "demo"
    _write_context(workload)
    decisions = workload / "run" / "decisions.jsonl"
    decisions.write_text(
        json.dumps(
            {
                "decision_id": "d-unknown",
                "category": "transformation",
                "requirement_ids": ["req-does-not-exist"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = RequirementAuditor(workload).audit()

    assert report["status"] == "blocked"
    assert report["coverage"]["decisions"] == 1
    assert any(
        "references unknown requirements" in issue
        for issue in report["blocking_issues"]
    )


def test_capture_buffers_turn_before_run_exists(tmp_path):
    workload = tmp_path / "demo"
    turn_id = capture_turn(
        workload="demo",
        prompt="What is the retention policy?",
        response="Keep seven days",
        cwd=tmp_path,
    )

    assert turn_id
    pending = tmp_path / "workloads" / "demo" / ".requirements_pending" / "requirements.jsonl"
    assert pending.exists()
    record = json.loads(pending.read_text().splitlines()[0])
    assert record["prompt"] == "What is the retention policy?"
