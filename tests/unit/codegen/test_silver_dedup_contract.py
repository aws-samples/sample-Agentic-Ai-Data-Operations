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


class TestDropExactDuplicatesOnlyNeedsSomewhereToPutConflicts:
    """`drop_exact_duplicates_only` separates a redundant row from a genuine conflict.

    A byte-identical row is redundant and safe to drop. Two rows sharing a primary key but
    differing in content are a conflict: choosing one by timestamp discards a value nobody
    reviewed. The first are dropped, the second quarantined — so the strategy is meaningless
    without a quarantine destination.

    Added because a live run's human answered exactly this, the enum had no such value, the
    answer was downgraded to `none`, and the duplicate then survived into Silver: uniqueness
    scored 0.875, critical_failures hit 1, and the gate blocked on every run forever. The
    overall score was 0.98, so nothing that anyone looks at showed a problem.
    """

    def test_strategy_requires_a_quarantine_block(self):
        errors = validate_spec(_spec(dedup_strategy="drop_exact_duplicates_only"), "silver")
        assert errors, "a conflict with nowhere to go must not validate"
        assert any("quarantine" in e for e in errors), errors

    def test_strategy_passes_with_quarantine(self):
        assert not validate_spec(
            _spec(
                dedup_strategy="drop_exact_duplicates_only",
                quarantine={"enabled": True, "location": "s3://bucket/quarantine/probe/"},
            ),
            "silver",
        )

    def test_enabled_quarantine_requires_a_location(self):
        errors = validate_spec(
            _spec(dedup_strategy="none", quarantine={"enabled": True}), "silver"
        )
        assert errors and any("location" in e for e in errors), errors

    def test_it_needs_no_ordering_column(self):
        """Unlike keep_latest/keep_first — there is no row to choose between."""
        assert not validate_spec(
            _spec(
                dedup_strategy="drop_exact_duplicates_only",
                quarantine={"enabled": True, "location": "s3://b/q/"},
            ),
            "silver",
        )


class TestSaltedHashIsNotOptionalOnceChosen:
    """An unsalted SHA-256 of a low-cardinality identifier is not one-way in any useful sense.

    A date of birth is roughly 40,000 candidates; a plan member-id space is often smaller.
    The digest is reversible by enumeration, so `hash` is inadequate for either — and the
    enum offered nothing else. A live HIPAA run answered "SHA-256 + salt", the spec recorded
    `hash`, and the template emitted `F.sha2(col, 256)` with no salt while the LF-Tags and
    the audit record both attested the column was protected.

    `hash_salted` without a salt source would silently degrade to exactly that, so the
    contract forbids the combination.
    """

    def _masking(self, **col):
        return {"enabled": True, "columns": [{"name": "member_dob", **col}]}

    def test_hash_salted_requires_a_salt_secret_id(self):
        errors = validate_spec(
            _spec(dedup_strategy="none", pii_masking=self._masking(method="hash_salted")),
            "silver",
        )
        assert errors, "a salted method with no salt must not validate"
        assert any("salt_secret_id" in e for e in errors), errors

    def test_hash_salted_passes_with_a_salt_secret_id(self):
        assert not validate_spec(
            _spec(
                dedup_strategy="none",
                pii_masking=self._masking(
                    method="hash_salted", salt_secret_id="adop/probe/phi_salt"
                ),
            ),
            "silver",
        )

    def test_an_empty_salt_secret_id_is_not_a_salt(self):
        errors = validate_spec(
            _spec(
                dedup_strategy="none",
                pii_masking=self._masking(method="hash_salted", salt_secret_id=""),
            ),
            "silver",
        )
        assert errors, "an empty secret id must not satisfy the requirement"

    def test_plain_hash_still_needs_no_salt(self):
        """Backward compatibility: every spec written before hash_salted existed."""
        assert not validate_spec(
            _spec(dedup_strategy="none", pii_masking=self._masking(method="hash")), "silver"
        )

    def test_the_spec_carries_a_secret_id_not_a_secret(self):
        """CLAUDE.md security rule 1. A salt value in a spec is a committed credential."""
        import json
        from pathlib import Path

        schema = json.loads(
            (Path(__file__).resolve().parents[3] / "contracts/v1/silver_spec.schema.json").read_text()
        )
        col = schema["properties"]["pii_masking"]["properties"]["columns"]["items"]
        assert "salt_secret_id" in col["properties"]
        assert not any(
            k in col["properties"] for k in ("salt", "salt_value", "secret", "secret_value")
        ), "the contract must not offer a field that would hold the salt itself"


class TestManualScheduleIsExpressible:
    """A null cron must validate, or a manual DAG has no valid spec at all.

    Lives with the other contract guards rather than beside the render tests, because the
    render tests build a spec in memory and never validate it — so narrowing `cron` back to
    string-only broke nothing until this class existed. Found by mutation testing: the
    mutation was applied, every test still passed, and the guard was proved absent.

    `schedule.cron` was `{type: string, minLength: 9}`, required, inside a `schedule` with
    `additionalProperties: false`. "@once" is 5 characters and "None" is 4, so a manual DAG —
    ordinary Airflow — was inexpressible. `minLength` still applies to the string form.
    """

    DAG_BASE = {
        "dataset_name": "probe",
        "schema_version": "v1",
        "tasks": [{"task_id": "t1", "type": "glue_job", "script_path": "s.py"}],
    }

    def _dag(self, **schedule):
        return {**self.DAG_BASE, "schedule": schedule}

    def test_null_cron_validates(self):
        assert not validate_spec(
            self._dag(cron=None, timezone="US/Eastern"), "dag"
        ), "a manual / on-demand DAG must be expressible"

    def test_a_cron_string_still_validates(self):
        assert not validate_spec(self._dag(cron="0 6 * * *", timezone="US/Eastern"), "dag")

    def test_minlength_still_rejects_a_truncated_cron(self):
        """Widening to accept null must not accept a malformed expression."""
        assert validate_spec(self._dag(cron="0 6 *", timezone="US/Eastern"), "dag")

    def test_cron_remains_required(self):
        """Null is a deliberate answer; absent is an unanswered question."""
        errors = validate_spec(self._dag(timezone="US/Eastern"), "dag")
        assert errors and any("cron" in e for e in errors), errors

    def test_a_non_string_non_null_cron_is_still_rejected(self):
        assert validate_spec(self._dag(cron=5, timezone="US/Eastern"), "dag")

    def test_timezone_is_still_required_for_a_manual_dag(self):
        """start_date and any later backfill still need a zone."""
        errors = validate_spec(self._dag(cron=None), "dag")
        assert errors and any("timezone" in e for e in errors), errors


class TestRowSuppressionIsExpressible:
    """A k-anonymity threshold must have somewhere to live in the spec.

    Same reason this sits with the contract guards rather than the render tests: mutation
    testing deleted `post_aggregation_filter` from gold_spec.schema.json and all 212 codegen
    tests still passed, because the render tests build a spec dict in memory and never call
    validate_spec. With the property gone, `additionalProperties: false` rejects every
    suppression spec at validation time while the template happily still handles it — the
    agent would report a contract error for a feature that exists.

    The underlying gap this property closes: `post_aggregation_columns` renders as
    `withColumn()`, so it can add a `k_anonymity_suppressed` boolean but cannot remove the
    disclosed row. A live HIPAA run hit this with 3 cells at n=1.
    """

    GOLD_BASE = {
        "dataset_name": "probe",
        "schema_version": "v1",
        "source_table": "glue_catalog.db.silver_probe",
        "schema_type": "flat_iceberg",
        "grain": {"dimensions": ["service_week"], "temporal": "weekly"},
        "measures": [
            {"name": "claim_count", "source_column": "claim_id", "aggregation": "count"}
        ],
    }

    def _gold(self, **over):
        return {**self.GOLD_BASE, **over}

    def test_a_suppression_predicate_validates(self):
        assert not validate_spec(
            self._gold(post_aggregation_filter="claim_count >= 11"), "gold"
        ), "a k=11 threshold must be expressible, or it can only be a label"

    def test_absent_is_fine(self):
        """Every gold spec written before this property existed must still validate."""
        assert not validate_spec(self._gold(), "gold")

    def test_an_empty_predicate_is_rejected(self):
        """`F.expr("")` raises at Spark runtime; better to fail validation."""
        assert validate_spec(self._gold(post_aggregation_filter=""), "gold")

    def test_a_non_string_predicate_is_rejected(self):
        assert validate_spec(self._gold(post_aggregation_filter=["claim_count >= 11"]), "gold")

    def test_it_is_optional_not_required(self):
        """Unlike cron, silence here is not an unanswered question.

        Most Gold tables have no disclosure threshold, and forcing one would make every
        existing spec invalid — a migration, not a fix.
        """
        import json
        from pathlib import Path

        schema = json.loads(
            (Path(__file__).resolve().parents[3] / "contracts/v1/gold_spec.schema.json").read_text()
        )
        assert "post_aggregation_filter" not in schema.get("required", [])


class TestGateBeforePublishIsExpressible:
    """Gate-before-publish needs three spec fields, and none of them existed.

    With them absent and `additionalProperties: false`, a spec asking for it fails validation
    while the templates handle it perfectly — the agent would report a contract error for a
    feature that works.

    Here for the same reason as the two classes above: mutation testing deleted each of the
    three properties in turn and all 251 codegen tests stayed green, because the render tests
    build spec dicts in memory and never call validate_spec. Three separate mutations, three
    green suites.
    """

    QUALITY_BASE = {
        "dataset_name": "probe",
        "schema_version": "v1",
        "rules": {},
        "quality_gates": {
            "bronze_to_silver": {"overall_score": 0.80, "action_on_failure": "block"},
            "silver_to_gold": {"overall_score": 0.95, "action_on_failure": "block"},
        },
    }
    GOLD_BASE = {
        "dataset_name": "probe",
        "schema_version": "v1",
        "source_table": "glue_catalog.db.silver_probe",
        "schema_type": "flat_iceberg",
        "grain": {"dimensions": ["service_week"], "temporal": "weekly"},
        "measures": [
            {"name": "claim_count", "source_column": "claim_id", "aggregation": "count"}
        ],
    }

    def test_quality_accepts_gate_before_publish(self):
        assert not validate_spec(
            {**self.QUALITY_BASE, "gate_before_publish": True}, "quality"
        ), "the gate cannot be told to publish, so publication stays in the transform"

    def test_silver_accepts_publish_via_gate(self):
        assert not validate_spec(_spec(dedup_strategy="none", publish_via_gate=True), "silver")

    def test_gold_accepts_publish_via_gate(self):
        assert not validate_spec({**self.GOLD_BASE, "publish_via_gate": True}, "gold")

    @pytest.mark.parametrize("spec_type,base_attr,field", [
        ("quality", "QUALITY_BASE", "gate_before_publish"),
        ("gold", "GOLD_BASE", "publish_via_gate"),
    ])
    def test_absent_is_valid(self, spec_type, base_attr, field):
        """Back-compat: every spec written before gating existed."""
        base = getattr(self, base_attr)
        assert field not in base
        assert not validate_spec(base, spec_type)

    def test_silver_absent_is_valid(self):
        assert not validate_spec(_spec(dedup_strategy="none"), "silver")

    @pytest.mark.parametrize("value", ["true", 1, "yes"])
    def test_a_non_boolean_is_rejected(self, value):
        """A truthy string would silently enable gating, or silently not.

        `"false"` is truthy in Jinja, so a string here inverts the meaning of the flag — the
        transform would stage while the reader of the YAML believes it publishes.
        """
        assert validate_spec(_spec(dedup_strategy="none", publish_via_gate=value), "silver")
        assert validate_spec({**self.QUALITY_BASE, "gate_before_publish": value}, "quality")

    def test_none_of_the_three_is_required(self):
        """Silence means "publish as before", which is what every existing workload does."""
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        for spec_type, field in (("quality", "gate_before_publish"),
                                 ("silver", "publish_via_gate"),
                                 ("gold", "publish_via_gate")):
            schema = json.loads((root / f"contracts/v1/{spec_type}_spec.schema.json").read_text())
            assert field in schema["properties"], f"{spec_type}.{field} is not settable"
            assert field not in schema.get("required", []), (
                f"{spec_type}.{field} became required, which invalidates every existing spec"
            )
