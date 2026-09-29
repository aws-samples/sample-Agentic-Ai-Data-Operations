"""Drift validator: detects hand-edits to rendered artifacts by re-rendering and comparing."""

import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .renderer import render_dry_run
from .spec_loader import compute_spec_hash, load_spec

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

HEADER_PATTERN = re.compile(
    r"^(?:#|--) spec_hash: ([a-f0-9]{64})\n"
    r"(?:#|--) template_id: ([\w]+)\n"
    r"(?:#|--) template_hash: ([a-f0-9]{64})\n"
    r"(?:#|--) schema_version: (v\d+)\n"
    r"(?:#|--) rendered_at: (.+)\n",
    re.MULTILINE,
)


@dataclass
class DriftReport:
    artifact_path: str
    ok: bool
    expected_hash: Optional[str] = None
    actual_hash: Optional[str] = None
    diff: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class WorkloadDriftReport:
    workload_path: str
    reports: list[DriftReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.reports)


def parse_artifact_header(content: str) -> Optional[dict]:
    """Extract the 5-line deterministic header from a rendered artifact."""
    match = HEADER_PATTERN.match(content)
    if not match:
        return None
    return {
        "spec_hash": match.group(1),
        "template_id": match.group(2),
        "template_hash": match.group(3),
        "schema_version": match.group(4),
        "rendered_at": match.group(5),
    }


def verify_artifact(artifact_path: Path) -> DriftReport:
    """
    Round-trip check on a single artifact:
    1. Parse header to get spec_hash, template_id, rendered_at
    2. Locate the workload config dir
    3. Re-render with same parameters
    4. Compare SHA-256 of actual vs expected
    """
    artifact_path = Path(artifact_path)
    if not artifact_path.exists():
        return DriftReport(
            artifact_path=str(artifact_path),
            ok=False,
            reason="Artifact file not found",
        )

    content = artifact_path.read_text(encoding="utf-8")
    header = parse_artifact_header(content)

    if header is None:
        return DriftReport(
            artifact_path=str(artifact_path),
            ok=False,
            reason="Missing or malformed deterministic header",
        )

    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    # Find the workload config directory
    workload_dir = _find_workload_dir(artifact_path)
    if workload_dir is None:
        return DriftReport(
            artifact_path=str(artifact_path),
            ok=False,
            reason="Cannot locate workload directory from artifact path",
        )

    # Determine spec type from template_id
    spec_type = _template_id_to_spec_type(header["template_id"])
    if spec_type is None:
        return DriftReport(
            artifact_path=str(artifact_path),
            ok=False,
            reason=f"Unknown template_id: {header['template_id']}",
        )

    # Load the spec
    spec_path = _find_spec_file(workload_dir, spec_type)
    if spec_path is None or not spec_path.exists():
        return DriftReport(
            artifact_path=str(artifact_path),
            ok=False,
            reason=f"Spec file not found for type '{spec_type}' in {workload_dir}",
        )

    try:
        spec, spec_hash = load_spec(spec_path, spec_type, header["schema_version"])
    except Exception as e:
        return DriftReport(
            artifact_path=str(artifact_path),
            ok=False,
            reason=f"Failed to load spec: {e}",
        )

    # Re-render
    try:
        rendered_bytes, expected_hash = render_dry_run(
            spec=spec,
            spec_hash=spec_hash,
            template_id=header["template_id"],
            template_version="1.0.0",
            run_started_at=header["rendered_at"],
            schema_version=header["schema_version"],
        )
    except Exception as e:
        return DriftReport(
            artifact_path=str(artifact_path),
            ok=False,
            reason=f"Re-render failed: {e}",
        )

    if actual_hash == expected_hash:
        return DriftReport(
            artifact_path=str(artifact_path),
            ok=True,
            expected_hash=expected_hash,
            actual_hash=actual_hash,
        )

    return DriftReport(
        artifact_path=str(artifact_path),
        ok=False,
        expected_hash=expected_hash,
        actual_hash=actual_hash,
        diff=f"Content differs (expected {expected_hash[:16]}..., got {actual_hash[:16]}...)",
    )


def verify_workload(workload_path: Path) -> WorkloadDriftReport:
    """Verify every generated artifact in a workload directory."""
    workload_path = Path(workload_path)
    report = WorkloadDriftReport(workload_path=str(workload_path))

    artifact_dirs = ["scripts", "dags", "sql"]
    for subdir in artifact_dirs:
        dir_path = workload_path / subdir
        if not dir_path.exists():
            continue
        for artifact in sorted(dir_path.rglob("*")):
            if artifact.is_file() and artifact.suffix in (".py", ".sql", ".yaml", ".yml"):
                content = artifact.read_text(encoding="utf-8")
                if parse_artifact_header(content) is not None:
                    report.reports.append(verify_artifact(artifact))

    return report


def _find_workload_dir(artifact_path: Path) -> Optional[Path]:
    """Walk up from artifact path to find the workload root (has config/ dir)."""
    current = artifact_path.parent
    for _ in range(10):
        if (current / "config").is_dir():
            return current
        if current.parent == current:
            break
        current = current.parent
    return None


def _template_id_to_spec_type(template_id: str) -> Optional[str]:
    mapping = {
        "bronze_ingestion": "bronze",
        "silver_transform": "silver",
        "gold_aggregate": "gold",
        "quality_check": "quality",
        "airflow_dag": "dag",
        "glue_job_config": "dag",
        "iceberg_ddl": "silver",
    }
    return mapping.get(template_id)


def _find_spec_file(workload_dir: Path, spec_type: str) -> Optional[Path]:
    """Find the spec YAML file for a given type in the config directory."""
    config_dir = workload_dir / "config"
    candidates = [
        config_dir / f"{spec_type}.yaml",
        config_dir / f"{spec_type}_spec.yaml",
        config_dir / f"{spec_type}_rules.yaml",
    ]
    # Special mappings
    if spec_type == "quality":
        candidates.insert(0, config_dir / "quality_rules.yaml")
    if spec_type == "dag":
        candidates.insert(0, config_dir / "schedule.yaml")
    if spec_type == "source":
        candidates.insert(0, config_dir / "source.yaml")

    for path in candidates:
        if path.exists():
            return path
    return None


def main():
    """CLI entrypoint for pre-commit and CI."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify artifact drift")
    parser.add_argument("paths", nargs="*", help="Artifact paths or workload directories")
    parser.add_argument("--pre-commit", action="store_true", help="Pre-commit mode (check specific files)")
    args = parser.parse_args()

    if not args.paths:
        print("No paths provided")
        sys.exit(0)

    has_drift = False
    for path_str in args.paths:
        path = Path(path_str)
        if path.is_dir():
            report = verify_workload(path)
            for r in report.reports:
                status = "OK" if r.ok else "DRIFT"
                print(f"  {status}: {r.artifact_path}")
                if not r.ok:
                    has_drift = True
                    if r.reason:
                        print(f"        reason: {r.reason}")
        elif path.is_file():
            r = verify_artifact(path)
            status = "OK" if r.ok else "DRIFT"
            print(f"  {status}: {r.artifact_path}")
            if not r.ok:
                has_drift = True
                if r.reason:
                    print(f"        reason: {r.reason}")

    sys.exit(1 if has_drift else 0)


if __name__ == "__main__":
    main()
