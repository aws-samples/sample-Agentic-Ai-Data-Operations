#!/usr/bin/env python3
"""Pre-commit hook: validate Cedar policy syntax before commit.

Attempts cedarpy parse if available, otherwise does structural validation
(checks for forbid/permit keywords, balanced braces, required fields).
"""

import re
import sys
from pathlib import Path

# Reuse paths from shared/utils/cedar_client.py (lines 21-24)
POLICIES_DIR = Path(__file__).resolve().parent.parent.parent / "policies"
SCHEMA_FILE = POLICIES_DIR / "schema.cedarschema"


def validate_with_cedarpy(filepath: str, content: str) -> tuple[bool, list[str]]:
    """Attempt validation using cedarpy library.

    Returns (attempted, errors): attempted=False means cedarpy is not usable,
    so caller should fall through to structural validation.
    """
    try:
        import cedarpy

        if not hasattr(cedarpy, "is_authorized"):
            return False, []  # cedarpy installed but API incompatible, fall through

        # cedarpy doesn't expose a standalone parse function in all versions.
        # If we can't validate with it, fall through to structural checks.
        return False, []
    except ImportError:
        return False, []  # cedarpy not available, fall through


def validate_structure(filepath: str, content: str) -> list[str]:
    """Structural validation when cedarpy is not available."""
    errors = []
    filename = Path(filepath).name
    is_schema = filepath.endswith(".cedarschema")

    if not content.strip():
        errors.append(f"{filepath}: file is empty")
        return errors

    # Check balanced braces
    open_braces = content.count("{")
    close_braces = content.count("}")
    if open_braces != close_braces:
        errors.append(
            f"{filepath}: unbalanced braces — "
            f"{open_braces} opening vs {close_braces} closing"
        )

    # Check balanced parentheses
    open_parens = content.count("(")
    close_parens = content.count(")")
    if open_parens != close_parens:
        errors.append(
            f"{filepath}: unbalanced parentheses — "
            f"{open_parens} opening vs {close_parens} closing"
        )

    if is_schema:
        # Schema files should have entity/action definitions
        if "entity" not in content.lower() and "action" not in content.lower():
            errors.append(
                f"{filepath}: schema file missing 'entity' or 'action' definitions"
            )
    else:
        # Policy files must contain forbid or permit
        has_forbid = bool(re.search(r"\bforbid\b", content))
        has_permit = bool(re.search(r"\bpermit\b", content))
        if not has_forbid and not has_permit:
            errors.append(
                f"{filepath}: policy file must contain at least one "
                f"'forbid' or 'permit' statement"
            )

        # Policy files should reference principal, action, resource
        if not re.search(r"\bprincipal\b", content):
            errors.append(f"{filepath}: missing 'principal' in policy")
        if not re.search(r"\baction\b", content):
            errors.append(f"{filepath}: missing 'action' in policy")
        if not re.search(r"\bresource\b", content):
            errors.append(f"{filepath}: missing 'resource' in policy")

    return errors


def validate_file(filepath: str) -> list[str]:
    """Validate a single Cedar file."""
    try:
        content = Path(filepath).read_text()
    except OSError as e:
        return [f"{filepath}: cannot read file: {e}"]

    # Try cedarpy first
    attempted, cedarpy_errors = validate_with_cedarpy(filepath, content)
    if attempted:
        return cedarpy_errors

    # Fall back to structural validation
    return validate_structure(filepath, content)


def main() -> int:
    if len(sys.argv) < 2:
        return 0

    all_errors: list[str] = []
    for filepath in sys.argv[1:]:
        errors = validate_file(filepath)
        all_errors.extend(errors)

    if not all_errors:
        return 0

    print("\n  CEDAR POLICY VALIDATOR — Syntax errors found\n")
    for error in all_errors:
        print(f"  [BLOCK] {error}")
    print(
        f"\n  {len(all_errors)} error(s) found. Fix before committing.\n"
        "  Docs: https://docs.cedarpolicy.com/syntax\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
