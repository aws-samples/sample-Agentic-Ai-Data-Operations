"""Integration tests proving bit-for-bit deterministic codegen."""

import copy
from pathlib import Path

import pytest
import yaml

from shared.codegen.drift_validator import verify_artifact, verify_workload
from shared.codegen.renderer import render
from shared.codegen.spec_loader import compute_spec_hash, load_spec

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "replay_workload" / "config"
RUN_STARTED_AT = "2026-05-21T10:00:00Z"


class TestDeterminismReplay:
    def test_replay_produces_byte_identical_artifacts(self, tmp_path):
        spec, spec_hash = load_spec(FIXTURES / "silver.yaml", "silver")

        out1 = tmp_path / "run1" / "silver.py"
        out2 = tmp_path / "run2" / "silver.py"
        out1.parent.mkdir(parents=True)
        out2.parent.mkdir(parents=True)

        bytes1, hash1 = render(spec, spec_hash, "silver_transform", "1.0.0", out1, RUN_STARTED_AT)
        bytes2, hash2 = render(spec, spec_hash, "silver_transform", "1.0.0", out2, RUN_STARTED_AT)

        assert bytes1 == bytes2
        assert hash1 == hash2

    def test_replay_with_different_run_started_at_only_changes_header(self, tmp_path):
        spec, spec_hash = load_spec(FIXTURES / "silver.yaml", "silver")

        out1 = tmp_path / "t1.py"
        out2 = tmp_path / "t2.py"

        bytes1, _ = render(spec, spec_hash, "silver_transform", "1.0.0", out1, "2026-01-01T00:00:00Z")
        bytes2, _ = render(spec, spec_hash, "silver_transform", "1.0.0", out2, "2026-12-31T23:59:59Z")

        content1 = bytes1.decode("utf-8")
        content2 = bytes2.decode("utf-8")

        # Strip the 5-line header
        body1 = "\n".join(content1.splitlines()[5:])
        body2 = "\n".join(content2.splitlines()[5:])

        assert body1 == body2
        assert content1 != content2  # headers differ

    def test_one_byte_spec_change_changes_at_least_one_artifact_hash(self, tmp_path):
        spec_orig, hash_orig = load_spec(FIXTURES / "silver.yaml", "silver")
        spec_mod = copy.deepcopy(spec_orig)
        spec_mod["quality_threshold"] = 0.86  # was 0.85
        hash_mod = compute_spec_hash(spec_mod)

        out1 = tmp_path / "orig.py"
        out2 = tmp_path / "mod.py"

        _, ahash1 = render(spec_orig, hash_orig, "silver_transform", "1.0.0", out1, RUN_STARTED_AT)
        _, ahash2 = render(spec_mod, hash_mod, "silver_transform", "1.0.0", out2, RUN_STARTED_AT)

        assert ahash1 != ahash2

    def test_drift_validator_passes_on_freshly_rendered_workload(self, tmp_path):
        import shutil

        workload = tmp_path / "fresh_workload"
        config_dir = workload / "config"
        scripts_dir = workload / "scripts" / "transform"
        config_dir.mkdir(parents=True)
        scripts_dir.mkdir(parents=True)

        shutil.copy(FIXTURES / "silver.yaml", config_dir / "silver.yaml")

        spec, spec_hash = load_spec(config_dir / "silver.yaml", "silver")
        output = scripts_dir / "bronze_to_silver.py"
        render(spec, spec_hash, "silver_transform", "1.0.0", output, RUN_STARTED_AT)

        report = verify_workload(workload)
        assert report.ok is True
        assert len(report.reports) == 1
        assert report.reports[0].ok is True

    def test_drift_validator_fails_after_hand_edit_to_any_artifact(self, tmp_path):
        import shutil

        workload = tmp_path / "edited_workload"
        config_dir = workload / "config"
        scripts_dir = workload / "scripts" / "transform"
        config_dir.mkdir(parents=True)
        scripts_dir.mkdir(parents=True)

        shutil.copy(FIXTURES / "silver.yaml", config_dir / "silver.yaml")

        spec, spec_hash = load_spec(config_dir / "silver.yaml", "silver")
        output = scripts_dir / "bronze_to_silver.py"
        render(spec, spec_hash, "silver_transform", "1.0.0", output, RUN_STARTED_AT)

        # Hand-edit: flip one character
        content = output.read_text()
        output.write_text(content + "\n# sneaky edit")

        report = verify_workload(workload)
        assert report.ok is False
        assert any(not r.ok for r in report.reports)
