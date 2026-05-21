#!/usr/bin/env python3
"""Validate that all JSON Schema files in contracts/ are valid Draft 2020-12 schemas."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = PROJECT_ROOT / "contracts"


def validate_schema_file(path: Path) -> list[str]:
    errors = []
    try:
        with open(path) as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"{path}: Invalid JSON: {e}")
        return errors

    if "$schema" not in schema:
        errors.append(f"{path}: Missing '$schema' field")
    elif "2020-12" not in schema["$schema"]:
        errors.append(f"{path}: '$schema' must reference Draft 2020-12")

    if "$id" not in schema:
        errors.append(f"{path}: Missing '$id' field")

    if "title" not in schema:
        errors.append(f"{path}: Missing 'title' field")

    if schema.get("type") == "object":
        if "required" not in schema:
            errors.append(f"{path}: Top-level object missing 'required' field")
        if schema.get("additionalProperties") is not False:
            errors.append(f"{path}: Top-level object must set 'additionalProperties: false'")

    try:
        import jsonschema
        jsonschema.validators.validator_for(schema).check_schema(schema)
    except ImportError:
        pass
    except jsonschema.SchemaError as e:
        errors.append(f"{path}: Invalid JSON Schema: {e.message}")

    return errors


def main() -> int:
    schema_files = sorted(CONTRACTS_DIR.rglob("*.schema.json"))
    if not schema_files:
        print("ERROR: No schema files found in contracts/")
        return 1

    all_errors = []
    for path in schema_files:
        errors = validate_schema_file(path)
        all_errors.extend(errors)
        status = "FAIL" if errors else "OK"
        print(f"  {status}: {path.relative_to(PROJECT_ROOT)}")

    if all_errors:
        print(f"\n{len(all_errors)} error(s) found:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print(f"\nAll {len(schema_files)} schemas valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
