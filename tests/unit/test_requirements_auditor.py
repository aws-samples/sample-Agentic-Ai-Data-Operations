import json
from pathlib import Path

from shared.requirements.auditor import (
    RequirementAuditor,
    append_requirement,
    append_user_turn,
)


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
