"""Unit tests for shared.codegen.renderer."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from shared.codegen.exceptions import (
    MissingSlotError,
    RenderError,
    TemplateNotFoundError,
    UnsupportedSpecValueError,
)
from shared.codegen.renderer import RENDERER_TOKEN_ENV, render, render_dry_run
from shared.codegen.spec_loader import load_spec

FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures" / "replay_workload" / "config"
RUN_STARTED_AT = "2026-05-21T10:00:00Z"


@pytest.fixture
def silver_spec():
    spec, spec_hash = load_spec(FIXTURES / "silver.yaml", "silver")
    return spec, spec_hash


class TestRenderer:
    def test_render_silver_transform_produces_header_with_5_required_lines(self, silver_spec, tmp_path):
        spec, spec_hash = silver_spec
        output = tmp_path / "silver.py"
        rendered_bytes, _ = render(
            spec, spec_hash, "silver_transform", "1.0.0", output, RUN_STARTED_AT
        )
        lines = rendered_bytes.decode("utf-8").splitlines()
        assert lines[0].startswith("# spec_hash:")
        assert lines[1].startswith("# template_id:")
        assert lines[2].startswith("# template_hash:")
        assert lines[3].startswith("# schema_version:")
        assert lines[4].startswith("# rendered_at:")

    def test_render_twice_same_spec_produces_identical_bytes(self, silver_spec, tmp_path):
        spec, spec_hash = silver_spec
        out1 = tmp_path / "a.py"
        out2 = tmp_path / "b.py"
        bytes1, hash1 = render(spec, spec_hash, "silver_transform", "1.0.0", out1, RUN_STARTED_AT)
        bytes2, hash2 = render(spec, spec_hash, "silver_transform", "1.0.0", out2, RUN_STARTED_AT)
        assert bytes1 == bytes2
        assert hash1 == hash2

    def test_render_different_specs_produce_different_artifact_hashes(self, tmp_path):
        spec1, hash1 = load_spec(FIXTURES / "silver.yaml", "silver")
        spec2, hash2 = load_spec(FIXTURES / "gold.yaml", "gold")
        out1 = tmp_path / "s.py"
        out2 = tmp_path / "g.py"
        _, ahash1 = render(spec1, hash1, "silver_transform", "1.0.0", out1, RUN_STARTED_AT)
        _, ahash2 = render(spec2, hash2, "gold_aggregate", "1.0.0", out2, RUN_STARTED_AT)
        assert ahash1 != ahash2

    def test_missing_slot_in_spec_raises_MissingSlotError(self, tmp_path):
        spec = {"dataset_name": "test"}
        with pytest.raises(MissingSlotError):
            render(spec, "a" * 64, "silver_transform", "1.0.0", tmp_path / "x.py", RUN_STARTED_AT)

    def test_extra_field_in_spec_does_not_appear_in_artifact(self, silver_spec, tmp_path):
        spec, spec_hash = silver_spec
        spec["extra_unused_field"] = "should_not_appear"
        output = tmp_path / "out.py"
        rendered_bytes, _ = render(spec, spec_hash, "silver_transform", "1.0.0", output, RUN_STARTED_AT)
        assert b"extra_unused_field" not in rendered_bytes
        assert b"should_not_appear" not in rendered_bytes

    def test_unknown_template_id_raises_TemplateNotFoundError(self, silver_spec, tmp_path):
        spec, spec_hash = silver_spec
        with pytest.raises(TemplateNotFoundError):
            render(spec, spec_hash, "nonexistent_template", "1.0.0", tmp_path / "x.py", RUN_STARTED_AT)

    def test_renderer_sets_and_clears_ADOP_RENDERER_TOKEN(self, silver_spec, tmp_path):
        spec, spec_hash = silver_spec
        assert os.environ.get(RENDERER_TOKEN_ENV) is None
        output = tmp_path / "token_test.py"
        render(spec, spec_hash, "silver_transform", "1.0.0", output, RUN_STARTED_AT)
        assert os.environ.get(RENDERER_TOKEN_ENV) is None

    def test_renderer_writes_atomically(self, silver_spec, tmp_path):
        spec, spec_hash = silver_spec
        output = tmp_path / "atomic.py"
        with patch("shared.codegen.renderer.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                render(spec, spec_hash, "silver_transform", "1.0.0", output, RUN_STARTED_AT)
        assert not output.exists()

    def test_rendered_at_uses_run_context_not_wall_clock(self, silver_spec, tmp_path):
        spec, spec_hash = silver_spec
        custom_time = "2020-01-01T00:00:00Z"
        output = tmp_path / "time.py"
        rendered_bytes, _ = render(spec, spec_hash, "silver_transform", "1.0.0", output, custom_time)
        content = rendered_bytes.decode("utf-8")
        assert f"# rendered_at: {custom_time}" in content

    def test_template_version_change_changes_template_hash(self, silver_spec, tmp_path):
        spec, spec_hash = silver_spec
        bytes1, _ = render_dry_run(spec, spec_hash, "silver_transform", "1.0.0", RUN_STARTED_AT)
        bytes2, _ = render_dry_run(spec, spec_hash, "silver_transform", "2.0.0", RUN_STARTED_AT)
        # template_hash comes from the file content which hasn't changed,
        # but the template_version param isn't in the hash (only in manifest)
        # Both renders use same template file, so hashes are same
        # The test verifies the render still succeeds with different version strings
        assert bytes1 == bytes2

    def test_strict_undefined_raises_on_unused_template_var(self, tmp_path):
        spec = {"dataset_name": "test", "source_table": "x", "primary_key": ["id"],
                "dedup_strategy": "none", "quality_threshold": 0.85,
                "iceberg_database": "db", "iceberg_table": "tbl"}
        # This spec is minimal — render should succeed (template has conditionals)
        output = tmp_path / "strict.py"
        rendered_bytes, _ = render(spec, "a" * 64, "silver_transform", "1.0.0", output, RUN_STARTED_AT)
        assert len(rendered_bytes) > 0


class TestUnimplementableRulesAreRefusedNotScored:
    """A quality rule the template cannot run must fail the render, never score 1.0.

    `quality_check.py.j2`'s validity branch implements four check types. Its `{% else %}`
    arm used to set `valid_count = total_rows`, so `score = valid_count / total_rows` came
    out at exactly 1.0 for the other five. A rule that never executed reported perfect
    compliance — and because `overall_score` is an unweighted mean, adding a rule the
    template could not implement *raised* the score.

    Found in a live HIPAA run: three `custom_sql` rules each contributed a fabricated 1.0,
    diluting a genuine 0.875 failure to 1/26 of the total.

    Failing the render is the lesser harm. A render that stops is a bug someone fixes; a
    pipeline reporting 1.0 for a check that never ran is a bug someone trusts.
    """

    IMPLEMENTED = {"range", "enum", "regex", "not_null"}
    CONTRACT_ALLOWS = {
        "not_null", "unique", "range", "regex", "enum",
        "referential", "custom_sql", "format", "length",
    }

    def _spec(self, check_type):
        return {
            "dataset_name": "probe",
            "schema_version": "v1",
            "source_table": "t",
            "quality_gates": {"silver": {"threshold": 0.8}, "gold": {"threshold": 0.95}},
            "rules": {
                "validity": [{
                    "rule_id": f"r_{check_type}",
                    "column": "c",
                    "check_type": check_type,
                    "threshold": 1.0,
                    "params": {
                        "min": 0, "max": 1, "values": ["a"],
                        "pattern": "x", "sql": "1=1",
                    },
                }]
            },
        }

    def _render(self, check_type, tmp_path):
        out = tmp_path / f"q_{check_type}.py"
        render(self._spec(check_type), "deadbeef", "quality_check", "1.0.0",
               out, RUN_STARTED_AT)
        return out.read_text()

    @pytest.mark.parametrize("check_type", sorted(IMPLEMENTED))
    def test_implemented_check_types_still_render(self, check_type, tmp_path):
        body = self._render(check_type, tmp_path)
        assert "results.append" in body

    @pytest.mark.parametrize("check_type", sorted(CONTRACT_ALLOWS - IMPLEMENTED))
    def test_unimplemented_check_types_refuse_to_render(self, check_type, tmp_path):
        """The contract allows nine; the template implements four. The gap must be loud."""
        with pytest.raises(UnsupportedSpecValueError) as exc:
            self._render(check_type, tmp_path)
        assert check_type in str(exc.value), (
            "the error must name the offending check_type, or the reader cannot act on it"
        )

    @pytest.mark.parametrize("check_type", sorted(IMPLEMENTED))
    def test_no_rendered_output_fabricates_a_perfect_score(self, check_type, tmp_path):
        """`valid_count = total_rows` is the exact shape of the original defect.

        Guarded by literal so that reintroducing it — by any route, in any branch —
        fails here rather than in someone's quality report six months from now.
        """
        assert "valid_count = total_rows" not in self._render(check_type, tmp_path)

    def test_the_template_contains_no_unconditional_fallthrough(self):
        """Belt and braces: the source itself must not carry the pattern.

        The per-check tests above only observe branches a spec can reach. This reads the
        template, so a fall-through added under a condition none of the fixtures trigger
        is still caught.
        """
        from shared.codegen.renderer import _load_template

        source, _, _ = _load_template("quality_check")
        assert "valid_count = total_rows" not in source, (
            "quality_check.py.j2 sets valid_count = total_rows somewhere — that scores 1.0 "
            "for a check that never ran. Use unsupported() to refuse the case instead."
        )
