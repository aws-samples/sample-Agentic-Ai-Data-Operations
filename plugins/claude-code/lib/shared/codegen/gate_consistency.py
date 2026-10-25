"""Cross-spec checks: the stages of a pipeline must actually connect to each other.

Two independent concerns live here, both of which no single-spec validator can see.

Every other validator in this package reads ONE spec. The renderer validates a spec against
its contract, and each template sees only its own slots — so no existing check can notice that
`silver_spec.publish_via_gate` is true while `quality_spec.gate_before_publish` is false.

That combination is the dangerous one, and it is dangerous in a quiet way. Staging without a
publisher never writes unapproved data — the safe direction — but the DAG goes green while the
real Silver table keeps whatever it held before, and `aggregate_gold` then reads that stale
table. A pipeline reporting success on data it did not refresh is harder to notice than one
that fails.

The mirror case is caught at runtime instead: `gate_before_publish` with nothing staging means
TABLE_NAME and PROMOTE_TO are the same table, and the rendered script raises rather than
rewriting it onto itself. Static is still better, so both are checked here.

Usage:
    python3 -m shared.codegen.gate_consistency workloads/*/
"""

import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# transform spec file -> (zone as the DAG names it, the spec field holding the real table name)
STAGING_SPECS = {
    "silver.yaml": ("silver", "iceberg_table"),
    "gold.yaml": ("gold", "iceberg_table"),
}


def _load(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    import yaml

    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def check_workload(workload_dir: Path) -> list[str]:
    """Return one message per inconsistency. Empty list means consistent."""
    workload_dir = Path(workload_dir)
    config = workload_dir / "config"
    if not config.is_dir():
        return []

    quality = _load(config / "quality.yaml")
    dag = _load(config / "dag.yaml")
    gate_publishes = bool((quality or {}).get("gate_before_publish"))

    problems: list[str] = []
    staging_zones: dict[str, str] = {}

    for filename, (zone, table_field) in STAGING_SPECS.items():
        spec = _load(config / filename)
        if not spec or not spec.get("publish_via_gate"):
            continue
        table = spec.get(table_field)
        if not table:
            problems.append(
                f"{filename} sets publish_via_gate but has no {table_field}, so the staging "
                f"table name is undefined"
            )
            continue
        staging_zones[zone] = table

        if not gate_publishes:
            problems.append(
                f"{filename} sets publish_via_gate (writes {table}_staging) but "
                f"quality.yaml does not set gate_before_publish, so nothing promotes "
                f"{table}_staging to {table}. The DAG would report success while {table} "
                f"kept its previous contents and the next zone read stale data."
            )

    if gate_publishes and not staging_zones:
        problems.append(
            "quality.yaml sets gate_before_publish but no transform spec sets "
            "publish_via_gate, so nothing writes a staging table. The gate would be handed "
            "the real table as TABLE_NAME and would refuse at runtime."
        )

    # The DAG has to carry PROMOTE_TO, or getResolvedOptions fails the task outright.
    for zone, table in sorted(staging_zones.items()):
        tasks = [
            t for t in (dag or {}).get("tasks", [])
            if t.get("type") == "quality_check"
            and (t.get("params") or {}).get("--ZONE") == zone
        ]
        if not (dag or {}).get("tasks"):
            problems.append(
                f"{zone} stages via the gate but there is no dag.yaml to carry PROMOTE_TO"
            )
            continue
        if not tasks:
            problems.append(
                f"{zone} stages via the gate but dag.yaml has no quality_check task with "
                f"--ZONE {zone} to promote it"
            )
            continue
        for task in tasks:
            params = task.get("params") or {}
            promote_to = params.get("--PROMOTE_TO")
            table_name = params.get("--TABLE_NAME") or ""
            if not promote_to:
                problems.append(
                    f"dag.yaml task '{task.get('task_id')}' has no --PROMOTE_TO, but "
                    f"gate_before_publish makes it a required Glue argument — the task "
                    f"fails at getResolvedOptions before any check runs"
                )
                continue
            if not table_name.endswith(f"{table}_staging"):
                problems.append(
                    f"dag.yaml task '{task.get('task_id')}' reads --TABLE_NAME "
                    f"{table_name!r}, but the transform writes {table}_staging. The gate "
                    f"would score a different table from the one it promotes."
                )
            if promote_to == table_name:
                problems.append(
                    f"dag.yaml task '{task.get('task_id')}' has --PROMOTE_TO equal to "
                    f"--TABLE_NAME ({promote_to}); the promotion would be a no-op that "
                    f"reports success"
                )
            elif not promote_to.endswith(table):
                problems.append(
                    f"dag.yaml task '{task.get('task_id')}' promotes to {promote_to!r}, "
                    f"which does not name the spec's target table {table!r}"
                )

    return problems


def main() -> int:
    paths = sys.argv[1:]
    if not paths:
        print("No workload directories provided")
        return 0
    bad = False
    for p in paths:
        problems = check_workload(Path(p)) + check_stage_connectivity(Path(p))
        if problems:
            bad = True
            print(f"  INCONSISTENT: {p}")
            for m in problems:
                print(f"        {m}")
        else:
            print(f"  OK: {p}")
    return 1 if bad else 0



# ---------------------------------------------------------------------------
# Stage connectivity
#
# Every spec can validate against its contract, every rendered script can compile, and the
# pipeline can still be unrunnable because the stages do not refer to each other correctly.
# Three such defects shipped simultaneously in one HIPAA workload and were found only by a
# human reading generated Terraform:
#
#   - the DAG's quality tasks pointed at a script name that was never rendered
#   - silver_spec.source_table named a Bronze table nothing registers
#   - that same reference carried the Iceberg catalog prefix, so it would have failed even
#     after the table was registered
#
# The third is the one worth dwelling on. `KNOWN_GAPS` logged only "source_table names a table
# bronze_ingestion never registers", so the obvious remedy is to register it — and a checker
# that verified only EXISTENCE would then go green while Silver still failed, because
# `glue_catalog` is the Iceberg catalog and Bronze is plain Parquet. Fixing the logged half of
# a defect and passing a check is worse than not having the check.
# ---------------------------------------------------------------------------

# The Iceberg catalog name the templates write into. silver_transform and gold_aggregate both
# emit `table_name = "glue_catalog.{db}.{table}"`, so a SILVER or GOLD table is addressed with
# this prefix. A BRONZE table is not: bronze_ingestion ends in
# `df.write.format("parquet").save(landing_zone)` — plain Parquet at a prefix, no catalog
# registration and nothing Iceberg about it.
ICEBERG_CATALOG = "glue_catalog."

# spec file -> (the zone it READS, whether that zone's tables are Iceberg)
READS = {
    "silver.yaml": ("bronze", False),   # Bronze is raw Parquet -> prefix is wrong
    "gold.yaml": ("silver", True),      # Silver is Iceberg      -> prefix is right
}

# airflow_dag.py.j2's DEFAULT for a quality_check task, mirrored here. The template renders
# `task.script_path | default('quality_check.py')`, so a quality task that names no script_path
# still resolves to this name.
#
# It used to be a bare constant that ignored script_path entirely, which is why the two task
# types need separate edges at all: a checker walking only script_path would silently skip every
# quality task — exactly the pair that was broken in both shipped workloads. That correction came
# from the session that hit it; the version I would have written passed them in silence.
#
# This constant is a MIRROR of the template's default. If the template's default changes and this
# does not, the check goes quietly wrong — so test_the_quality_default_matches_the_template pins
# the two together by reading the template source.
QUALITY_SCRIPT_DEFAULT = "quality_check.py"


def check_stage_connectivity(workload_dir: Path) -> list[str]:
    """Return one message per broken link between stages. Empty list means connected."""
    workload_dir = Path(workload_dir)
    config = workload_dir / "config"
    if not config.is_dir():
        return []

    problems: list[str] = []

    # --- the catalog-prefix edge -------------------------------------------------------
    for filename, (reads_zone, reads_iceberg) in READS.items():
        spec = _load(config / filename)
        if not spec:
            continue
        ref = spec.get("source_table")
        if not isinstance(ref, str) or not ref:
            continue
        has_prefix = ref.startswith(ICEBERG_CATALOG)
        if has_prefix and not reads_iceberg:
            problems.append(
                f"{filename} reads {ref!r}, but {reads_zone.title()} is plain Parquet "
                f"(bronze_ingestion ends in .save(landing_zone), registering no table and "
                f"writing nothing Iceberg). `{ICEBERG_CATALOG}` routes to the Iceberg catalog, "
                f"which cannot read a Hive/Parquet table, so spark.table() fails even once the "
                f"table IS registered. Use the two-part name "
                f"{ref[len(ICEBERG_CATALOG):]!r}, resolved through the session catalog."
            )
        elif not has_prefix and reads_iceberg:
            problems.append(
                f"{filename} reads {ref!r} without the `{ICEBERG_CATALOG}` prefix, but "
                f"{reads_zone.title()} is written as Iceberg by its own template. Without the "
                f"prefix this resolves through the session catalog and will not see the "
                f"Iceberg table."
            )

    # --- does anything claim to produce the Bronze table Silver reads? -----------------
    silver = _load(config / "silver.yaml")
    if silver and silver.get("source_table") and not (config / "bronze.yaml").exists():
        problems.append(
            f"silver.yaml reads {silver['source_table']!r} but this workload has no "
            f"bronze.yaml, so no stage in it produces that table. Either add the Bronze spec "
            f"or document the external producer — a Silver run will fail at spark.table()."
        )

    # --- the DAG's script references --------------------------------------------------
    dag = _load(config / "dag.yaml")
    if dag:
        rendered = {p.name for p in (workload_dir / "scripts").rglob("*.py")} \
            if (workload_dir / "scripts").is_dir() else set()
        for task in dag.get("tasks", []):
            ttype, tid = task.get("type"), task.get("task_id")
            if ttype == "glue_job":
                sp = task.get("script_path")
                if not sp:
                    continue        # the template falls back to task_id + '.py'
                if Path(sp).name not in rendered:
                    problems.append(
                        f"dag.yaml task {tid!r} has script_path {sp!r}, but no such file was "
                        f"rendered under scripts/. Rendered: {sorted(rendered) or 'nothing'}. "
                        f"The DAG would upload and run a path that does not exist."
                    )
            elif ttype == "quality_check":
                # Same edge as glue_job, but the template supplies a default when script_path is
                # absent, so the key to check is the resolved one rather than the declared one.
                key = task.get("script_path") or QUALITY_SCRIPT_DEFAULT
                if rendered and Path(key).name not in rendered:
                    problems.append(
                        f"dag.yaml task {tid!r} resolves to the script key {key!r} "
                        + ("(its own script_path)" if task.get("script_path")
                           else f"(airflow_dag.py.j2's default, since it names no script_path)")
                        + f", but no such file was rendered. Rendered: {sorted(rendered)}. "
                        f"Set script_path to the artifact that exists."
                    )

    return problems

if __name__ == "__main__":
    sys.exit(main())
