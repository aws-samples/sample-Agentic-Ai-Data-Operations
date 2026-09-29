"""The silver contract must not let a non-deterministic dedup through.

`silver_transform.py.j2` falls back to `orderBy(F.monotonically_increasing_id())` when
`dedup_order_by` is absent. That ordering is arbitrary and unstable across runs, so a spec
saying `keep_latest` would keep an arbitrary row — breaking both the human's stated intent
and the transformation-idempotency property. The contract forbids that combination.
"""

import pytest

from shared.codegen.spec_loader import validate_spec

BASE = {
    "dataset_name": "probe",
    "schema_version": "v1",
    "source_table": "bronze.probe_claims",
    "primary_key": ["claim_id"],
    "quality_threshold": 0.85,
    "iceberg_database": "silver_db",
    "iceberg_table": "probe_claims",
}


def _spec(**overrides) -> dict:
    return {**BASE, **overrides}


class TestDedupOrderingRequired:
    @pytest.mark.parametrize("strategy", ["keep_latest", "keep_first"])
    def test_ordered_strategy_demands_an_ordering_column(self, strategy):
        errors = validate_spec(_spec(dedup_strategy=strategy), "silver")
        assert errors, f"{strategy} without dedup_order_by must be rejected"
        assert any("dedup_order_by" in str(e) for e in errors), errors

    @pytest.mark.parametrize("strategy", ["keep_latest", "keep_first"])
    def test_ordered_strategy_passes_with_ordering_column(self, strategy):
        assert not validate_spec(
            _spec(dedup_strategy=strategy, dedup_order_by="ingest_ts"), "silver"
        )

    def test_none_needs_no_ordering_column(self):
        """With no dedup, the template never builds a window — nothing to order."""
        assert not validate_spec(_spec(dedup_strategy="none"), "silver")

    def test_ordering_column_alone_is_not_enough(self):
        """dedup_strategy stays required regardless."""
        assert validate_spec(_spec(dedup_order_by="ingest_ts"), "silver")


class TestIcebergTargetRequired:
    @pytest.mark.parametrize("missing", ["iceberg_database", "iceberg_table"])
    def test_render_target_is_required_by_the_contract(self, missing):
        spec = _spec(dedup_strategy="none")
        del spec[missing]
        errors = validate_spec(spec, "silver")
        assert errors, f"{missing} must fail validation, not MissingSlotError at render"
        assert any(missing in str(e) for e in errors), errors
