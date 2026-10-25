#!/usr/bin/env python3
"""Pre-commit hook: scan YAML metadata for prompt injection patterns.

Checks workloads/*/config/semantic.yaml and similar files for:
  - Control characters in column names and descriptions
  - SQL injection fragments in metadata
  - Prompt override attempts in descriptions and business terms
"""

import sys
from pathlib import Path

import yaml

# Import injection detection from the sanitizer module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from shared.utils.prompt_sanitizer import has_injection_patterns, CONTROL_CHARS


def scan_yaml_value(value: object, path: str, filepath: str) -> list[dict]:
    """Recursively scan YAML values for injection patterns."""
    findings = []

    if isinstance(value, str):
        patterns = has_injection_patterns(value)
        if patterns:
            findings.append(
                {
                    "file": filepath,
                    "path": path,
                    "value": value[:100],
                    "patterns": patterns,
                }
            )
    elif isinstance(value, dict):
        for k, v in value.items():
            # Scan both keys and values
            key_patterns = has_injection_patterns(str(k))
            if key_patterns:
                findings.append(
                    {
                        "file": filepath,
                        "path": f"{path}.{k} (key)",
                        "value": str(k)[:100],
                        "patterns": key_patterns,
                    }
                )
            findings.extend(scan_yaml_value(v, f"{path}.{k}", filepath))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            findings.extend(scan_yaml_value(item, f"{path}[{i}]", filepath))

    return findings


def scan_file(filepath: str) -> list[dict]:
    """Scan a single YAML file for injection patterns."""
    try:
        content = Path(filepath).read_text()
    except (OSError, UnicodeDecodeError):
        return []

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError:
        return []  # YAML syntax errors caught by check-yaml hook

    if data is None:
        return []

    return scan_yaml_value(data, "$", filepath)


def main() -> int:
    if len(sys.argv) < 2:
        return 0

    all_findings: list[dict] = []
    for filepath in sys.argv[1:]:
        findings = scan_file(filepath)
        all_findings.extend(findings)

    if not all_findings:
        return 0

    print("\n  PROMPT INJECTION SCANNER — Suspicious patterns in YAML metadata\n")
    for f in all_findings:
        print(f"  [BLOCK] {f['file']} at {f['path']}")
        print(f"         Value: {f['value']}")
        for p in f["patterns"]:
            print(f"         Pattern: {p}")
        print()

    print(
        f"  Found {len(all_findings)} suspicious pattern(s).\n"
        "  These patterns could enable prompt injection attacks.\n"
        "  Remove control characters, SQL fragments, or override attempts.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
