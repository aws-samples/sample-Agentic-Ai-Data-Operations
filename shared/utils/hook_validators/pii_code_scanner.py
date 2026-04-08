#!/usr/bin/env python3
"""Pre-commit hook: scan source code for PII patterns.

Reuses PII regex patterns from shared/utils/pii_detection_and_tagging.py.
Blocks on CRITICAL severity (SSN, CREDIT_CARD), warns on HIGH (EMAIL, DOB).
"""

import re
import sys
from pathlib import Path

# PII patterns reused from shared/utils/pii_detection_and_tagging.py (lines 50-86)
PII_PATTERNS = {
    "EMAIL": {
        "regex": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "sensitivity": "HIGH",
    },
    "PHONE": {
        "regex": r"\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b",
        "sensitivity": "MEDIUM",
    },
    "SSN": {
        "regex": r"\b\d{3}-\d{2}-\d{4}\b",
        "sensitivity": "CRITICAL",
    },
    "CREDIT_CARD": {
        "regex": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
        "sensitivity": "CRITICAL",
    },
    "DATE_OF_BIRTH": {
        "regex": r"\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12][0-9]|3[01])[/-](?:19|20)\d{2}\b",
        "sensitivity": "HIGH",
    },
}

# Patterns that indicate the match is in a regex definition or comment, not actual PII
FALSE_POSITIVE_INDICATORS = [
    r"regex",
    r"pattern",
    r"r['\"]",
    r"r\"\\b",
    r"re\.compile",
    r"PII_PATTERNS",
    r"#.*example",
    r"#.*pattern",
    r"#.*detect",
    r"#.*format",
    r"description",
    r"placeholder",
    r"123456789012",  # allowed test account ID
    r"AKIAIOSFODNN7EXAMPLE",  # allowed test key
]

# Allowed patterns from .gitallowed
ALLOWED_FILE = Path(".gitallowed")


def load_allowed_patterns() -> list[str]:
    """Load allowed patterns from .gitallowed file."""
    if not ALLOWED_FILE.exists():
        return []
    patterns = []
    for line in ALLOWED_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def is_false_positive(line: str) -> bool:
    """Check if a line contains PII patterns as regex definitions, not actual PII."""
    line_lower = line.lower().strip()
    # Skip comment lines that describe patterns
    if line_lower.lstrip().startswith("#"):
        return True
    # Skip lines defining regex patterns
    for indicator in FALSE_POSITIVE_INDICATORS:
        if re.search(indicator, line, re.IGNORECASE):
            return True
    return False


def scan_file(filepath: str, allowed_patterns: list[str]) -> list[dict]:
    """Scan a single file for PII patterns. Returns list of findings."""
    findings = []
    try:
        content = Path(filepath).read_text(errors="replace")
    except (OSError, UnicodeDecodeError):
        return findings

    for line_num, line in enumerate(content.splitlines(), start=1):
        if is_false_positive(line):
            continue

        for pii_type, info in PII_PATTERNS.items():
            matches = re.findall(info["regex"], line)
            if not matches:
                continue

            # Check against allowed patterns
            skip = False
            for allowed in allowed_patterns:
                if allowed in line:
                    skip = True
                    break
            if skip:
                continue

            findings.append(
                {
                    "file": filepath,
                    "line": line_num,
                    "type": pii_type,
                    "sensitivity": info["sensitivity"],
                    "content": line.strip()[:120],
                }
            )

    return findings


def main() -> int:
    if len(sys.argv) < 2:
        return 0

    allowed_patterns = load_allowed_patterns()
    all_findings: list[dict] = []
    has_critical = False

    for filepath in sys.argv[1:]:
        findings = scan_file(filepath, allowed_patterns)
        all_findings.extend(findings)
        for f in findings:
            if f["sensitivity"] == "CRITICAL":
                has_critical = True

    if not all_findings:
        return 0

    # Report findings
    print("\n  PII CODE SCANNER — Potential PII detected in source code\n")
    for f in all_findings:
        severity_marker = "BLOCK" if f["sensitivity"] == "CRITICAL" else "WARN"
        print(
            f"  [{severity_marker}] {f['file']}:{f['line']} — "
            f"{f['type']} ({f['sensitivity']})"
        )
        print(f"         {f['content']}")
        print()

    print(f"  Found {len(all_findings)} potential PII pattern(s).")
    if has_critical:
        print(
            "  CRITICAL findings must be resolved before committing.\n"
            "  If this is a false positive, add the pattern to .gitallowed\n"
            "  or skip: SKIP=pii-code-scanner git commit -m 'reason'\n"
        )
        return 1

    print(
        "  HIGH/MEDIUM findings are warnings — review before committing.\n"
        "  Proceeding (no CRITICAL findings).\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
