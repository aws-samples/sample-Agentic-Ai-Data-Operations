#!/usr/bin/env python3
"""Render a workload artifact from its spec, using the plugin's vendored codegen.

Why this exists
---------------
In a checkout of the ADOP repository a sub-agent can `import shared.codegen` and
call `render()` directly. In a user's own repository there is no `shared/`, so the
plugin vendors the engine under `lib/` and this script is the entry point the
agents reach it through:

    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/adop_render.py" \
        --workload workloads/claims --template silver_transform \
        --out workloads/claims/scripts/transform/bronze_to_silver.py

Sub-agents hold `Bash`, so shelling out costs nothing and keeps the vendored
library out of the user's import path.

Why the vendored copy needs no edits
------------------------------------
`shared/codegen/renderer.py` resolves its template directory by walking three
parents up from `__file__` and appending `shared/templates`; `spec_loader.py` does
the same for `contracts`. Mirroring the repo's relative layout under `lib/` makes
both resolve correctly, so every vendored file is byte-identical to its source and
`tests/unit/test_plugin_translation.py` can compare them with `cmp`. Rewriting the
paths — as an earlier attempt at this plugin did, via ADOP_TEMPLATES_DIR — would
have made that check impossible, and an unverifiable copy is how the previous
plugin's skills silently went stale.

Spec discovery
--------------
Templates map to the contract that validates their spec. The mapping mirrors
`shared/templates/*.j2` and is asserted against the vendored contracts at startup,
so a template added upstream without a matching schema fails loudly here rather
than rendering something unvalidated.
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
LIB = PLUGIN_ROOT / "lib"

# The vendored tree is laid out so `import shared.codegen` resolves and the
# library's own relative path arithmetic lands on lib/shared/templates and
# lib/contracts. Nothing else is added to sys.path.
sys.path.insert(0, str(LIB))

from shared.codegen.exceptions import (  # noqa: E402
    MissingSlotError,
    RenderError,
    SpecValidationError,
    TemplateNotFoundError,
)
from shared.codegen.renderer import render  # noqa: E402
from shared.codegen.spec_loader import load_spec  # noqa: E402

# template_id -> (spec file stem under <workload>/config/, contract, VERSION key)
#
# shared/templates/VERSION is an env-style file with a key per template family, not
# a single version. .claude/agents/dag-agent.md names DAG_TEMPLATE_VERSION
# explicitly; the transformation and quality agents say "from VERSION" without
# naming a key, so they take the family key matching their template. TEMPLATE_VERSION
# is the fallback for anything with no family of its own.
TEMPLATES = {
    "bronze_ingestion": ("bronze", "bronze", "TRANSFORMATION_TEMPLATE_VERSION"),
    "silver_transform": ("silver", "silver", "TRANSFORMATION_TEMPLATE_VERSION"),
    "gold_aggregate": ("gold", "gold", "TRANSFORMATION_TEMPLATE_VERSION"),
    "quality_check": ("quality", "quality", "QUALITY_RULES_TEMPLATE_VERSION"),
    "airflow_dag": ("dag", "dag", "DAG_TEMPLATE_VERSION"),
    "glue_job_config": ("silver", "silver", "TEMPLATE_VERSION"),
    "iceberg_ddl": ("silver", "silver", "TEMPLATE_VERSION"),
}


def _versions() -> dict[str, str]:
    out = {}
    for line in (LIB / "shared" / "templates" / "VERSION").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def template_version(template_id: str) -> str:
    key = TEMPLATES[template_id][2]
    versions = _versions()
    if key not in versions:
        raise SystemExit(
            f"error: shared/templates/VERSION has no {key}; the vendored template "
            f"set does not match what {template_id} expects"
        )
    return versions[key]


def list_templates() -> int:
    versions = _versions()
    print("vendored template set:")
    for k, v in sorted(versions.items()):
        print(f"  {k:<34} {v}")
    print(f"\n  {'template':<20} {'spec file':<26} {'contract':<10} version key")
    for tid, (stem, contract, key) in sorted(TEMPLATES.items()):
        print(f"  {tid:<20} config/{stem + '.yaml':<19} {contract:<10} {key}")
    print(
        "\nEach spec is validated against lib/contracts/v1/<contract>_spec.schema.json\n"
        "before anything is written. An invalid spec renders nothing."
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="adop_render",
        description="Render a workload artifact from its validated spec.",
    )
    p.add_argument("--list", action="store_true", help="show templates and their specs")
    p.add_argument("--workload", help="path to the workload directory")
    p.add_argument("--template", choices=sorted(TEMPLATES), help="template to render")
    p.add_argument("--out", help="output path for the rendered artifact")
    p.add_argument(
        "--rendered-at",
        help="ISO timestamp recorded in the provenance header; pass a fixed value "
        "to reproduce a byte-identical artifact",
    )
    args = p.parse_args()

    if args.list:
        return list_templates()

    missing = [f"--{n}" for n in ("workload", "template", "out") if not getattr(args, n)]
    if missing:
        p.error("missing required argument(s): " + ", ".join(missing))

    stem, contract, _ = TEMPLATES[args.template]
    spec_path = Path(args.workload) / "config" / f"{stem}.yaml"
    if not spec_path.is_file():
        print(f"error: no spec at {spec_path}", file=sys.stderr)
        print(
            f"       {args.template} renders from config/{stem}.yaml — write the spec first.",
            file=sys.stderr,
        )
        return 2

    # render() requires run_started_at — it goes into the provenance header. Default
    # to now, but --rendered-at lets a caller pin it so re-rendering the same spec
    # produces byte-identical output, which is what the drift check depends on.
    rendered_at = args.rendered_at or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    try:
        spec, spec_hash = load_spec(spec_path, contract)
        render(
            spec=spec,
            spec_hash=spec_hash,
            template_id=args.template,
            template_version=template_version(args.template),
            output_path=Path(args.out),
            run_started_at=rendered_at,
        )
    except SpecValidationError as e:
        print(f"error: spec validation failed for {spec_path}\n  {e}", file=sys.stderr)
        return 2
    except MissingSlotError as e:
        print(
            f"error: {args.template} needs a slot the spec does not provide\n  {e}\n"
            "       Extend the spec — do not edit the template.",
            file=sys.stderr,
        )
        return 2
    except (TemplateNotFoundError, RenderError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(f"rendered {args.out}")
    print("  provenance header records spec_hash, template_id, template_hash,")
    print("  schema_version and rendered_at — this is what makes drift detectable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
