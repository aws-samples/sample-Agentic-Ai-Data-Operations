"""The gate must publish what the transform staged, and nothing may stage with no publisher.

Three specs have to agree for gate-before-publish to work: the transform's `publish_via_gate`,
the quality spec's `gate_before_publish`, and the DAG task's `--PROMOTE_TO`. No existing check
can see more than one of them — the renderer validates one spec against one contract, and each
template is rendered from its own slots only.

The combination that matters is stage-without-publisher. It never writes unapproved data, but
the DAG reports success while the real table keeps its previous contents and the next zone
reads them. Silent staleness is harder to spot than a failure.

No shipped workload sets either flag yet, so a test that only scanned `workloads/` would pass
by finding nothing — the failure mode this repo keeps producing. Every case below is therefore
synthetic, and the one test that does read the real tree proves it can still fail.
"""

from pathlib import Path

import pytest
import yaml

from shared.codegen.gate_consistency import check_workload

PROJECT_ROOT = Path(__file__).resolve().parents[3]

TABLE = "silver_claims"
QUALIFIED = f"glue_catalog.claims_db.{TABLE}"


def _workload(tmp_path, silver=None, quality=None, dag=None, gold=None):
    config = tmp_path / "config"
    config.mkdir(parents=True, exist_ok=True)
    for name, doc in (("silver.yaml", silver), ("quality.yaml", quality),
                      ("dag.yaml", dag), ("gold.yaml", gold)):
        if doc is not None:
            (config / name).write_text(yaml.safe_dump(doc))
    return tmp_path


def _dag(table_name: str = f"{QUALIFIED}_staging",
         promote_to: str | None = QUALIFIED, zone: str = "silver"):
    params = {"--TABLE_NAME": table_name, "--ZONE": zone}
    if promote_to is not None:
        params["--PROMOTE_TO"] = promote_to
    return {"tasks": [{"task_id": "quality_check_silver", "type": "quality_check",
                       "params": params}]}


class TestAConsistentSetupPasses:
    def test_fully_wired_gate_is_consistent(self, tmp_path):
        problems = check_workload(_workload(
            tmp_path,
            silver={"iceberg_table": TABLE, "publish_via_gate": True},
            quality={"gate_before_publish": True},
            dag=_dag(),
        ))
        assert problems == [], problems

    def test_neither_flag_set_is_consistent(self, tmp_path):
        """The default. Every workload written before this feature existed."""
        assert check_workload(_workload(
            tmp_path,
            silver={"iceberg_table": TABLE},
            quality={},
            dag=_dag(table_name=QUALIFIED, promote_to=None),
        )) == []

    def test_a_workload_with_no_config_dir_is_not_an_error(self, tmp_path):
        assert check_workload(tmp_path) == []


class TestTheSilentStalenessCase:
    """Staging with no publisher: green DAG, unrefreshed table, stale read downstream."""

    def test_stage_without_gate_is_flagged(self, tmp_path):
        problems = check_workload(_workload(
            tmp_path,
            silver={"iceberg_table": TABLE, "publish_via_gate": True},
            quality={},                       # gate_before_publish missing
            dag=_dag(promote_to=None),
        ))
        assert problems
        assert any("nothing promotes" in m for m in problems), problems
        assert any("stale" in m for m in problems), problems

    def test_the_message_names_both_tables(self, tmp_path):
        """An operator has to be able to act on it without reading this module."""
        problems = check_workload(_workload(
            tmp_path,
            silver={"iceberg_table": TABLE, "publish_via_gate": True},
            quality={},
            dag=_dag(promote_to=None),
        ))
        joined = " ".join(problems)
        assert f"{TABLE}_staging" in joined and "quality.yaml" in joined


class TestTheMirrorCase:
    def test_gate_without_any_staging_is_flagged(self, tmp_path):
        problems = check_workload(_workload(
            tmp_path,
            silver={"iceberg_table": TABLE},   # publish_via_gate missing
            quality={"gate_before_publish": True},
            dag=_dag(),
        ))
        assert any("no transform spec sets" in m for m in problems), problems


class TestTheDagHasToCarryPromoteTo:
    def test_missing_promote_to_is_flagged(self, tmp_path):
        """getResolvedOptions raises on a listed argument the caller omits.

        So the task dies before a single rule runs — and it dies with a Glue argument error,
        which reads like an infrastructure problem rather than a spec inconsistency.
        """
        problems = check_workload(_workload(
            tmp_path,
            silver={"iceberg_table": TABLE, "publish_via_gate": True},
            quality={"gate_before_publish": True},
            dag=_dag(promote_to=None),
        ))
        assert any("--PROMOTE_TO" in m for m in problems), problems

    def test_scoring_one_table_and_promoting_another_is_flagged(self, tmp_path):
        """The worst shape: the gate passes on staging and publishes something unchecked."""
        problems = check_workload(_workload(
            tmp_path,
            silver={"iceberg_table": TABLE, "publish_via_gate": True},
            quality={"gate_before_publish": True},
            dag=_dag(table_name="glue_catalog.claims_db.some_other_table"),
        ))
        assert any("different table" in m for m in problems), problems

    def test_promoting_onto_itself_is_flagged(self, tmp_path):
        problems = check_workload(_workload(
            tmp_path,
            silver={"iceberg_table": TABLE, "publish_via_gate": True},
            quality={"gate_before_publish": True},
            dag=_dag(table_name=f"{QUALIFIED}_staging", promote_to=f"{QUALIFIED}_staging"),
        ))
        assert any("no-op" in m for m in problems), problems

    def test_no_quality_task_for_the_zone_is_flagged(self, tmp_path):
        problems = check_workload(_workload(
            tmp_path,
            silver={"iceberg_table": TABLE, "publish_via_gate": True},
            quality={"gate_before_publish": True},
            dag=_dag(zone="gold"),          # stages silver, gates only gold
        ))
        assert any("--ZONE silver" in m for m in problems), problems


class TestGoldStagesToo:
    def test_gold_publish_via_gate_is_checked_on_its_own_zone(self, tmp_path):
        problems = check_workload(_workload(
            tmp_path,
            gold={"iceberg_table": "gold_claims", "publish_via_gate": True},
            quality={"gate_before_publish": True},
            dag={"tasks": [{"task_id": "quality_check_gold", "type": "quality_check",
                            "params": {"--TABLE_NAME": "glue_catalog.claims_db.gold_claims_staging",
                                       "--PROMOTE_TO": "glue_catalog.claims_db.gold_claims",
                                       "--ZONE": "gold"}}]},
        ))
        assert problems == [], problems


class TestTheRealTree:
    WORKLOADS = sorted(
        p.name for p in (PROJECT_ROOT / "workloads").iterdir()
        if p.is_dir() and (p / "config").is_dir()
    )

    @pytest.mark.parametrize("name", WORKLOADS)
    def test_every_shipped_workload_is_consistent(self, name):
        problems = check_workload(PROJECT_ROOT / "workloads" / name)
        assert problems == [], f"{name}:\n  " + "\n  ".join(problems)

    def test_this_scan_is_not_vacuous(self, tmp_path):
        """The check above passes because no workload stages yet, not because it is strong.

        Copies a real workload's config, flips publish_via_gate on, and requires a complaint.
        Without this, deleting the body of check_workload would leave the suite green.
        """
        import shutil

        src = PROJECT_ROOT / "workloads" / "claims_v2" / "config"
        assert src.is_dir(), "fixture workload moved; repoint this test"
        dst = tmp_path / "config"
        shutil.copytree(src, dst)
        spec = yaml.safe_load((dst / "silver.yaml").read_text())
        spec["publish_via_gate"] = True
        (dst / "silver.yaml").write_text(yaml.safe_dump(spec))

        problems = check_workload(tmp_path)
        assert problems, (
            "flipping publish_via_gate on a real workload produced no complaint, so "
            "test_every_shipped_workload_is_consistent proves nothing"
        )


class TestTheRenderedArtifactsAgreeOnTheStagingName:
    """The string "_staging" is spelled in three places and nothing tied them together.

    silver_transform.py.j2 and gold_aggregate.py.j2 each build `{iceberg_table}_staging`, and
    gate_consistency.py checks the DAG's --TABLE_NAME against `{table}_staging`. Change one and
    two of them still agree, which is how the gate ends up scoring a table nobody wrote.

    Templates cannot share a macro here: the renderer loads each from a string through
    jinja2.BaseLoader, so {% import %} has nothing to import from. A test is the only place the
    three can be held to one answer.
    """

    def _render(self, fixture, template, spec_type, tmp_path, **over):
        from shared.codegen.renderer import render
        from shared.codegen.spec_loader import load_spec

        fixtures = PROJECT_ROOT / "tests" / "fixtures" / "replay_workload" / "config"
        spec, spec_hash = load_spec(fixtures / fixture, spec_type)
        out = tmp_path / f"{template}.py"
        render({**spec, **over}, spec_hash, template, "1.0.0", out, "2026-01-01T00:00:00Z")
        return spec, out.read_text()

    def _table_name(self, body):
        line = next(l for l in body.splitlines() if l.strip().startswith("table_name = "))
        return line.split("=", 1)[1].strip().strip('"')

    def test_silver_staging_matches_what_the_consistency_check_expects(self, tmp_path):
        spec, body = self._render("silver.yaml", "silver_transform", "silver", tmp_path,
                                  publish_via_gate=True)
        written = self._table_name(body)
        # What gate_consistency requires the DAG's --TABLE_NAME to end with:
        expected_suffix = f"{spec['iceberg_table']}_staging"
        assert written.endswith(expected_suffix), (
            f"silver_transform writes {written!r}, but gate_consistency requires the DAG to "
            f"point the gate at something ending {expected_suffix!r} — the gate would score a "
            f"table that does not exist"
        )

    def test_gold_staging_matches_what_the_consistency_check_expects(self, tmp_path):
        spec, body = self._render("gold.yaml", "gold_aggregate", "gold", tmp_path,
                                  schema_type="flat_iceberg", publish_via_gate=True)
        written = self._table_name(body)
        assert written.endswith(f"{spec['iceberg_table']}_staging"), written

    def test_a_dag_built_from_the_rendered_name_is_consistent(self, tmp_path):
        """End to end: take the name silver_transform actually wrote, build the DAG from it,
        and require check_workload to be satisfied. Ties the renderer to the checker."""
        spec, body = self._render("silver.yaml", "silver_transform", "silver", tmp_path / "r",
                                  publish_via_gate=True)
        staging = self._table_name(body)
        target = staging[: -len("_staging")]

        wl = tmp_path / "wl"
        (wl / "config").mkdir(parents=True)
        (wl / "config" / "silver.yaml").write_text(yaml.safe_dump(
            {"iceberg_table": spec["iceberg_table"], "publish_via_gate": True}))
        (wl / "config" / "quality.yaml").write_text(yaml.safe_dump({"gate_before_publish": True}))
        (wl / "config" / "dag.yaml").write_text(yaml.safe_dump({"tasks": [
            {"task_id": "quality_check_silver", "type": "quality_check",
             "params": {"--TABLE_NAME": staging, "--PROMOTE_TO": target, "--ZONE": "silver"}}]}))

        problems = check_workload(wl)
        assert problems == [], (
            "the name silver_transform renders and the name gate_consistency accepts have "
            f"diverged:\n  " + "\n  ".join(problems)
        )


class TestStageConnectivity:
    """Specs can all validate, scripts can all compile, and the pipeline still cannot run.

    Three such defects shipped together in one HIPAA workload and were found by a human reading
    generated Terraform, not by any check:

      - the DAG's two quality tasks pointed at a script name that was never rendered
      - silver_spec.source_table named a Bronze table nothing registers
      - that reference carried the Iceberg catalog prefix, so it would have failed even AFTER
        the table was registered

    The third is why this exists. KNOWN_GAPS logged only "source_table names a table
    bronze_ingestion never registers", so the obvious remedy is to register it — and a check that
    verified only EXISTENCE would then pass while Silver still failed, because `glue_catalog` is
    the Iceberg catalog and Bronze is plain Parquet. Fixing the logged half of a defect and
    passing a check is worse than having no check.
    """

    def _wl(self, tmp_path, **files):
        c = tmp_path / "config"
        c.mkdir(parents=True, exist_ok=True)
        for name, doc in files.items():
            if doc is not None:
                (c / f"{name}.yaml").write_text(yaml.safe_dump(doc))
        return tmp_path

    def _with_scripts(self, tmp_path, *names):
        d = tmp_path / "scripts" / "quality"
        d.mkdir(parents=True, exist_ok=True)
        for n in names:
            (d / n).write_text("# rendered\n")
        return tmp_path

    # --- the catalog-prefix edge, both directions --------------------------------------

    def test_iceberg_prefix_on_a_bronze_source_is_flagged(self, tmp_path):
        """Silver reads Bronze, which bronze_ingestion writes as plain Parquet."""
        from shared.codegen.gate_consistency import check_stage_connectivity

        problems = check_stage_connectivity(self._wl(
            tmp_path, silver={"source_table": "glue_catalog.db.bronze_x"}, bronze={"x": 1}))
        assert problems, "the Iceberg prefix on a Parquet source was not caught"
        assert "cannot read a Hive/Parquet table" in problems[0]
        assert "'db.bronze_x'" in problems[0], "the message must name the correct form"

    def test_a_two_part_bronze_reference_is_accepted(self, tmp_path):
        from shared.codegen.gate_consistency import check_stage_connectivity

        assert check_stage_connectivity(self._wl(
            tmp_path, silver={"source_table": "db.bronze_x"}, bronze={"x": 1})) == []

    def test_a_MISSING_prefix_on_a_silver_source_is_also_flagged(self, tmp_path):
        """The asymmetry matters: Gold reads Silver, which IS Iceberg.

        A rule of "never use glue_catalog" would be wrong — it would break every Gold spec.
        """
        from shared.codegen.gate_consistency import check_stage_connectivity

        problems = check_stage_connectivity(self._wl(
            tmp_path, gold={"source_table": "db.silver_x"}))
        assert problems and "without the" in problems[0]

    def test_the_prefix_on_a_gold_source_is_correct(self, tmp_path):
        from shared.codegen.gate_consistency import check_stage_connectivity

        assert check_stage_connectivity(self._wl(
            tmp_path, gold={"source_table": "glue_catalog.db.silver_x"})) == []

    # --- the DAG script edges ---------------------------------------------------------

    def test_a_glue_job_pointing_at_an_unrendered_script_is_flagged(self, tmp_path):
        from shared.codegen.gate_consistency import check_stage_connectivity

        wl = self._with_scripts(self._wl(tmp_path, dag={"tasks": [
            {"task_id": "t", "type": "glue_job", "script_path": "scripts/x/nope.py"}]}),
            "real.py")
        problems = check_stage_connectivity(wl)
        assert problems and "no such file was rendered" in problems[0]

    def test_a_quality_task_with_no_script_path_uses_the_template_default(self, tmp_path):
        """The edge that would have been skipped.

        A checker walking only script_path sees None here and moves on — and quality tasks are
        exactly where script_path is absent, so it would pass the broken pair in silence.
        """
        from shared.codegen.gate_consistency import check_stage_connectivity

        wl = self._with_scripts(self._wl(tmp_path, dag={"tasks": [
            {"task_id": "qc", "type": "quality_check"}]}), "check_quality.py")
        problems = check_stage_connectivity(wl)
        assert problems, "a quality task resolving to the default was not checked at all"
        assert "default" in problems[0] and "quality_check.py" in problems[0]

    def test_a_quality_task_naming_the_rendered_file_passes(self, tmp_path):
        from shared.codegen.gate_consistency import check_stage_connectivity

        wl = self._with_scripts(self._wl(tmp_path, dag={"tasks": [
            {"task_id": "qc", "type": "quality_check",
             "script_path": "scripts/quality/check_quality.py"}]}), "check_quality.py")
        assert check_stage_connectivity(wl) == []

    def test_the_quality_default_matches_the_template(self):
        """The constant here MIRRORS airflow_dag.py.j2's default. Pin them together.

        If the template's default changes and this module does not, the check keeps passing
        while testing a key the template no longer emits.
        """
        import re

        from shared.codegen.gate_consistency import QUALITY_SCRIPT_DEFAULT

        src = (PROJECT_ROOT / "shared/templates/airflow_dag.py.j2").read_text()
        m = re.search(r"task\.script_path \| default\('([^']+)'\)", src)
        assert m, "airflow_dag.py.j2 no longer renders a default for the quality script key"
        assert m.group(1) == QUALITY_SCRIPT_DEFAULT, (
            f"template default is {m.group(1)!r} but gate_consistency mirrors "
            f"{QUALITY_SCRIPT_DEFAULT!r}"
        )

    # --- a workload that produces nothing for Silver to read --------------------------

    def test_silver_reading_a_bronze_table_with_no_bronze_spec_is_flagged(self, tmp_path):
        from shared.codegen.gate_consistency import check_stage_connectivity

        problems = check_stage_connectivity(self._wl(
            tmp_path, silver={"source_table": "db.bronze_x"}))
        assert problems and "no bronze.yaml" in problems[0]


class TestShippedWorkloadsAreConnected:
    """A ratchet over the real tree, like EXEMPT_HEADERLESS.

    customer_master's silver.yaml reads a Bronze table and the workload has no bronze.yaml.
    Not fixable here: authoring a Bronze spec means choosing a source path, format and ingestion
    mode, which CLAUDE.md reserves for the human. Named so a NEW disconnection still fails.
    """

    KNOWN_DISCONNECTED = {
        "customer_master": ["no bronze.yaml"],
    }

    @pytest.mark.parametrize("name", sorted(
        p.name for p in (PROJECT_ROOT / "workloads").iterdir()
        if p.is_dir() and (p / "config").is_dir()))
    def test_shipped_workload_stages_connect(self, name):
        from shared.codegen.gate_consistency import check_stage_connectivity

        problems = check_stage_connectivity(PROJECT_ROOT / "workloads" / name)
        allowed = self.KNOWN_DISCONNECTED.get(name)
        if allowed is None:
            assert not problems, (
                f"workloads/{name} stages do not connect:\n  " + "\n  ".join(problems))
            return
        assert problems, (
            f"workloads/{name} now connects — remove it from KNOWN_DISCONNECTED, or the "
            f"exemption becomes a standing one")
        unexpected = [p for p in problems if not any(f in p for f in allowed)]
        assert not unexpected, (
            f"workloads/{name} has a NEW disconnection beyond its exemption:\n  "
            + "\n  ".join(unexpected))

    def test_the_exemption_list_only_shrinks(self):
        assert len(self.KNOWN_DISCONNECTED) <= 1, (
            "a new workload should connect its stages, not be exempted")


def test_the_cli_actually_runs():
    """Importing the module is not the same as running it, and only the CLI caught this.

    I appended check_stage_connectivity AFTER the `if __name__ == "__main__"` block. On import
    the whole module executes, the guard is False, and the definition is reached — so every test
    passed. Run as `python -m`, main() is called before the definition exists:

        NameError: name 'check_stage_connectivity' is not defined

    CI invokes this as a module, so a green suite would have shipped a CLI that cannot start.
    """
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "-m", "shared.codegen.gate_consistency",
         str(PROJECT_ROOT / "workloads" / "claims_v2")],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    assert "Traceback" not in r.stderr, f"the CLI crashed:\n{r.stderr[-600:]}"
    assert "claims_v2" in r.stdout, f"the CLI produced no report:\n{r.stdout}"
    assert r.returncode == 0, f"claims_v2 should be consistent, got {r.returncode}:\n{r.stdout}"


def test_the_cli_reports_an_inconsistent_workload_nonzero():
    """Exit 0 on a real problem is the failure mode that matters for CI."""
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "-m", "shared.codegen.gate_consistency",
         str(PROJECT_ROOT / "workloads" / "customer_master")],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    assert "Traceback" not in r.stderr
    assert r.returncode == 1, "an inconsistent workload must exit nonzero or CI ignores it"
    assert "INCONSISTENT" in r.stdout
