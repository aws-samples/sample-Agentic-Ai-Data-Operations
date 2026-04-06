"""
Tests for the post-run memory extractor (distill_run_insights + lambda_handler).
Uses mocked Bedrock client — no real AWS calls.
"""

import pytest
from unittest.mock import MagicMock

from shared.memory.extractor import (
    distill_run_insights,
    lambda_handler,
    MIN_DECISIONS_FOR_DISTILLATION,
    _parse_distilled_memories,
)


def _make_agent_output(**overrides) -> dict:
    """Minimal AgentOutput dict."""
    base = {
        "agent_name": "Test Agent",
        "agent_type": "quality",
        "workload_name": "test_wl",
        "run_id": "run-001",
        "started_at": "2026-04-06T10:00:00Z",
        "completed_at": "2026-04-06T10:05:00Z",
        "status": "success",
        "artifacts": [],
        "tests": {"unit": {"passed": 5, "failed": 0, "total": 5}},
        "blocking_issues": [],
        "warnings": [],
        "decisions": [],
        "memory_hints": [],
    }
    base.update(overrides)
    return base


def _make_decisions(n: int) -> list:
    """Generate N dummy decisions."""
    return [
        {
            "decision_id": f"d-{i:03d}",
            "category": "test_choice",
            "reasoning": f"Reasoning for decision {i}",
            "choice_made": f"Choice {i}",
            "confidence": "high",
        }
        for i in range(n)
    ]


def _mock_extraction_response(memories: list) -> dict:
    """Build a mock Bedrock converse() response for distill_memories tool."""
    return {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "name": "distill_memories",
                            "input": {"memories": memories},
                        }
                    }
                ]
            }
        }
    }


# ------------------------------------------------------------------
# distill_run_insights
# ------------------------------------------------------------------


class TestDistillRunInsights:
    def test_skips_llm_when_too_few_decisions(self, tmp_path):
        client = MagicMock()
        output = _make_agent_output(decisions=_make_decisions(2))
        count = distill_run_insights("test_wl", output, client, base_dir=tmp_path)
        assert count == 0
        client.converse.assert_not_called()

    def test_processes_memory_hints_without_llm(self, tmp_path):
        client = MagicMock()
        hints = [
            {"type": "project", "content": "pe_ratio has 5% expected nulls"},
            {"type": "feedback", "content": "dont quarantine growth stocks"},
        ]
        output = _make_agent_output(memory_hints=hints, decisions=[])
        count = distill_run_insights("test_wl", output, client, base_dir=tmp_path)
        assert count == 2
        client.converse.assert_not_called()

    def test_calls_bedrock_when_enough_decisions(self, tmp_path):
        client = MagicMock()
        client.converse.return_value = _mock_extraction_response([])
        output = _make_agent_output(decisions=_make_decisions(5))
        distill_run_insights("test_wl", output, client, base_dir=tmp_path)
        client.converse.assert_called_once()

    def test_saves_extracted_memories_to_disk(self, tmp_path):
        client = MagicMock()
        client.converse.return_value = _mock_extraction_response([
            {
                "filename": "schema_fact.md",
                "type": "project",
                "name": "Schema fact",
                "description": "ticker is the PK for stocks",
                "content": "The stocks table uses ticker as primary key.",
            }
        ])
        output = _make_agent_output(decisions=_make_decisions(5))
        count = distill_run_insights("test_wl", output, client, base_dir=tmp_path)
        assert count == 1
        mem_dir = tmp_path / "test_wl" / "memory"
        assert (mem_dir / "schema_fact.md").exists()

    def test_invalid_memory_type_from_llm_is_skipped(self, tmp_path):
        client = MagicMock()
        client.converse.return_value = _mock_extraction_response([
            {
                "filename": "bad.md",
                "type": "invalid_type",
                "name": "Bad",
                "description": "Bad type",
                "content": "Should be skipped",
            }
        ])
        output = _make_agent_output(decisions=_make_decisions(5))
        count = distill_run_insights("test_wl", output, client, base_dir=tmp_path)
        assert count == 0

    def test_combined_hints_and_decisions(self, tmp_path):
        client = MagicMock()
        client.converse.return_value = _mock_extraction_response([
            {
                "filename": "extracted.md",
                "type": "project",
                "name": "Extracted",
                "description": "From decisions",
                "content": "Decision-based insight",
            }
        ])
        hints = [{"type": "project", "content": "Direct hint"}]
        output = _make_agent_output(
            memory_hints=hints,
            decisions=_make_decisions(5),
        )
        count = distill_run_insights("test_wl", output, client, base_dir=tmp_path)
        # 1 hint + 1 extracted = 2
        assert count == 2

    def test_bedrock_error_returns_hints_only(self, tmp_path):
        client = MagicMock()
        client.converse.side_effect = RuntimeError("Service unavailable")
        hints = [{"type": "project", "content": "Still saved"}]
        output = _make_agent_output(
            memory_hints=hints,
            decisions=_make_decisions(5),
        )
        count = distill_run_insights("test_wl", output, client, base_dir=tmp_path)
        assert count == 1  # Only the hint

    def test_empty_output_returns_zero(self, tmp_path):
        client = MagicMock()
        output = _make_agent_output()
        count = distill_run_insights("test_wl", output, client, base_dir=tmp_path)
        assert count == 0


# ------------------------------------------------------------------
# lambda_handler
# ------------------------------------------------------------------


class TestLambdaHandler:
    def test_missing_workload_returns_400(self):
        result = lambda_handler({}, None)
        assert result["statusCode"] == 400

    def test_empty_outputs_returns_zero(self):
        result = lambda_handler({"workload_name": "test", "agent_outputs": []}, None)
        assert result["memories_saved"] == 0


# ------------------------------------------------------------------
# _parse_distilled_memories
# ------------------------------------------------------------------


class TestParseDistilledMemories:
    def test_parses_valid_response(self):
        response = _mock_extraction_response([
            {"filename": "a.md", "type": "project", "name": "A",
             "description": "desc", "content": "body"}
        ])
        result = _parse_distilled_memories(response)
        assert len(result) == 1
        assert result[0]["filename"] == "a.md"

    def test_returns_empty_on_malformed(self):
        assert _parse_distilled_memories({}) == []
