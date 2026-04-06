"""
Tests for find_relevant_memories (curate_relevant_memories) and MemoryLoader.
Uses mocked Bedrock client — no real AWS calls.
"""

import pytest
from unittest.mock import MagicMock, patch

from shared.memory.workload_memory import WorkloadMemory
from shared.memory.find_relevant_memories import (
    curate_relevant_memories,
    _extract_filenames_from_response,
    CURATOR_TOOL,
)
from shared.memory.memory_loader import MemoryLoader


def _seed_memory(mem: WorkloadMemory) -> None:
    """Write 3 test memory files."""
    mem.inscribe("source_facts.md", "project", "Source facts",
                 "S3 CSV source with 3 tables", "PK=ticker, SOX compliance")
    mem.inscribe("known_quirks.md", "project", "Known quirks",
                 "pe_ratio has expected 5% nulls", "Do not quarantine pe_ratio nulls")
    mem.inscribe("quality_thresholds.md", "project", "Quality thresholds",
                 "95% completeness required", "Zero critical failures")


def _mock_bedrock_response(selected_files: list) -> dict:
    """Build a mock Bedrock converse() response with tool_use."""
    return {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "name": "curate_memory_files",
                            "input": {"selected_files": selected_files},
                        }
                    }
                ]
            }
        }
    }


# ------------------------------------------------------------------
# curate_relevant_memories
# ------------------------------------------------------------------


class TestCurateRelevantMemories:
    def test_returns_empty_when_no_memory_files(self, tmp_path):
        mem = WorkloadMemory("test_wl", base_dir=tmp_path)
        mem._ensure_dir()
        client = MagicMock()
        result = curate_relevant_memories("Generate quality rules", mem, client)
        assert result == []
        client.converse.assert_not_called()

    def test_returns_empty_when_bedrock_selects_nothing(self, tmp_path):
        mem = WorkloadMemory("test_wl", base_dir=tmp_path)
        _seed_memory(mem)
        client = MagicMock()
        client.converse.return_value = _mock_bedrock_response([])
        result = curate_relevant_memories("query", mem, client)
        assert result == []

    def test_calls_bedrock_with_manifest_not_full_content(self, tmp_path):
        mem = WorkloadMemory("test_wl", base_dir=tmp_path)
        _seed_memory(mem)
        client = MagicMock()
        client.converse.return_value = _mock_bedrock_response(["source_facts.md"])

        curate_relevant_memories("query", mem, client)

        call_args = client.converse.call_args
        user_msg = call_args[1]["messages"][0]["content"][0]["text"]
        # Manifest should contain description but NOT full file content
        assert "S3 CSV source with 3 tables" in user_msg
        assert "PK=ticker, SOX compliance" not in user_msg

    def test_filters_already_surfaced_files(self, tmp_path):
        mem = WorkloadMemory("test_wl", base_dir=tmp_path)
        _seed_memory(mem)
        client = MagicMock()
        client.converse.return_value = _mock_bedrock_response(["source_facts.md"])

        # Mark source_facts.md as already surfaced
        result = curate_relevant_memories(
            "query", mem, client,
            already_surfaced={"source_facts.md", "known_quirks.md", "quality_thresholds.md"},
        )
        # All candidates filtered out — no Bedrock call
        assert result == []
        client.converse.assert_not_called()

    def test_respects_max_memories_limit(self, tmp_path):
        mem = WorkloadMemory("test_wl", base_dir=tmp_path)
        _seed_memory(mem)
        client = MagicMock()
        # Bedrock returns all 3 but max is 2
        client.converse.return_value = _mock_bedrock_response([
            "source_facts.md", "known_quirks.md", "quality_thresholds.md",
        ])
        result = curate_relevant_memories("query", mem, client, max_memories=2)
        assert len(result) <= 2

    def test_invalid_filenames_from_bedrock_are_filtered(self, tmp_path):
        mem = WorkloadMemory("test_wl", base_dir=tmp_path)
        _seed_memory(mem)
        client = MagicMock()
        client.converse.return_value = _mock_bedrock_response([
            "source_facts.md", "nonexistent.md",
        ])
        result = curate_relevant_memories("query", mem, client)
        # Only source_facts.md should be returned
        assert len(result) == 1
        assert "PK=ticker" in result[0]

    def test_uses_tool_choice_for_structured_output(self, tmp_path):
        mem = WorkloadMemory("test_wl", base_dir=tmp_path)
        _seed_memory(mem)
        client = MagicMock()
        client.converse.return_value = _mock_bedrock_response(["source_facts.md"])

        curate_relevant_memories("query", mem, client)

        call_args = client.converse.call_args[1]
        assert "toolConfig" in call_args
        assert call_args["toolConfig"]["toolChoice"] == {
            "tool": {"name": "curate_memory_files"}
        }

    def test_handles_bedrock_error_gracefully(self, tmp_path):
        mem = WorkloadMemory("test_wl", base_dir=tmp_path)
        _seed_memory(mem)
        client = MagicMock()
        client.converse.side_effect = RuntimeError("Service unavailable")
        result = curate_relevant_memories("query", mem, client)
        assert result == []


# ------------------------------------------------------------------
# _extract_filenames_from_response
# ------------------------------------------------------------------


class TestExtractFilenames:
    def test_parses_valid_response(self):
        response = _mock_bedrock_response(["a.md", "b.md"])
        assert _extract_filenames_from_response(response) == ["a.md", "b.md"]

    def test_returns_empty_on_malformed_response(self):
        assert _extract_filenames_from_response({}) == []
        assert _extract_filenames_from_response({"output": {}}) == []


# ------------------------------------------------------------------
# MemoryLoader
# ------------------------------------------------------------------


class TestMemoryLoader:
    def test_load_for_phase_returns_empty_when_no_memory(self, tmp_path):
        loader = MemoryLoader("empty_wl", bedrock_client=MagicMock(), base_dir=tmp_path)
        loader.memory._ensure_dir()
        result = loader.load_for_phase("some query")
        assert result == ""

    def test_collect_hint_queues_hint(self, tmp_path):
        loader = MemoryLoader("test_wl", bedrock_client=MagicMock(), base_dir=tmp_path)
        loader.collect_hint({"type": "project", "content": "pe_ratio nulls are expected"})
        assert len(loader._pending_hints) == 1

    def test_collect_hint_ignores_invalid(self, tmp_path):
        loader = MemoryLoader("test_wl", bedrock_client=MagicMock(), base_dir=tmp_path)
        loader.collect_hint({"invalid": "no type or content"})
        loader.collect_hint("not a dict")
        assert len(loader._pending_hints) == 0

    def test_flush_hints_creates_memory_files(self, tmp_path):
        loader = MemoryLoader("test_wl", bedrock_client=MagicMock(), base_dir=tmp_path)
        loader.collect_hint({"type": "project", "content": "pe_ratio nulls ok"})
        loader.collect_hint({"type": "feedback", "content": "dont quarantine growth stocks"})
        count = loader.flush_hints_to_disk()
        assert count == 2
        # Verify files exist
        files = list(loader.memory.memory_dir.glob("hint_*.md"))
        assert len(files) == 2

    def test_flush_empty_returns_zero(self, tmp_path):
        loader = MemoryLoader("test_wl", bedrock_client=MagicMock(), base_dir=tmp_path)
        assert loader.flush_hints_to_disk() == 0
