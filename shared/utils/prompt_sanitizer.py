"""Prompt injection sanitization for the Agentic Data Onboarding Platform.

Sanitizes external data (column names, table names, descriptions, user queries)
before they enter LLM prompts via f-strings. Prevents prompt injection attacks
where malicious metadata could manipulate agent behavior.

Usage:
    from shared.utils.prompt_sanitizer import (
        sanitize_identifier,
        sanitize_description,
        sanitize_user_query,
    )

    safe_col = sanitize_identifier(column_name)
    safe_desc = sanitize_description(column_description)
    safe_query = sanitize_user_query(user_nl_query)
"""

import re
import unicodedata

# Maximum lengths for sanitized outputs
MAX_IDENTIFIER_LENGTH = 128
MAX_DESCRIPTION_LENGTH = 500
MAX_QUERY_LENGTH = 1000

# Characters allowed in identifiers (column/table names)
IDENTIFIER_ALLOWED = re.compile(r"[^a-zA-Z0-9_\-. ]")

# Control character ranges
CONTROL_CHARS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]"
)

# Prompt injection patterns — attempts to override system instructions
INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(all\s+)?previous\s+instructions?\b"),
    re.compile(r"(?i)\bignore\s+(all\s+)?above\b"),
    re.compile(r"(?i)\bsystem\s*:\s*"),
    re.compile(r"(?i)\bSYSTEM\s*:\s*"),
    re.compile(r"(?i)\buser\s*:\s*"),
    re.compile(r"(?i)\bassistant\s*:\s*"),
    re.compile(r"(?i)\b(forget|disregard|override)\s+(everything|all|previous)\b"),
    re.compile(r"(?i)\bnew\s+instructions?\s*:\s*"),
    re.compile(r"(?i)\byou\s+are\s+now\b"),
    re.compile(r"(?i)\bact\s+as\s+(a|an)\b"),
    re.compile(r"(?i)\bdo\s+not\s+follow\b"),
    re.compile(r"(?i)\breturn\s+all\s+(secrets?|credentials?|passwords?)\b"),
]

# SQL injection fragments
SQL_INJECTION_PATTERNS = [
    re.compile(r";\s*(DROP|DELETE|TRUNCATE|ALTER|UPDATE|INSERT)\b", re.IGNORECASE),
    re.compile(r"--\s*$", re.MULTILINE),
    re.compile(r"/\*.*?\*/", re.DOTALL),
    re.compile(r"(?i)\bUNION\s+(ALL\s+)?SELECT\b"),
    re.compile(r"(?i)'\s*OR\s+'1'\s*=\s*'1"),
    re.compile(r"(?i)'\s*;\s*--"),
]


def sanitize_identifier(name: str) -> str:
    """Sanitize column/table names for safe prompt inclusion.

    - Strips control characters
    - Removes backtick sequences that could break SQL formatting
    - Removes newlines and carriage returns
    - Allows only: alphanumeric, underscore, hyphen, period, space
    - Truncates to 128 chars
    """
    if not name:
        return ""

    # Normalize Unicode (NFC)
    result = unicodedata.normalize("NFC", name)

    # Strip control characters
    result = CONTROL_CHARS.sub("", result)

    # Remove newlines
    result = result.replace("\n", " ").replace("\r", "")

    # Remove backticks (prevent SQL/markdown escaping tricks)
    result = result.replace("`", "")

    # Remove characters outside the allowed set
    result = IDENTIFIER_ALLOWED.sub("", result)

    # Collapse multiple spaces
    result = re.sub(r"\s+", " ", result).strip()

    # Truncate
    return result[:MAX_IDENTIFIER_LENGTH]


def sanitize_description(text: str) -> str:
    """Sanitize free-text descriptions before prompt inclusion.

    - Strips control characters
    - Strips prompt injection patterns
    - Strips SQL comment sequences
    - Truncates to 500 chars
    """
    if not text:
        return ""

    # Normalize Unicode
    result = unicodedata.normalize("NFC", text)

    # Strip control characters
    result = CONTROL_CHARS.sub("", result)

    # Remove newlines (collapse to spaces)
    result = result.replace("\n", " ").replace("\r", "")

    # Strip prompt injection patterns
    for pattern in INJECTION_PATTERNS:
        result = pattern.sub("[FILTERED]", result)

    # Strip SQL comments
    result = re.sub(r"--.*$", "", result, flags=re.MULTILINE)
    result = re.sub(r"/\*.*?\*/", "", result, flags=re.DOTALL)

    # Collapse spaces
    result = re.sub(r"\s+", " ", result).strip()

    return result[:MAX_DESCRIPTION_LENGTH]


def sanitize_user_query(query: str) -> str:
    """Sanitize user natural language queries before LLM processing.

    - Strips control characters
    - Strips multi-line injection attempts
    - Strips embedded system/instruction overrides
    - Strips SQL injection fragments
    - Truncates to 1000 chars
    """
    if not query:
        return ""

    # Normalize Unicode
    result = unicodedata.normalize("NFC", query)

    # Strip control characters
    result = CONTROL_CHARS.sub("", result)

    # Remove newlines (collapse to spaces — prevents multi-line injection)
    result = result.replace("\n", " ").replace("\r", "")

    # Strip prompt injection patterns
    for pattern in INJECTION_PATTERNS:
        result = pattern.sub("[FILTERED]", result)

    # Strip SQL injection fragments
    for pattern in SQL_INJECTION_PATTERNS:
        result = pattern.sub("[FILTERED]", result)

    # Collapse spaces
    result = re.sub(r"\s+", " ", result).strip()

    return result[:MAX_QUERY_LENGTH]


def has_injection_patterns(text: str) -> list[str]:
    """Check text for injection patterns without modifying it.

    Returns list of detected pattern descriptions (empty if clean).
    Useful for pre-commit scanning of YAML metadata.
    """
    if not text:
        return []

    findings = []
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            findings.append(f"prompt injection: {pattern.pattern}")

    for pattern in SQL_INJECTION_PATTERNS:
        if pattern.search(text):
            findings.append(f"SQL injection: {pattern.pattern}")

    # Check for control characters
    if CONTROL_CHARS.search(text):
        findings.append("control characters detected")

    return findings
