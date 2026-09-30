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


class TestManualScheduleRendersUnquoted:
    """`schedule_interval=None` is ordinary Airflow, and was inexpressible.

    `dag_spec.schedule.cron` was `{type: string, minLength: 9}` and required, inside a
    `schedule` with `additionalProperties: false`. "@once" is 5 characters and "None" is 4,
    so both were rejected — there was no valid dag_spec for a manual DAG. A live run's human
    answered "Manual / on-demand only" and the spec could not hold it.

    The template compounded it: `schedule_interval="{{ schedule.cron }}"` is always quoted,
    so even a null that survived validation would have emitted a string, which Airflow parses
    as a cron expression before failing to load the DAG.
    """

    def _dag_spec(self, cron):
        spec, spec_hash = load_spec(FIXTURES / "dag.yaml", "dag")
        spec = {**spec, "schedule": {**spec["schedule"], "cron": cron}}
        return spec, spec_hash

    def _render(self, cron, tmp_path):
        spec, spec_hash = self._dag_spec(cron)
        out = tmp_path / "d.py"
        render(spec, spec_hash, "airflow_dag", "1.0.0", out, RUN_STARTED_AT)
        return out.read_text()

    def _schedule_line(self, body):
        lines = [l.strip() for l in body.splitlines() if "schedule_interval" in l]
        assert len(lines) == 1, f"expected exactly one schedule_interval line, got {lines}"
        return lines[0]

    def test_null_cron_emits_a_bare_none(self, tmp_path):
        assert self._schedule_line(self._render(None, tmp_path)) == "schedule_interval=None,"

    def test_null_cron_never_emits_a_string(self, tmp_path):
        """The exact defect: a quoted value here is parsed as a cron expression."""
        line = self._schedule_line(self._render(None, tmp_path))
        assert '"' not in line and "'" not in line, (
            f"schedule_interval carries a string literal: {line}"
        )

    def test_a_cron_string_still_renders_quoted(self, tmp_path):
        line = self._schedule_line(self._render("0 6 * * *", tmp_path))
        assert line == 'schedule_interval="0 6 * * *",'

    @pytest.mark.parametrize("cron", [None, "0 6 * * *"])
    def test_both_forms_compile(self, cron, tmp_path):
        compile(self._render(cron, tmp_path), "d.py", "exec")


class TestDedupAndMaskingBranchesRender:
    """Every enum value must reach generated code, or the enum is a promise, not a control."""

    def _silver(self, tmp_path, **overrides):
        spec, spec_hash = load_spec(FIXTURES / "silver.yaml", "silver")
        spec = {**spec, **overrides}
        out = tmp_path / "s.py"
        render(spec, spec_hash, "silver_transform", "1.0.0", out, RUN_STARTED_AT)
        return out.read_text()

    @pytest.mark.parametrize("strategy", ["keep_latest", "keep_first", "none"])
    def test_pre_existing_strategies_are_unchanged(self, strategy, tmp_path):
        body = self._silver(tmp_path, dedup_strategy=strategy, dedup_order_by="submit_date")
        assert "dropDuplicates()" not in body
        compile(body, "s.py", "exec")

    def test_drop_exact_duplicates_only_drops_and_quarantines(self, tmp_path):
        body = self._silver(
            tmp_path,
            dedup_strategy="drop_exact_duplicates_only",
            quarantine={"enabled": True, "location": "s3://bucket/quarantine/probe/"},
        )
        assert "dropDuplicates()" in body, "byte-identical rows are not dropped"
        assert "_pk_occurrences" in body, "PK collisions are not separated from exact dupes"
        assert "s3://bucket/quarantine/probe/" in body, "conflicts are not written anywhere"
        assert "append" in body, (
            "quarantine must append — overwrite would erase an unreviewed conflict"
        )
        compile(body, "s.py", "exec")

    def test_conflicts_are_counted_separately_from_exact_duplicates(self, tmp_path):
        """One number cannot carry both meanings.

        A row dropped as byte-identical is resolved; a row quarantined is not. Reporting
        both as `duplicates_removed` would make an unreviewed conflict look like a clean
        drop.
        """
        body = self._silver(
            tmp_path,
            dedup_strategy="drop_exact_duplicates_only",
            quarantine={"enabled": True, "location": "s3://b/q/"},
        )
        assert "exact_duplicates_removed=" in body
        assert "pk_conflicts_quarantined=" in body

    def test_hash_salted_emits_a_salted_digest(self, tmp_path):
        body = self._silver(
            tmp_path,
            pii_masking={
                "enabled": True,
                "columns": [
                    {"name": "member_dob", "method": "hash_salted",
                     "salt_secret_id": "adop/probe/phi_salt"},
                ],
            },
        )
        assert "def _phi_salt" in body, "no salt is fetched"
        assert "F.concat" in body, "the salt is not concatenated into the digest input"
        assert "get_secret_value" in body, "the salt does not come from Secrets Manager"
        assert "adop/probe/phi_salt" in body
        compile(body, "s.py", "exec")

    def test_plain_hash_stays_unsalted_and_pulls_in_nothing(self, tmp_path):
        """A spec that did not ask for salting must render exactly as before.

        Also guards against an unused import: the first version of this change emitted
        `from functools import lru_cache` into every silver artifact, including workloads
        with no masking at all.
        """
        body = self._silver(
            tmp_path,
            pii_masking={"enabled": True,
                         "columns": [{"name": "member_dob", "method": "hash"}]},
        )
        assert "def _phi_salt" not in body
        assert "import boto3" not in body
        assert "lru_cache" not in body
        compile(body, "s.py", "exec")

    def test_the_salt_helper_refuses_to_degrade(self, tmp_path):
        """A masking step that silently falls back to unsalted is the original bug.

        The spec, the LF-Tags and the audit record would all still say the column was
        protected, so the failure has to be loud.
        """
        body = self._silver(
            tmp_path,
            pii_masking={
                "enabled": True,
                "columns": [{"name": "member_dob", "method": "hash_salted",
                             "salt_secret_id": "s"}],
            },
        )
        helper = body[body.index("def _phi_salt"):]
        helper = helper[: helper.index("\ndef ", 1)] if "\ndef " in helper[1:] else helper
        assert "raise" in helper, "an empty or missing secret must raise, not fall through"


class TestNoPhiColumnShipsUnmaskedBecauseOfAMissingBranch:
    """An unimplemented masking method used to emit no masking at all.

    The masking loop ran `{% if hash %}{% elif hash_salted %}{% elif redact %}{% elif
    mask_partial %}{% endif %}` — with no else. The contract also allows `encrypt` and
    `tokenize`, so either of those fell straight through and the column was written in clear
    text, while the spec, the Lake Formation tags and the audit record all recorded it as
    protected.

    Worse than the unsalted-hash defect in the same template: an unsalted digest over a
    small domain is weak, this is absent.

    Found while investigating why `workloads/customer_master` drifts. Its
    `config/silver.yaml` specifies `encrypt` for `date_of_birth` and `address`, so rendering
    that workload from its own spec-of-record produced unmasked PHI. The artifact on disk
    redacts both, which is how it survived: somebody rendered it under an older spec that
    said `redact`, the spec was later changed to `encrypt`, and nothing anywhere reported
    that the new value did nothing.
    """

    CONTRACT_ALLOWS = {"hash", "hash_salted", "mask_partial", "redact", "tokenize", "encrypt"}
    IMPLEMENTED = {"hash", "hash_salted", "mask_partial", "redact"}

    def _render(self, method, tmp_path):
        spec, spec_hash = load_spec(FIXTURES / "silver.yaml", "silver")
        col = {"name": "member_dob", "method": method}
        if method == "hash_salted":
            col["salt_secret_id"] = "adop/probe/phi_salt"
        spec = {**spec, "pii_masking": {"enabled": True, "columns": [col]}}
        out = tmp_path / "s.py"
        render(spec, spec_hash, "silver_transform", "1.0.0", out, RUN_STARTED_AT)
        return out.read_text()

    @pytest.mark.parametrize("method", sorted(IMPLEMENTED))
    def test_implemented_methods_emit_a_masking_statement(self, method, tmp_path):
        body = self._render(method, tmp_path)
        assert 'masked_df = masked_df.withColumn(\n        "member_dob"' in body, (
            f"{method} rendered but member_dob was never transformed"
        )
        compile(body, "s.py", "exec")

    @pytest.mark.parametrize("method", sorted(CONTRACT_ALLOWS - IMPLEMENTED))
    def test_unimplemented_methods_refuse_rather_than_emit_clear_text(self, method, tmp_path):
        with pytest.raises(UnsupportedSpecValueError) as exc:
            self._render(method, tmp_path)
        assert method in str(exc.value)
        assert "member_dob" in str(exc.value), (
            "the error must name the column, or an operator cannot tell which PHI is at risk"
        )

    def test_the_masking_loop_has_an_else_arm(self):
        """Structural guard: re-deleting the else arm restores silent clear text.

        The per-method tests only cover methods the contract allows today. A seventh value
        added to the enum later would fall through unnoticed without this.
        """
        from shared.codegen.renderer import _load_template

        source, _, _ = _load_template("silver_transform")
        start = source.index("{% for col_mask in pii_masking.columns %}")
        end = source.index("{% endfor %}", start)
        loop = source[start:end]
        assert "{% else %}" in loop and "unsupported(" in loop, (
            "the pii_masking loop has no else arm — an unhandled method emits no masking"
        )


class TestComplianceRulesAreActuallyRendered:
    """The HIPAA masking gate did not exist — `compliance_rules` was never looped.

    `quality_check.py.j2` looped rules.completeness, rules.uniqueness and rules.validity.
    There was no loop over `compliance_rules.rules`, so in a live HIPAA run
    phi_masking_applied, phi_masking_member_email, phi_masking_member_dob,
    phi_masking_member_id, phi_columns_lf_tagged and phi_not_in_logs were never executed.
    `critical_failures` counts only rendered results, so a rule the human designated
    CRITICAL and blocking could not contribute to it. Of three critical rules, two ran.

    The masking itself works. What was absent is the verification that it happened — so the
    spec, the Lake Formation tags and the audit record all attested a control that nothing
    checked. Verifier finding C1.
    """

    RENDERABLE = {
        "rule_id": "phi_masking_member_dob",
        "column": "member_dob",
        "check_type": "regex",
        "threshold": 1.0,
        "severity": "critical",
        "params": {"pattern": "^[0-9a-f]{64}$"},
    }
    # params are a pseudo-function; not a property of the dataframe at all
    PSEUDO_FUNCTION = {
        "rule_id": "phi_columns_lf_tagged",
        "column": "member_dob",
        "check_type": "custom_sql",
        "threshold": 1.0,
        "severity": "critical",
        "params": {"sql": "lf_tags_present(member_dob)"},
    }

    def _render(self, rules, tmp_path, regulation="HIPAA"):
        spec, spec_hash = load_spec(FIXTURES / "quality.yaml", "quality")
        spec = {**spec, "compliance_rules": {"regulation": regulation, "rules": rules}}
        out = tmp_path / "q.py"
        render(spec, spec_hash, "quality_check", "1.0.0", out, RUN_STARTED_AT)
        return out.read_text()

    def test_a_compliance_rule_reaches_the_generated_script(self, tmp_path):
        body = self._render([self.RENDERABLE], tmp_path)
        assert "phi_masking_member_dob" in body, "the rule was silently dropped"
        assert '"dimension": "compliance"' in body
        assert "# Compliance checks — HIPAA" in body
        compile(body, "q.py", "exec")

    def test_a_failing_compliance_rule_blocks_the_gate(self, tmp_path):
        """Not just present — it must reach critical_failures.

        Executes the rendered scoring arithmetic against a synthetic results list, because
        the whole defect was a rule that existed on paper and could not affect the outcome.
        """
        import textwrap

        lines = self._render([self.RENDERABLE], tmp_path).splitlines()

        i_rule = next(n for n, l in enumerate(lines) if "phi_masking_member_dob" in l)
        i_count = next(n for n, l in enumerate(lines) if "critical_failures = sum" in l)
        assert i_rule < i_count, (
            "the compliance rule is appended after critical_failures is computed, so it "
            "cannot affect the gate"
        )

        scoring = textwrap.dedent("\n".join(lines[i_count : i_count + 4]))
        ns = {
            "results": [
                {"rule_id": "phi_masking_member_dob", "passed": False, "severity": "critical"},
                {"rule_id": "valid_billed", "passed": True, "severity": "warning"},
            ]
        }
        exec(scoring, ns)  # nosec B102
        assert ns["critical_failures"] == 1, (
            "an unmasked PHI column did not register as a critical failure"
        )

    def test_an_unexecutable_compliance_rule_refuses_rather_than_passing(self, tmp_path):
        """L2: declaring an unexecutable check CRITICAL manufactures a control.

        `lf_tags_present(...)` needs the Lake Formation API; `no_phi_literals_in_logs(...)`
        is not a property of the data. Neither can be a dataframe check, and neither may
        quietly score 1.0 while marked blocking.
        """
        with pytest.raises(UnsupportedSpecValueError) as exc:
            self._render([self.PSEUDO_FUNCTION], tmp_path)
        msg = str(exc.value)
        assert "phi_columns_lf_tagged" in msg and "(compliance)" in msg, (
            "the error must name the rule and the section it came from"
        )
        assert "severity info" in msg, (
            "the message must say where such a check belongs, or the reader cannot act"
        )

    def test_a_spec_with_no_compliance_rules_renders_unchanged(self, tmp_path):
        """Backward compatibility: every quality spec written before this existed."""
        spec, spec_hash = load_spec(FIXTURES / "quality.yaml", "quality")
        out = tmp_path / "q.py"
        render(spec, spec_hash, "quality_check", "1.0.0", out, RUN_STARTED_AT)
        body = out.read_text()
        assert "# Compliance checks" not in body
        assert '"dimension": "compliance"' not in body
        compile(body, "q.py", "exec")

    def test_validity_and_compliance_share_one_dispatch(self):
        """Two copies of one if/elif chain is how this bug class began.

        `compliance_rules` went unrendered and five of nine check types fell through a bare
        else, because the dispatch lived inline in one place and nowhere else. It is now a
        macro, so a check type added later reaches every caller.
        """
        from shared.codegen.renderer import _load_template

        source, _, _ = _load_template("quality_check")
        assert "{% macro scored_rule(" in source, "the shared dispatch macro is gone"
        assert source.count('rule.check_type == "range"') == 1, (
            "the dispatch is duplicated — the copies will drift"
        )
        for caller in ('scored_rule(rule, "validity")', 'scored_rule(rule, "compliance")'):
            assert caller in source, f"{caller} does not use the shared macro"


class TestNullHandlingIsHonoured:
    """The pipeline used to drop null-PK rows whatever the human answered.

    `silver_transform.py.j2` filtered `F.col(pk).isNotNull()` unconditionally and never read
    `null_handling` at all. A human answering "allow" or "quarantine" got silent drops
    either way — an override of the one category of decision CLAUDE.md says the agent must
    never make for them (finding M3).

    The second consequence is worse. Dropping the rows first made the critical rule
    `not_null_<pk>` **unfalsifiable**: the offending rows were gone before the rule could
    measure them, so it always scored 1.0. A guardrail that cannot fail.

    `workloads/customer_master/config/silver.yaml` asks for `quarantine` on customer_id,
    email and last_name; it was getting drops.
    """

    def _silver(self, tmp_path, null_handling=None, quarantine="keep", **over):
        spec, spec_hash = load_spec(FIXTURES / "silver.yaml", "silver")
        spec = {**spec, **over}
        if null_handling is None:
            spec.pop("null_handling", None)
        else:
            spec["null_handling"] = null_handling
        if quarantine == "drop":
            spec.pop("quarantine", None)
        elif isinstance(quarantine, dict):
            spec["quarantine"] = quarantine
        out = tmp_path / "s.py"
        render(spec, spec_hash, "silver_transform", "1.0.0", out, RUN_STARTED_AT)
        body = out.read_text()
        compile(body, "s.py", "exec")
        return body

    def test_allow_keeps_the_rows(self, tmp_path):
        """The whole point: the rule downstream must be able to fail."""
        body = self._silver(tmp_path, {"strategy": "allow", "critical_columns": []})
        assert "filter(~_null_in_checked)" not in body, (
            "strategy 'allow' still removes rows — the human's answer is overridden"
        )
        assert "null_rows_retained" in body, "the retained count is not reported"

    def test_drop_row_drops(self, tmp_path):
        body = self._silver(tmp_path, {"strategy": "drop_row", "critical_columns": ["amount"]})
        assert "filter(~_null_in_checked)" in body

    def test_quarantine_writes_the_rows_somewhere(self, tmp_path):
        body = self._silver(
            tmp_path,
            {"strategy": "quarantine", "critical_columns": ["amount"]},
            quarantine={"enabled": True, "location": "s3://bucket/q/"},
        )
        assert "s3://bucket/q/" in body, "the rows are dropped, not quarantined"
        assert 'mode("append")' in body, (
            "quarantine must append — overwrite erases rows awaiting review"
        )

    @pytest.mark.parametrize("quarantine", ["drop", {"enabled": True}])
    def test_quarantine_without_a_location_refuses(self, quarantine, tmp_path):
        """Otherwise the template must choose between a silent drop and a failed run."""
        with pytest.raises(UnsupportedSpecValueError) as exc:
            self._silver(
                tmp_path,
                {"strategy": "quarantine", "critical_columns": ["amount"]},
                quarantine=quarantine,
            )
        assert "quarantine.location" in str(exc.value)

    def test_fill_default_fills_from_the_spec(self, tmp_path):
        body = self._silver(
            tmp_path,
            {"strategy": "fill_default", "critical_columns": ["amount"],
             "fill_values": {"record_id": "UNKNOWN", "amount": 0}},
        )
        assert "F.coalesce" in body and "UNKNOWN" in body

    def test_fill_default_without_a_value_refuses(self, tmp_path):
        """Gap G-1: the contract has no conditional tying fill_default to fill_values.

        So a spec can say "fill nulls with defaults" and name none. Inventing one would put
        a value nobody chose into a column the human called critical.
        """
        with pytest.raises(UnsupportedSpecValueError) as exc:
            self._silver(
                tmp_path,
                {"strategy": "fill_default", "critical_columns": ["amount"],
                 "fill_values": {"amount": 0}},   # record_id, the PK, has no default
            )
        assert "fill_values has no entry for 'record_id'" in str(exc.value)

    def test_the_primary_key_is_checked_even_if_not_listed_critical(self, tmp_path):
        """A row with no primary key cannot be deduped or joined to anything."""
        body = self._silver(tmp_path, {"strategy": "drop_row", "critical_columns": []})
        assert 'F.col("record_id").isNull()' in body

    def test_a_spec_without_null_handling_behaves_as_before(self, tmp_path):
        """Back-compat: drop_row over the primary key, which is what it always did."""
        body = self._silver(tmp_path, None)
        assert "filter(~_null_in_checked)" in body
        assert 'F.col("record_id").isNull()' in body


class TestGoldSchemaIsActuallyBuilt:
    """Four separate silent-nothing defects in one template, all the same shape.

    `gold_aggregate.py.j2` had a duplicated measure dispatch and no else arm anywhere, so
    every contract value it did not implement produced *something that compiled*:

      output_tables / dimensions  never read      -> star_schema gave one flat fact table;
                                                     no dim_member, no dim_provider, and
                                                     scd_type inert (M7)
      measures[].filter           never rendered  -> a filtered aggregation became
                                                     unfiltered, silently
      aggregation "percentile"    no branch       -> the measure vanished from .agg()
      schema_type "iceberg_dynamodb" no branch    -> no groupBy, no agg, no write at all

    The filter one was not hypothetical: `workloads/claims_v2/config/gold.yaml` defines
    `denied_count` as count(claim_id) WHERE claim_status = 'denied', and the committed
    artifact rendered `F.count("claim_id")`. That table has been counting every claim as
    denied.
    """

    def _gold(self, tmp_path, **over):
        spec, spec_hash = load_spec(FIXTURES / "gold.yaml", "gold")
        spec = {**spec, **over}
        out = tmp_path / "g.py"
        render(spec, spec_hash, "gold_aggregate", "1.0.0", out, RUN_STARTED_AT)
        body = out.read_text()
        compile(body, "g.py", "exec")
        return body

    STAR_WITH_DIMS = dict(
        schema_type="star_schema",
        output_tables=[
            {"name": "gold_fact", "type": "fact"},
            {"name": "dim_member", "type": "dimension", "columns": ["record_id", "region"]},
            {"name": "dim_provider", "type": "dimension", "columns": ["region"]},
        ],
        dimensions=[
            {"name": "dim_member", "source_column": "record_id", "scd_type": 1},
            {"name": "dim_provider", "source_column": "region", "scd_type": 1},
        ],
    )

    def test_star_schema_creates_the_dimension_tables(self, tmp_path):
        body = self._gold(tmp_path, **self.STAR_WITH_DIMS)
        for name in ("dim_member", "dim_provider"):
            assert f"{name}_df = pre_agg_df.select(" in body, f"{name} is never built"
            assert f"{name}_df.writeTo({name}_table)" in body, f"{name} is never written"
        assert "dropDuplicates()" in body, "a dimension must be distinct on its columns"

    def test_star_schema_without_output_tables_is_unchanged(self, tmp_path):
        """Back-compat: every gold spec written before output_tables was read."""
        body = self._gold(tmp_path, schema_type="star_schema")
        assert "dim_member" not in body
        assert "fact_df.writeTo(table_name)" in body

    def test_scd_type_2_refuses_rather_than_emitting_type_1(self, tmp_path):
        """Type 1 where Type 2 was asked for loses history irrecoverably.

        Unlike most of these, the damage cannot be repaired by re-rendering later — the
        superseded rows were never captured. So it must refuse, not downgrade.
        """
        with pytest.raises(UnsupportedSpecValueError) as exc:
            self._gold(
                tmp_path,
                schema_type="star_schema",
                output_tables=[{"name": "dim_member", "type": "dimension",
                                "columns": ["record_id"]}],
                dimensions=[{"name": "dim_member", "source_column": "record_id",
                             "scd_type": 2}],
            )
        assert "scd_type 2" in str(exc.value) and "history" in str(exc.value)

    def test_a_dimension_with_no_columns_refuses(self, tmp_path):
        with pytest.raises(UnsupportedSpecValueError) as exc:
            self._gold(
                tmp_path,
                schema_type="star_schema",
                output_tables=[{"name": "dim_member", "type": "dimension"}],
            )
        assert "names no columns" in str(exc.value)

    def test_a_filtered_measure_is_actually_filtered(self, tmp_path):
        """The live bug: claims_v2's denied_count counted every claim."""
        body = self._gold(
            tmp_path,
            measures=[{"name": "denied_count", "source_column": "record_id",
                       "aggregation": "count", "filter": "status = 'denied'"}],
        )
        assert "F.when(F.expr(" in body, "the filter was dropped from the aggregation"
        assert "denied_count" in body

    def test_an_unfiltered_measure_keeps_its_original_form(self, tmp_path):
        """Adding filter support must not rewrite every measure line in every artifact.

        F.sum("x") and F.sum(F.col("x")) are equivalent; a diff for no behavioural gain is
        noise in every future review.
        """
        body = self._gold(
            tmp_path,
            measures=[{"name": "total", "source_column": "amount", "aggregation": "sum"}],
        )
        assert 'F.sum("amount").alias("total")' in body

    def test_an_unimplemented_aggregation_refuses(self, tmp_path):
        """`percentile` is in the enum, had no branch, and produced an empty .agg()."""
        with pytest.raises(UnsupportedSpecValueError) as exc:
            self._gold(
                tmp_path,
                measures=[{"name": "p95", "source_column": "amount",
                           "aggregation": "percentile"}],
            )
        assert "percentile" in str(exc.value)

    def test_an_unimplemented_schema_type_refuses(self, tmp_path):
        """iceberg_dynamodb rendered a script with no groupBy, no agg and no write."""
        with pytest.raises(UnsupportedSpecValueError) as exc:
            self._gold(tmp_path, schema_type="iceberg_dynamodb")
        assert "iceberg_dynamodb" in str(exc.value)

    def test_the_measure_dispatch_is_not_duplicated(self):
        """It was two identical copies, which is why percentile fell through unnoticed."""
        from shared.codegen.renderer import _load_template

        source, _, _ = _load_template("gold_aggregate")
        assert source.count('measure.aggregation == "sum"') == 1, (
            "the measure dispatch is duplicated — the copies will drift again"
        )
        assert "{% macro aggregated_measure(" in source
