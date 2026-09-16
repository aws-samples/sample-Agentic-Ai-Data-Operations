"""Unit tests for .claude/hooks/inject_run_context.py.

The hook is loaded in-process and pointed at a tmp_path so the tests never depend
on which workloads happen to exist in the repo.
"""

import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
HOOK_PATH = PROJECT_ROOT / ".claude" / "hooks" / "inject_run_context.py"


@pytest.fixture
def hook():
    """Fresh module instance — each test rebinds PROJECT_ROOT independently."""
    spec = importlib.util.spec_from_file_location("inject_run_context", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _context(**overrides) -> dict:
    ctx = {
        "schema_version": "v1",
        "run_id": "run-abc123",
        "workload_name": "claims",
        "started_at": "2026-09-16T10:00:00Z",
        "template_version": "1.0.0",
        "timestamp_mode": "fixed",
        "human_answers": {
            "zones": ["bronze", "silver"],
            "recorded_at": "2026-09-16T09:55:00Z",
            "dedup_strategy": "keep latest by ingest_ts",
        },
    }
    ctx.update(overrides)
    return ctx


def _write_run(root: Path, workload: str, ctx, decisions: list[str] | None = None) -> Path:
    run_dir = root / "workloads" / workload / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = ctx if isinstance(ctx, str) else json.dumps(ctx)
    (run_dir / "context.json").write_text(payload)
    if decisions is not None:
        (run_dir / "decisions.jsonl").write_text("".join(d + "\n" for d in decisions))
    return run_dir


def _run(hook, monkeypatch, root: Path, capsys) -> str:
    """Invoke the hook against `root` and return additionalContext ("" if silent)."""
    monkeypatch.setattr(hook, "PROJECT_ROOT", root)
    monkeypatch.setattr(hook.sys.stdin, "read", lambda: "{}", raising=False)
    hook.main()
    out = capsys.readouterr().out
    if not out.strip():
        return ""
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


class TestSilence:
    def test_no_workloads_emits_nothing(self, hook, monkeypatch, tmp_path, capsys):
        assert _run(hook, monkeypatch, tmp_path, capsys) == ""

    def test_workload_without_run_dir_emits_nothing(self, hook, monkeypatch, tmp_path, capsys):
        (tmp_path / "workloads" / "claims" / "config").mkdir(parents=True)
        assert _run(hook, monkeypatch, tmp_path, capsys) == ""

    def test_deployed_run_is_not_in_flight(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", _context(current_phase="5.9"))
        assert _run(hook, monkeypatch, tmp_path, capsys) == ""

    def test_complete_run_is_not_in_flight(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", _context(current_phase="complete"))
        assert _run(hook, monkeypatch, tmp_path, capsys) == ""


class TestInFlightRun:
    def test_reports_identity_and_phase(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", _context(current_phase="4.3"))
        ctx = _run(hook, monkeypatch, tmp_path, capsys)
        assert "claims" in ctx
        assert "run-abc123" in ctx
        assert "4.3" in ctx

    def test_reports_furthest_completed_step(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", _context(
            current_phase="4.4",
            previous_phases=[
                {"phase": 4.2, "agent": "metadata", "status": "success"},
                {"phase": 4.3, "agent": "transformation", "status": "success"},
            ],
        ))
        ctx = _run(hook, monkeypatch, tmp_path, capsys)
        assert "Step 4.3 (transformation) -> success" in ctx

    def test_says_so_when_no_subagent_has_run(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", _context())
        assert "no sub-agent has completed yet" in _run(hook, monkeypatch, tmp_path, capsys)

    def test_lists_answered_keys_and_asserts_authority(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", _context())
        ctx = _run(hook, monkeypatch, tmp_path, capsys)
        assert "dedup_strategy" in ctx and "zones" in ctx
        assert "recorded_at" not in ctx  # bookkeeping, not an answer
        assert "AUTHORITATIVE" in ctx

    def test_flags_unsatisfied_phase_1_gate(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", _context(human_answers={}))
        ctx = _run(hook, monkeypatch, tmp_path, capsys)
        assert "gate is NOT satisfied" in ctx

    def test_includes_recent_decisions(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", _context(), decisions=[
            json.dumps({"agent": "metadata", "choice_made": "claim_id as PK"}),
        ])
        assert "claim_id as PK" in _run(hook, monkeypatch, tmp_path, capsys)

    def test_caps_decision_tail_and_keeps_newest(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", _context(), decisions=[
            json.dumps({"agent": "a", "choice_made": f"decision-{i}"}) for i in range(12)
        ])
        ctx = _run(hook, monkeypatch, tmp_path, capsys)
        assert "decision-11" in ctx
        assert "decision-0\n" not in ctx
        assert ctx.count("- a: decision-") == hook.MAX_DECISIONS

    def test_skips_malformed_decision_lines(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", _context(), decisions=[
            "{not json",
            "",
            json.dumps({"agent": "quality", "choice_made": "threshold 0.95"}),
        ])
        ctx = _run(hook, monkeypatch, tmp_path, capsys)
        assert "threshold 0.95" in ctx
        assert "not json" not in ctx


class TestMultipleRuns:
    def test_most_recently_started_run_wins(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", _context(
            workload_name="claims", started_at="2026-09-14T08:00:00Z"))
        _write_run(tmp_path, "orders", _context(
            workload_name="orders", run_id="run-newer", started_at="2026-09-16T08:00:00Z"))
        ctx = _run(hook, monkeypatch, tmp_path, capsys)
        assert "workload:   orders" in ctx
        assert "Other in-flight runs: claims" in ctx


class TestResilience:
    def test_malformed_context_warns_instead_of_raising(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", "this is not json")
        ctx = _run(hook, monkeypatch, tmp_path, capsys)
        assert "WARNING" in ctx
        assert "not valid JSON" in ctx

    def test_non_object_context_warns(self, hook, monkeypatch, tmp_path, capsys):
        _write_run(tmp_path, "claims", "[1, 2, 3]")
        assert "not a JSON object" in _run(hook, monkeypatch, tmp_path, capsys)

    def test_good_run_still_reported_alongside_a_broken_one(
        self, hook, monkeypatch, tmp_path, capsys
    ):
        _write_run(tmp_path, "claims", _context(workload_name="claims"))
        _write_run(tmp_path, "broken", "}{")
        ctx = _run(hook, monkeypatch, tmp_path, capsys)
        assert "workload:   claims" in ctx
        assert "WARNING" in ctx


class TestSchemaAgreement:
    def test_emitted_fields_validate_against_the_contract(self):
        """The hook only reads fields the run_context contract allows."""
        from shared.codegen.spec_loader import validate_spec

        assert validate_spec(_context(
            current_phase="4.3",
            previous_phases=[{"phase": 4.2, "agent": "metadata", "status": "success"}],
        ), "run_context") == []

    @pytest.mark.parametrize("phase", ["4.3", "0", "5.11", "complete"])
    def test_contract_accepts_phases_the_hook_understands(self, phase):
        from shared.codegen.spec_loader import validate_spec

        assert validate_spec(_context(current_phase=phase), "run_context") == []

    def test_contract_rejects_a_nonsense_phase(self):
        from shared.codegen.spec_loader import validate_spec

        assert validate_spec(_context(current_phase="phase four"), "run_context")
