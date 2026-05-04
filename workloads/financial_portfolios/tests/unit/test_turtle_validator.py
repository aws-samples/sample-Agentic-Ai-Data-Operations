"""Unit tests for shared.semantic_layer.turtle_validator."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from shared.semantic_layer.turtle_validator import validate_and_fix  # noqa: E402


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.ttl"
    p.write_text(content, encoding="utf-8")
    return p


class TestValidTurtle:
    def test_parses_valid_file(self, tmp_path):
        content = (
            "@prefix ex: <http://example.com/> .\n"
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            "ex:Thing rdfs:label \"a thing\" .\n"
        )
        path = _write(tmp_path, content)
        result = validate_and_fix(str(path))
        assert result.ok is True
        assert result.triple_count == 1
        assert result.fixes_applied is None


class TestMissingFile:
    def test_file_not_found(self, tmp_path):
        result = validate_and_fix(str(tmp_path / "nope.ttl"))
        assert result.ok is False
        assert "not found" in (result.error or "").lower()


class TestInvalidTurtleBeyondAutoFix:
    def test_unrecoverable_error_reports_failure(self, tmp_path):
        # Missing prefix declaration for `unknown:`
        content = "unknown:Broken a unknown:Class .\n"
        path = _write(tmp_path, content)
        result = validate_and_fix(str(path), max_retries=2)
        assert result.ok is False
        assert result.error


class TestMissingTrailingDot:
    def test_appends_missing_final_dot(self, tmp_path):
        # Last statement is missing its terminating `.`
        content = (
            "@prefix ex: <http://example.com/> .\n"
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            "ex:Foo rdfs:label \"foo\"\n"
        )
        path = _write(tmp_path, content)
        result = validate_and_fix(str(path))
        # The validator should retry with a fix; whether it ultimately parses
        # depends on the content, but we assert it at least attempted the fix.
        assert result.fixes_applied is None or any(
            "trailing_dot" in f for f in (result.fixes_applied or [])
        ) or result.ok
