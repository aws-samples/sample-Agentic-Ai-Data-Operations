"""Unit tests for shared.codegen.slot_extractor."""

import pytest

from shared.codegen.slot_extractor import extract_slots, parse_required_slots_header, validate_slots
from shared.codegen.exceptions import MissingSlotError


class TestExtractSlots:
    def test_extracts_simple_variable_slots(self):
        source = "Hello {{ name }}, you have {{ count }} items."
        slots = extract_slots(source)
        assert "name" in slots
        assert "count" in slots

    def test_extracts_slots_from_for_loops(self):
        source = "{% for item in items %}{{ item.name }}{% endfor %}"
        slots = extract_slots(source)
        assert "items" in slots

    def test_extracts_slots_from_if_blocks(self):
        source = "{% if enabled %}Active{% endif %}"
        slots = extract_slots(source)
        assert "enabled" in slots

    def test_does_not_count_loop_variables_as_slots(self):
        source = "{% for x in items %}{{ x }}{% endfor %}"
        slots = extract_slots(source)
        assert "items" in slots
        assert "x" not in slots

    def test_handles_dotted_access(self):
        source = "{{ spec.primary_key }} and {{ config.name }}"
        slots = extract_slots(source)
        assert "spec" in slots
        assert "config" in slots
        assert "primary_key" not in slots


class TestParseRequiredSlotsHeader:
    def test_parses_header_comment(self):
        source = """{# template_id: test #}
{# required_slots: name, age, email #}
Hello {{ name }}"""
        slots = parse_required_slots_header(source)
        assert slots == {"name", "age", "email"}

    def test_returns_empty_set_when_no_header(self):
        source = "Hello {{ name }}"
        assert parse_required_slots_header(source) == set()


class TestValidateSlots:
    def test_raises_on_missing_declared_slot(self):
        source = "{# required_slots: name, age #}\nHello {{ name }}"
        spec = {"name": "Alice"}
        with pytest.raises(MissingSlotError) as exc_info:
            validate_slots(source, spec, "test_template")
        assert "age" in exc_info.value.missing

    def test_passes_when_all_slots_present(self):
        source = "{# required_slots: name, age #}\nHello {{ name }}"
        spec = {"name": "Alice", "age": 30}
        validate_slots(source, spec, "test_template")
