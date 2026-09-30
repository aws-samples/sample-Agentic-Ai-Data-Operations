"""Cross-spec check: if a transform stages, the gate must actually publish.

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
        problems = check_workload(Path(p))
        if problems:
            bad = True
            print(f"  INCONSISTENT: {p}")
            for m in problems:
                print(f"        {m}")
        else:
            print(f"  OK: {p}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
