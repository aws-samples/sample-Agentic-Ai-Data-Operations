"""Unit tests for shared.codegen.spec_loader."""

import copy
from pathlib import Path

import pytest

from shared.codegen.exceptions import SchemaVersionError, SpecValidationError
from shared.codegen.spec_loader import compute_spec_hash, load_spec, validate_spec

FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures" / "replay_workload" / "config"


@pytest.fixture
def silver_spec_path():
    return FIXTURES / "silver.yaml"


@pytest.fixture
def silver_spec_dict(silver_spec_path):
    import yaml
    with open(silver_spec_path) as f:
        return yaml.safe_load(f)


class TestLoadSpec:
    def test_valid_silver_spec_loads_and_returns_hash(self, silver_spec_path):
        spec, spec_hash = load_spec(silver_spec_path, "silver")
        assert isinstance(spec, dict)
        assert len(spec_hash) == 64
        assert all(c in "0123456789abcdef" for c in spec_hash)

    def test_spec_hash_is_deterministic_across_calls(self, silver_spec_path):
        hashes = set()
        for _ in range(100):
            _, h = load_spec(silver_spec_path, "silver")
            hashes.add(h)
        assert len(hashes) == 1

    def test_spec_hash_changes_on_any_field_modification(self, silver_spec_dict):
        original_hash = compute_spec_hash(silver_spec_dict)
        modified = copy.deepcopy(silver_spec_dict)
        modified["quality_threshold"] = 0.90
        modified_hash = compute_spec_hash(modified)
        assert original_hash != modified_hash

    def test_spec_hash_is_stable_under_key_reordering(self, silver_spec_dict):
        import json
        hash1 = compute_spec_hash(silver_spec_dict)
        reversed_dict = dict(reversed(list(silver_spec_dict.items())))
        hash2 = compute_spec_hash(reversed_dict)
        assert hash1 == hash2

    def test_invalid_spec_missing_required_field_raises_SpecValidationError(self, tmp_path):
        import yaml
        spec = {"dataset_name": "test"}
        spec_file = tmp_path / "bad.yaml"
        spec_file.write_text(yaml.dump(spec))
        with pytest.raises(SpecValidationError):
            load_spec(spec_file, "silver")

    def test_invalid_spec_extra_field_raises_SpecValidationError(self, tmp_path, silver_spec_dict):
        import yaml
        silver_spec_dict["unknown_field"] = "surprise"
        spec_file = tmp_path / "extra.yaml"
        spec_file.write_text(yaml.dump(silver_spec_dict))
        with pytest.raises(SpecValidationError):
            load_spec(spec_file, "silver")

    def test_unknown_schema_version_raises_SchemaVersionError(self, silver_spec_path):
        with pytest.raises(SchemaVersionError):
            load_spec(silver_spec_path, "silver", schema_version="v99")

    def test_silver_spec_rejects_dedup_strategy_not_in_enum(self, tmp_path, silver_spec_dict):
        import yaml
        silver_spec_dict["dedup_strategy"] = "merge_all"
        spec_file = tmp_path / "bad_enum.yaml"
        spec_file.write_text(yaml.dump(silver_spec_dict))
        with pytest.raises(SpecValidationError):
            load_spec(spec_file, "silver")

    def test_silver_spec_rejects_quality_threshold_below_0_80(self, tmp_path, silver_spec_dict):
        import yaml
        silver_spec_dict["quality_threshold"] = 0.50
        spec_file = tmp_path / "low_thresh.yaml"
        spec_file.write_text(yaml.dump(silver_spec_dict))
        with pytest.raises(SpecValidationError):
            load_spec(spec_file, "silver")

    def test_silver_spec_rejects_empty_primary_key(self, tmp_path, silver_spec_dict):
        import yaml
        silver_spec_dict["primary_key"] = []
        spec_file = tmp_path / "empty_pk.yaml"
        spec_file.write_text(yaml.dump(silver_spec_dict))
        with pytest.raises(SpecValidationError):
            load_spec(spec_file, "silver")


def _run_context(**overrides) -> dict:
    """Minimal valid run/context.json payload."""
    ctx = {
        "schema_version": "v1",
        "run_id": "run-abc123",
        "workload_name": "claims",
        "started_at": "2026-09-16T10:00:00Z",
        "template_version": "1.0.0",
        "timestamp_mode": "fixed",
        "human_answers": {
            "zones": ["bronze", "silver", "gold"],
            "recorded_at": "2026-09-16T09:55:00Z",
        },
    }
    ctx.update(overrides)
    return ctx


class TestRunContextSpec:
    def test_minimal_run_context_validates(self):
        assert validate_spec(_run_context(), "run_context") == []

    def test_load_run_context_from_json_file(self, tmp_path):
        import json
        path = tmp_path / "context.json"
        path.write_text(json.dumps(_run_context()))
        ctx, ctx_hash = load_spec(path, "run_context")
        assert ctx["workload_name"] == "claims"
        assert len(ctx_hash) == 64

    def test_carries_parallel_agent_answers_verbatim(self):
        """4.3 and 4.4 can run in parallel — both read these two strings."""
        ctx = _run_context()
        ctx["human_answers"]["dedup_strategy"] = "keep latest by ingest_ts, drop the rest"
        ctx["human_answers"]["null_handling"] = "quarantine rows with null claim_id"
        assert validate_spec(ctx, "run_context") == []

    def test_rejects_wall_clock_timestamp_mode(self):
        errors = validate_spec(_run_context(timestamp_mode="now"), "run_context")
        assert errors

    def test_rejects_unknown_top_level_field(self):
        errors = validate_spec(_run_context(surprise="x"), "run_context")
        assert errors

    def test_rejects_human_answers_without_zones(self):
        ctx = _run_context(human_answers={"recorded_at": "2026-09-16T09:55:00Z"})
        assert validate_spec(ctx, "run_context")

    def test_rejects_quality_threshold_above_one(self):
        ctx = _run_context()
        ctx["human_answers"]["quality_thresholds"] = {"silver": 1.5}
        assert validate_spec(ctx, "run_context")

    def test_previous_phases_accepts_completed_phase_record(self):
        ctx = _run_context(previous_phases=[{
            "phase": 4.3,
            "agent": "transformation",
            "output_hash": "a" * 64,
            "status": "success",
            "completed_at": "2026-09-16T10:20:00Z",
        }])
        assert validate_spec(ctx, "run_context") == []

    def test_previous_phases_rejects_unknown_agent(self):
        ctx = _run_context(previous_phases=[
            {"phase": 4, "agent": "mystery", "status": "success"}
        ])
        assert validate_spec(ctx, "run_context")

    def test_hash_is_stable_under_key_reordering(self):
        ctx = _run_context()
        assert compute_spec_hash(ctx) == compute_spec_hash(
            dict(reversed(list(ctx.items())))
        )
