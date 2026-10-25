#!/usr/bin/env python3
"""Kiro entry point for deterministic, schema-validated ADOP rendering."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


def _bundle_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (
            (candidate / "shared" / "codegen" / "renderer.py").is_file()
            or (candidate / "plugins" / "claude-code" / "lib" / "shared" / "codegen" / "renderer.py").is_file()
        ):
            return candidate
    raise SystemExit(
        "error: ADOP shared/codegen is not available; use the complete integration bundle"
    )


ROOT = _bundle_root()
ENGINE_ROOT = ROOT
if not (ENGINE_ROOT / "shared" / "templates").is_dir():
    ENGINE_ROOT = ROOT / "plugins" / "claude-code" / "lib"
if not (ENGINE_ROOT / "shared" / "codegen" / "renderer.py").is_file():
    raise SystemExit("error: no shared codegen engine or vendored plugin engine found")
sys.path.insert(0, str(ENGINE_ROOT))

from shared.codegen.exceptions import (  # noqa: E402
    MissingSlotError,
    RenderError,
    SpecValidationError,
    TemplateNotFoundError,
)
from shared.codegen.renderer import render  # noqa: E402
from shared.codegen.spec_loader import load_spec  # noqa: E402


TEMPLATES = {
    "bronze_ingestion": ("bronze", "bronze", "TRANSFORMATION_TEMPLATE_VERSION"),
    "silver_transform": ("silver", "silver", "TRANSFORMATION_TEMPLATE_VERSION"),
    "gold_aggregate": ("gold", "gold", "TRANSFORMATION_TEMPLATE_VERSION"),
    "quality_check": ("quality", "quality", "QUALITY_RULES_TEMPLATE_VERSION"),
    "airflow_dag": ("dag", "dag", "DAG_TEMPLATE_VERSION"),
    "glue_job_config": ("dag", "dag", "TEMPLATE_VERSION"),
    "iceberg_ddl": ("silver", "silver", "TEMPLATE_VERSION"),
}


def _versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    version_file = ENGINE_ROOT / "shared" / "templates" / "VERSION"
    for line in version_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            versions[key.strip()] = value.strip()
    return versions


def _list() -> int:
    print("ADOP Kiro renderer:")
    versions = _versions()
    for template_id, (stem, contract, version_key) in sorted(TEMPLATES.items()):
        print(
            f"  {template_id:<20} config/{stem}.yaml  "
            f"{contract:<8} {version_key}={versions.get(version_key, '<missing>')}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="adop_render",
        description="Render a workload artifact from a validated ADOP spec.",
    )
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--workload")
    parser.add_argument("--template", choices=sorted(TEMPLATES))
    parser.add_argument("--out")
    parser.add_argument("--rendered-at")
    args = parser.parse_args()
    if args.list:
        return _list()
    missing = [
        f"--{name}"
        for name in ("workload", "template", "out")
        if not getattr(args, name)
    ]
    if missing:
        parser.error("missing required argument(s): " + ", ".join(missing))

    stem, contract, version_key = TEMPLATES[args.template]
    workload = Path(args.workload)
    spec_path = workload / "config" / f"{stem}.yaml"
    if not spec_path.is_file():
        print(f"error: no spec at {spec_path}", file=sys.stderr)
        return 2
    versions = _versions()
    if version_key not in versions:
        print(f"error: VERSION has no {version_key}", file=sys.stderr)
        return 2
    rendered_at = args.rendered_at or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    try:
        spec, spec_hash = load_spec(spec_path, contract)
        render(
            spec=spec,
            spec_hash=spec_hash,
            template_id=args.template,
            template_version=versions[version_key],
            output_path=Path(args.out),
            run_started_at=rendered_at,
        )
    except SpecValidationError as exc:
        print(f"error: spec validation failed: {exc}", file=sys.stderr)
        return 2
    except MissingSlotError as exc:
        print(f"error: missing renderer slot: {exc}", file=sys.stderr)
        return 2
    except (TemplateNotFoundError, RenderError) as exc:
        print(f"error: render failed: {exc}", file=sys.stderr)
        return 2
    print(f"rendered {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
