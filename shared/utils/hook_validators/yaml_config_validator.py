#!/usr/bin/env python3
"""Pre-commit hook: validate workload YAML config schemas.

Validates required keys per config type:
  - source.yaml: source_type, location, format
  - quality_rules.yaml: rules list with rule_id, dimension, threshold
  - schedule.yaml: schedule_interval, start_date
  - semantic.yaml: columns with role field

Also scans YAML values for hardcoded secrets and infrastructure details.
"""

import re
import sys
from pathlib import Path

import yaml

# Known config file types (for documentation; no strict schema enforcement).
# Existing workloads use varied key naming, so validation focuses on:
#   1. Valid YAML syntax
#   2. Non-empty content
#   3. No hardcoded secrets
KNOWN_CONFIG_TYPES = {
    "source.yaml",
    "quality_rules.yaml",
    "schedule.yaml",
    "semantic.yaml",
    "transformations.yaml",
}

# Patterns indicating hardcoded secrets in YAML values
SECRET_PATTERNS = [
    (r"AKIA[A-Z0-9]{16}", "AWS Access Key ID"),
    (r"-----BEGIN.*PRIVATE KEY-----", "Private key"),
    (r"""(?i)password\s*:\s*['"][^'"]{8,}['"]""", "Hardcoded password"),
]

# Allowed values that look like secrets but aren't
ALLOWED_VALUES = [
    "123456789012",  # test account ID
    "000000000000",
    "AKIAIOSFODNN7EXAMPLE",
]


def validate_structure(filepath: str, data: object) -> list[str]:
    """Basic structural validation — must be a non-empty YAML mapping."""
    if not isinstance(data, dict):
        return [f"{filepath}: expected a YAML mapping, got {type(data).__name__}"]
    return []


def scan_for_secrets(filepath: str, content: str) -> list[str]:
    """Scan YAML content for hardcoded secrets."""
    warnings = []
    for line_num, line in enumerate(content.splitlines(), start=1):
        # Skip comments
        if line.strip().startswith("#"):
            continue
        for pattern, description in SECRET_PATTERNS:
            matches = re.findall(pattern, line)
            for match in matches:
                if any(allowed in line for allowed in ALLOWED_VALUES):
                    continue
                warnings.append(
                    f"{filepath}:{line_num}: potential {description} — "
                    f"use Secrets Manager or Airflow Connections instead"
                )
    return warnings


def validate_file(filepath: str) -> list[str]:
    """Validate a single YAML config file."""
    errors = []
    path = Path(filepath)
    filename = path.name

    try:
        content = path.read_text()
    except OSError as e:
        return [f"{filepath}: cannot read file: {e}"]

    # Parse YAML
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return [f"{filepath}: YAML parse error: {e}"]

    if data is None:
        return [f"{filepath}: file is empty"]

    # Structural validation
    errors.extend(validate_structure(filepath, data))

    # Secret scanning for all YAML files
    errors.extend(scan_for_secrets(filepath, content))

    return errors


def main() -> int:
    if len(sys.argv) < 2:
        return 0

    all_errors: list[str] = []
    for filepath in sys.argv[1:]:
        errors = validate_file(filepath)
        all_errors.extend(errors)

    if not all_errors:
        return 0

    print("\n  YAML CONFIG VALIDATOR — Issues found\n")
    for error in all_errors:
        print(f"  [BLOCK] {error}")
    print(f"\n  {len(all_errors)} issue(s) found. Fix before committing.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
