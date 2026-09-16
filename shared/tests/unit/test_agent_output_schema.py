"""
Tests for AgentOutput typed schema and SUBMIT_OUTPUT_TOOL.
"""

import json
import pytest

from shared.templates.agent_output_schema import (
    AgentOutput,
    REQUIRED_OUTPUT_FIELDS,
    SUBMIT_OUTPUT_TOOL,
    VALID_AGENT_TYPES,
    VALID_STATUSES,
    compute_input_hash,
    extract_output_payload,
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


def _complete_output(**overrides) -> dict:
    """Return an AgentOutput payload carrying every REQUIRED_OUTPUT_FIELDS key."""
    base = _minimal_output(
        artifacts=[{"path": "config/source.yaml", "type": "config", "checksum": "abc"}],
        tests={"unit": {"passed": 3, "failed": 0, "total": 3}},
        blocking_issues=[],
        decisions=[{"category": "schema", "choice_made": "typed x as DATE",
                    "reasoning": "all sampled values are ISO-8601"}],
    )
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
            "blocking_issues", "tests", "decisions",
        }
        assert set(required) == expected

    def test_decisions_must_be_non_empty(self):
        """rules/07 makes the cognitive surface mandatory, so [] is not a valid answer."""
        props = SUBMIT_OUTPUT_TOOL["toolSpec"]["inputSchema"]["json"]["properties"]
        assert props["decisions"]["minItems"] == 1

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
# Claude Code sub-agent message parsing
# ------------------------------------------------------------------


class TestFromAgentMessage:
    def test_parses_fenced_json_block(self):
        payload = _complete_output()
        msg = f"Done.\n\n```json\n{json.dumps(payload, indent=2)}\n```\n"
        output = AgentOutput.from_agent_message(msg)
        assert output.agent_name == "Test Agent"
        assert output.can_proceed is True

    def test_parses_fence_without_language_tag(self):
        msg = f"```\n{json.dumps(_complete_output())}\n```"
        assert AgentOutput.from_agent_message(msg).agent_type == "metadata"

    def test_last_block_wins_over_intermediate_example(self):
        example = json.dumps(_complete_output(agent_name="Example Only"))
        final = json.dumps(_complete_output(agent_name="Real Agent"))
        msg = (
            f"Here is the shape I will return:\n```json\n{example}\n```\n"
            f"And my actual result:\n```json\n{final}\n```"
        )
        assert AgentOutput.from_agent_message(msg).agent_name == "Real Agent"

    def test_falls_back_to_unfenced_json(self):
        msg = f"Result follows.\n{json.dumps(_complete_output())}"
        assert AgentOutput.from_agent_message(msg).workload_name == "test_workload"

    def test_nested_objects_do_not_shadow_payload(self):
        """tests{} and artifacts[] contain braces — the outer object must win."""
        payload = _complete_output(
            tests={
                "unit": {"passed": 3, "failed": 0, "total": 3},
                "integration": {"passed": 1, "failed": 0, "total": 1},
            }
        )
        output = AgentOutput.from_agent_message(json.dumps(payload))
        assert output.total_tests_passed == 4

    def test_preserves_decisions_and_memory_hints(self):
        payload = _complete_output(
            decisions=[{"decision_id": "d-001", "category": "schema_inference",
                        "reasoning": "only unique column", "choice_made": "claim_id",
                        "alternatives_considered": ["member_id"],
                        "rejection_reasons": {"member_id": "not unique"},
                        "confidence": "high", "context": {}}],
            memory_hints=[{"type": "project", "content": "pe_ratio has 5% expected nulls"}],
        )
        output = AgentOutput.from_agent_message(f"```json\n{json.dumps(payload)}\n```")
        assert output.decisions[0]["choice_made"] == "claim_id"
        assert output.memory_hints[0]["type"] == "project"

    def test_raises_when_no_json_present(self):
        with pytest.raises(ValueError, match="No JSON object found"):
            AgentOutput.from_agent_message("I finished the work. All tests pass.")

    def test_raises_listing_missing_required_fields(self):
        payload = _minimal_output()  # no artifacts / tests / blocking_issues
        with pytest.raises(ValueError, match="missing required field") as exc:
            AgentOutput.from_agent_message(f"```json\n{json.dumps(payload)}\n```")
        message = str(exc.value)
        assert "artifacts" in message
        assert "blocking_issues" in message
        assert "tests" in message
        assert "decisions" in message

    def test_raises_on_empty_decisions(self):
        """An empty array satisfies presence but records no reasoning — reject it."""
        payload = _complete_output(decisions=[])
        with pytest.raises(ValueError, match="decisions is empty"):
            AgentOutput.from_agent_message(f"```json\n{json.dumps(payload)}\n```")

    def test_accepts_a_single_decision(self):
        out = AgentOutput.from_agent_message(
            f"```json\n{json.dumps(_complete_output())}\n```"
        )
        assert len(out.decisions) == 1

    def test_malformed_json_in_fence_falls_through_to_error(self):
        with pytest.raises(ValueError, match="No JSON object found"):
            AgentOutput.from_agent_message("```json\n{not valid json,,,}\n```")

    def test_required_fields_track_the_bedrock_tool_spec(self):
        """Both return paths must enforce the same required set."""
        spec_required = set(
            SUBMIT_OUTPUT_TOOL["toolSpec"]["inputSchema"]["json"]["required"]
        )
        assert set(REQUIRED_OUTPUT_FIELDS) == spec_required

    def test_extract_returns_none_for_prose(self):
        assert extract_output_payload("no json here") is None


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
