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
