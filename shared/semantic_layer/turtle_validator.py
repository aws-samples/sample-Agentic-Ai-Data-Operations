"""
Turtle Validator — parses generated .ttl files with rdflib, attempts
bounded auto-fixes for common syntax issues, and reports blocking errors
when the file cannot be salvaged.

Public API:
    validate_and_fix(ttl_path, max_retries=2) -> ValidationResult
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from rdflib import Graph


@dataclass
class ValidationResult:
    ok: bool
    ttl_path: str
    triple_count: int = 0
    fixes_applied: Optional[List[str]] = None
    error: Optional[str] = None


def validate_and_fix(ttl_path: str, max_retries: int = 2) -> ValidationResult:
    """
    Parse a Turtle file; if parsing fails, apply bounded auto-fixes and retry.

    Fixes attempted (in order):
      1. Escape unescaped double quotes inside `"..."` literals.
      2. Strip non-ASCII characters from rdfs:label / rdfs:comment strings.
      3. Add a trailing `.` if the final statement is missing one.

    Args:
        ttl_path: Path to the .ttl file to validate.
        max_retries: Maximum number of fix+reparse cycles. Default 2.

    Returns:
        ValidationResult with ok=True and triple_count on success, else
        ok=False with a diagnostic error message.
    """
    path = Path(ttl_path)
    if not path.exists():
        return ValidationResult(
            ok=False,
            ttl_path=str(path),
            error=f"File not found: {path}",
        )

    fixes_applied: List[str] = []
    attempt = 0
    last_error: Optional[str] = None

    while attempt <= max_retries:
        text = path.read_text(encoding="utf-8")
        try:
            g = Graph()
            g.parse(data=text, format="turtle")
            return ValidationResult(
                ok=True,
                ttl_path=str(path),
                triple_count=len(g),
                fixes_applied=fixes_applied or None,
            )
        except Exception as exc:
            last_error = str(exc)
            if attempt >= max_retries:
                break
            fixed_text, applied = _apply_fixes(text, attempt)
            if fixed_text == text:
                # No fix available; no point in retrying.
                break
            path.write_text(fixed_text, encoding="utf-8")
            fixes_applied.extend(applied)
            attempt += 1

    return ValidationResult(
        ok=False,
        ttl_path=str(path),
        fixes_applied=fixes_applied or None,
        error=last_error,
    )


def _apply_fixes(text: str, attempt: int) -> tuple[str, List[str]]:
    """Apply escalating fixes. Returns (possibly-modified text, fix labels)."""
    applied: List[str] = []

    # Attempt 0: escape unescaped quotes inside simple "..." string literals.
    if attempt == 0:
        def _escape_quotes(match: re.Match) -> str:
            inner = match.group(1)
            # Only escape lone " not already preceded by a backslash.
            fixed = re.sub(r'(?<!\\)"', r'\\"', inner)
            return f'"{fixed}"'

        # This regex is conservative: only rewrites "..." that do NOT span
        # whitespace boundaries (so we don't clobber multi-line literals).
        new_text = re.sub(r'"([^"\n]*?)"', _escape_quotes, text)
        if new_text != text:
            applied.append("escape_unescaped_quotes_in_literals")
            return new_text, applied

    # Attempt 1: strip non-ASCII from rdfs:label / rdfs:comment literals.
    if attempt == 1:
        def _strip_non_ascii(match: re.Match) -> str:
            prefix = match.group(1)
            literal = match.group(2)
            cleaned = "".join(ch for ch in literal if ord(ch) < 128)
            return f'{prefix}"{cleaned}"'

        new_text = re.sub(
            r'(rdfs:(?:label|comment)\s+)"([^"\n]*)"',
            _strip_non_ascii,
            text,
        )
        if new_text != text:
            applied.append("strip_non_ascii_from_labels")
            return new_text, applied

    # Attempt 2+: ensure the file ends with a `.` on the last non-blank line.
    lines = text.rstrip().splitlines()
    if lines and not lines[-1].rstrip().endswith("."):
        lines[-1] = lines[-1].rstrip() + " ."
        applied.append("append_missing_trailing_dot")
        return "\n".join(lines) + "\n", applied

    return text, applied
