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
