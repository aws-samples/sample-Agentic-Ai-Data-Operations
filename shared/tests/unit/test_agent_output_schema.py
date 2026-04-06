"""
Tests for AgentOutput typed schema and SUBMIT_OUTPUT_TOOL.
"""

import json
import pytest

from shared.templates.agent_output_schema import (
    AgentOutput,
    SUBMIT_OUTPUT_TOOL,
    VALID_AGENT_TYPES,
    VALID_STATUSES,
    compute_input_hash,
)


def _minimal_output(**overrides) -> dict:
    """Return minimal valid AgentOutput kwargs."""
    base = {
        "agent_name": "Test Agent",
        "agent_type": "metadata",
        "workload_name": "test_workload",
        "run_id": "run-001",
        "started_at": "2026-04-06T10:00:00Z",
        "completed_at": "2026-04-06T10:05:00Z",
        "status": "success",
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------
# SUBMIT_OUTPUT_TOOL schema validation
# ------------------------------------------------------------------


class TestSubmitOutputTool:
    def test_tool_has_correct_name(self):
        assert SUBMIT_OUTPUT_TOOL["toolSpec"]["name"] == "submit_agent_output"

    def test_tool_has_all_required_fields(self):
        required = SUBMIT_OUTPUT_TOOL["toolSpec"]["inputSchema"]["json"]["required"]
        expected = {
            "agent_name", "agent_type", "workload_name", "run_id",
            "started_at", "completed_at", "status", "artifacts",
            "blocking_issues", "tests",
        }
        assert set(required) == expected

    def test_tool_agent_type_enum(self):
        props = SUBMIT_OUTPUT_TOOL["toolSpec"]["inputSchema"]["json"]["properties"]
        assert set(props["agent_type"]["enum"]) == VALID_AGENT_TYPES

    def test_tool_status_enum(self):
        props = SUBMIT_OUTPUT_TOOL["toolSpec"]["inputSchema"]["json"]["properties"]
        assert set(props["status"]["enum"]) == VALID_STATUSES

    def test_tool_has_memory_hints_property(self):
        props = SUBMIT_OUTPUT_TOOL["toolSpec"]["inputSchema"]["json"]["properties"]
        assert "memory_hints" in props
        assert props["memory_hints"]["type"] == "array"


# ------------------------------------------------------------------
# from_bedrock_tool_call
# ------------------------------------------------------------------


class TestFromBedrockToolCall:
    def test_parses_valid_tool_call(self):
        tool_use = {
            "name": "submit_agent_output",
            "input": _minimal_output(),
        }
        output = AgentOutput.from_bedrock_tool_call(tool_use)
        assert output.agent_name == "Test Agent"
        assert output.agent_type == "metadata"
        assert output.status == "success"

    def test_raises_on_wrong_tool_name(self):
        tool_use = {"name": "wrong_tool", "input": _minimal_output()}
        with pytest.raises(ValueError, match="Expected tool 'submit_agent_output'"):
            AgentOutput.from_bedrock_tool_call(tool_use)

    def test_raises_on_missing_required_field(self):
        incomplete = _minimal_output()
        del incomplete["agent_name"]
        tool_use = {"name": "submit_agent_output", "input": incomplete}
        with pytest.raises(TypeError):
            AgentOutput.from_bedrock_tool_call(tool_use)

    def test_memory_hints_default_empty(self):
        tool_use = {"name": "submit_agent_output", "input": _minimal_output()}
        output = AgentOutput.from_bedrock_tool_call(tool_use)
        assert output.memory_hints == []

    def test_memory_hints_preserved(self):
        hints = [{"type": "project", "content": "pe_ratio has 5% nulls"}]
        tool_use = {
            "name": "submit_agent_output",
            "input": _minimal_output(memory_hints=hints),
        }
        output = AgentOutput.from_bedrock_tool_call(tool_use)
        assert output.memory_hints == hints


# ------------------------------------------------------------------
# Serialization roundtrips
# ------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_roundtrip(self):
        original = AgentOutput(**_minimal_output(
            artifacts=[{"path": "config/source.yaml", "type": "config", "checksum": "abc"}],
            decisions=[{"decision_id": "d-001", "category": "test", "reasoning": "r",
                        "choice_made": "c", "alternatives_considered": [], "rejection_reasons": {},
                        "confidence": "high", "context": {}}],
            memory_hints=[{"type": "project", "content": "fact"}],
        ))
        restored = AgentOutput.from_dict(original.to_dict())
        assert restored.to_dict() == original.to_dict()

    def test_to_json_roundtrip(self):
        original = AgentOutput(**_minimal_output())
        restored = AgentOutput.from_json(original.to_json())
        assert restored.agent_name == original.agent_name

    def test_from_dict_filters_unknown_keys(self):
        data = _minimal_output(unknown_future_field="ignored")
        output = AgentOutput.from_dict(data)
        assert output.agent_name == "Test Agent"
        assert not hasattr(output, "unknown_future_field")

    def test_from_dict_without_memory_hints_uses_default(self):
        """Old serialized dicts that lack memory_hints still work."""
        data = _minimal_output()
        assert "memory_hints" not in data
        output = AgentOutput.from_dict(data)
        assert output.memory_hints == []


# ------------------------------------------------------------------
# Orchestrator decision helpers
# ------------------------------------------------------------------


class TestCanProceed:
    def test_can_proceed_true_when_success_no_blocking(self):
        output = AgentOutput(**_minimal_output())
        assert output.can_proceed is True

    def test_can_proceed_false_when_has_blocking_issues(self):
        output = AgentOutput(**_minimal_output(
            blocking_issues=["Schema mismatch"],
        ))
        assert output.can_proceed is False

    def test_can_proceed_false_when_failed_status(self):
        output = AgentOutput(**_minimal_output(
            status="failed",
            blocking_issues=["Crash"],
        ))
        assert output.can_proceed is False
        assert output.needs_retry is True
