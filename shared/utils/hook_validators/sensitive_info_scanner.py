#!/usr/bin/env python3
"""Pre-commit hook: scan for hardcoded secrets, infrastructure details, and debug artifacts.

Complements git-secrets (which only catches AWS credential patterns) by detecting:
  - AWS account IDs, S3 bucket names with real data
  - Hardcoded passwords, tokens, API keys
  - Private key markers
  - Connection strings with embedded credentials
  - .env file content patterns
"""

import re
import sys
from pathlib import Path

# Sensitive patterns to detect
SENSITIVE_PATTERNS = [
    {
        "name": "AWS Account ID",
        "regex": r"(?<!\d)\d{12}(?!\d)",
        "severity": "HIGH",
        "context_required": True,  # only flag when near AWS-related keywords
        "context_keywords": ["account", "aws", "arn:", "iam", "role"],
    },
    {
        "name": "S3 Bucket (real)",
        "regex": r"s3://[a-z][a-z0-9.-]{2,62}",
        "severity": "HIGH",
        "allowed_values": [
            "s3://your-datalake-bucket",
            "s3://your-",
            "s3://example-",
            "s3://test-",
            "s3://placeholder",
            "s3://bucket-name",
        ],
    },
    {
        "name": "Hardcoded Password",
        "regex": r"""(?i)(?:password|passwd|pwd)\s*[=:]\s*['"][^'"]{4,}['"]""",
        "severity": "CRITICAL",
    },
    {
        "name": "Hardcoded Token",
        "regex": r"""(?i)(?:token|api_key|apikey|secret_key|secret)\s*[=:]\s*['"][^'"]{8,}['"]""",
        "severity": "CRITICAL",
        "exclude_values": [r"arn:aws:"],  # ARN references are not hardcoded tokens
    },
    {
        "name": "Private Key",
        "regex": r"-----BEGIN\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE\s+KEY-----",
        "severity": "CRITICAL",
    },
    {
        "name": "Connection String (with creds)",
        "regex": r"(?i)(?:jdbc:|mongodb://|postgresql://|mysql://|redis://)\S+:\S+@",
        "severity": "CRITICAL",
    },
    {
        "name": "Generic Secret Assignment",
        "regex": r"""(?i)(?:SECRET|PRIVATE|CREDENTIAL)\s*[=:]\s*['"][A-Za-z0-9+/=]{20,}['"]""",
        "severity": "HIGH",
    },
]

# Lines that are regex definitions or documentation (false positives)
FALSE_POSITIVE_INDICATORS = [
    r"regex",
    r"pattern",
    r"r['\"]\\b",
    r"re\.compile",
    r"re\.search",
    r"re\.match",
    r"#.*example",
    r"#.*pattern",
    r"#.*detect",
    r"#.*format",
    r"#.*test",
    r"description",
    r"placeholder",
    r"SENSITIVE_PATTERNS",
    r"SECRET_PATTERNS",
    r"FALSE_POSITIVE",
    r"ALLOWED",
]

# Allowed values from .gitallowed
ALLOWED_FILE = Path(".gitallowed")

GLOBAL_ALLOWED = [
    "123456789012",
    "000000000000",
    "AKIAIOSFODNN7EXAMPLE",
    "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
]


def load_allowed_patterns() -> list[str]:
    """Load allowed patterns from .gitallowed file."""
    patterns = list(GLOBAL_ALLOWED)
    if ALLOWED_FILE.exists():
        for line in ALLOWED_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def is_false_positive(line: str) -> bool:
    """Check if a line is a regex definition or documentation."""
    stripped = line.strip()
    if stripped.startswith("#"):
        return True
    for indicator in FALSE_POSITIVE_INDICATORS:
        if re.search(indicator, line, re.IGNORECASE):
            return True
    return False


def scan_file(filepath: str, allowed_patterns: list[str]) -> list[dict]:
    """Scan a single file for sensitive information."""
    findings = []
    try:
        content = Path(filepath).read_text(errors="replace")
    except (OSError, UnicodeDecodeError):
        return findings

    for line_num, line in enumerate(content.splitlines(), start=1):
        if is_false_positive(line):
            continue

        for pattern_def in SENSITIVE_PATTERNS:
            matches = re.findall(pattern_def["regex"], line)
            if not matches:
                continue

            # Check context requirement (e.g., account IDs only near AWS keywords)
            if pattern_def.get("context_required"):
                keywords = pattern_def.get("context_keywords", [])
                if not any(kw in line.lower() for kw in keywords):
                    continue

            # Check allowed values
            skip = False
            for allowed in allowed_patterns:
                if allowed in line:
                    skip = True
                    break

            # Check pattern-specific allowed values
            if not skip and "allowed_values" in pattern_def:
                for match in matches:
                    match_str = match if isinstance(match, str) else str(match)
                    if any(
                        match_str.startswith(av)
                        for av in pattern_def["allowed_values"]
                    ):
                        skip = True
                        break

            # Check pattern-specific exclude values (line-level)
            if not skip and "exclude_values" in pattern_def:
                for excl in pattern_def["exclude_values"]:
                    if re.search(excl, line):
                        skip = True
                        break

            if skip:
                continue

            findings.append(
                {
                    "file": filepath,
                    "line": line_num,
                    "name": pattern_def["name"],
                    "severity": pattern_def["severity"],
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
            if f["severity"] == "CRITICAL":
                has_critical = True

    if not all_findings:
        return 0

    print("\n  SENSITIVE INFO SCANNER — Potential secrets/infrastructure details found\n")
    for f in all_findings:
        severity_marker = "BLOCK" if f["severity"] == "CRITICAL" else "WARN"
        print(
            f"  [{severity_marker}] {f['file']}:{f['line']} — "
            f"{f['name']} ({f['severity']})"
        )
        print(f"         {f['content']}")
        print()

    print(f"  Found {len(all_findings)} potential issue(s).")
    if has_critical:
        print(
            "  CRITICAL findings must be resolved before committing.\n"
            "  Use Secrets Manager, Airflow Connections, or env vars instead.\n"
            "  If false positive, add pattern to .gitallowed\n"
            "  or skip: SKIP=sensitive-info-scanner git commit -m 'reason'\n"
        )
        return 1

    print("  HIGH findings are warnings — review before committing.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
