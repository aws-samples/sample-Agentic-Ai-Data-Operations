"""Load and validate workload specs against versioned JSON Schema contracts."""

import hashlib
import json
from pathlib import Path

import jsonschema
import yaml

from .exceptions import SchemaVersionError, SpecHashMismatchError, SpecValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONTRACTS_DIR = PROJECT_ROOT / "contracts"

SPEC_TYPE_TO_SCHEMA = {
    "source": "source_profile.schema.json",
    "bronze": "bronze_spec.schema.json",
    "silver": "silver_spec.schema.json",
    "gold": "gold_spec.schema.json",
    "quality": "quality_spec.schema.json",
    "dag": "dag_spec.schema.json",
    "manifest": "workload_manifest.schema.json",
    "run_context": "run_context.schema.json",
}


def _canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def compute_spec_hash(spec: dict) -> str:
    """SHA-256 of the canonical JSON representation of a spec dict."""
    return hashlib.sha256(_canonical_json(spec).encode("utf-8")).hexdigest()


def _load_schema(spec_type: str, schema_version: str) -> dict:
    version_dir = CONTRACTS_DIR / schema_version
    if not version_dir.is_dir():
        raise SchemaVersionError(schema_version)

    schema_filename = SPEC_TYPE_TO_SCHEMA.get(spec_type)
    if schema_filename is None:
        raise SchemaVersionError(
            f"{schema_version}/{spec_type} (unknown spec type)"
        )

    schema_path = version_dir / schema_filename
    if not schema_path.exists():
        raise SchemaVersionError(
            f"{schema_version}/{schema_filename} (file missing)"
        )

    with open(schema_path) as f:
        return json.load(f)


def _normalise_s3_prefix(value: str) -> str:
    """Trailing slashes are cosmetic in S3; compare prefixes without them."""
    return value.rstrip("/") if isinstance(value, str) else value


def _semantic_errors(spec: dict, spec_type: str) -> list[str]:
    """Cross-field rules that JSON Schema cannot express.

    JSON Schema validates each field in isolation, so a spec can be structurally perfect
    and still describe something the architecture forbids. `bronze-immutable` is a
    BLOCK-severity invariant, and the way to violate it is to write the Bronze output on
    top of the raw source -- which is two individually valid paths that happen to match.
    Observed in a real run: the generated bronze.yaml set `landing_zone` to the same prefix
    as `source_path`, so the job would have appended Parquet over the source CSV.
    """
    errors: list[str] = []
    if spec_type == "bronze":
        source = _normalise_s3_prefix(spec.get("source_path"))
        landing = _normalise_s3_prefix(spec.get("landing_zone"))
        if source and landing:
            if source == landing:
                errors.append(
                    "landing_zone must not equal source_path "
                    f"(both are {source!r}); writing Bronze output over the raw source "
                    "violates the bronze-immutable invariant. Give landing_zone its own "
                    "prefix, e.g. the source under .../raw/ and the landing under "
                    ".../bronze/<dataset>/."
                )
            elif landing.startswith(source + "/"):
                errors.append(
                    f"landing_zone ({landing!r}) is nested inside source_path "
                    f"({source!r}); Bronze output would be written into the raw source "
                    "prefix, which violates the bronze-immutable invariant."
                )
            elif source.startswith(landing + "/"):
                errors.append(
                    f"source_path ({source!r}) is nested inside landing_zone "
                    f"({landing!r}); the job would append output over its own input on "
                    "re-run, which violates the bronze-immutable invariant."
                )
    return errors


def validate_spec(spec: dict, spec_type: str, schema_version: str = "v1") -> list[str]:
    """Validate a spec dict against its JSON Schema and the cross-field rules.

    Schema errors first, then semantic ones, so a spec that is both malformed and
    architecturally wrong reports everything in one pass.
    """
    schema = _load_schema(spec_type, schema_version)
    validator = jsonschema.Draft202012Validator(schema)
    errors = [err.message for err in validator.iter_errors(spec)]
    return errors + _semantic_errors(spec, spec_type)


def load_spec(path: Path, spec_type: str, schema_version: str = "v1") -> tuple[dict, str]:
    """
    Load a YAML/JSON spec file, validate against its contract, return (spec, spec_hash).

    Args:
        path: Path to the spec YAML or JSON file.
        spec_type: One of 'source', 'bronze', 'silver', 'gold', 'quality', 'dag',
            'manifest', 'run_context'.
        schema_version: Contract version directory (default 'v1').

    Returns:
        Tuple of (spec_dict, spec_hash) where spec_hash is SHA-256 hex of canonical JSON.

    Raises:
        SpecValidationError: If the spec fails schema validation.
        SchemaVersionError: If the schema version directory or file is missing.
        FileNotFoundError: If the spec file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Spec file not found: {path}")

    with open(path) as f:
        if path.suffix == ".json":
            spec = json.load(f)
        else:
            spec = yaml.safe_load(f)

    errors = validate_spec(spec, spec_type, schema_version)
    if errors:
        schema_file = SPEC_TYPE_TO_SCHEMA.get(spec_type, spec_type)
        raise SpecValidationError(
            f"contracts/{schema_version}/{schema_file}", errors
        )

    spec_hash = compute_spec_hash(spec)
    return spec, spec_hash


def verify_manifest_hashes(
    manifest: dict, specs: dict[str, dict]
) -> list[SpecHashMismatchError]:
    """
    Verify that spec_hashes in a manifest match computed hashes of the actual specs.

    Args:
        manifest: Loaded manifest dict with 'spec_hashes' field.
        specs: Dict mapping spec_type ('bronze', 'silver', etc.) to loaded spec dict.

    Returns:
        List of SpecHashMismatchError for any mismatches (empty if all match).
    """
    mismatches = []
    manifest_hashes = manifest.get("spec_hashes", {})

    for spec_type, spec_dict in specs.items():
        expected = manifest_hashes.get(spec_type)
        if expected is None:
            continue
        actual = compute_spec_hash(spec_dict)
        if actual != expected:
            mismatches.append(
                SpecHashMismatchError(spec_type, expected, actual)
            )

    return mismatches
