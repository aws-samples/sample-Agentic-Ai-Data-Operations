"""Every slot a template requires must be required by its contract too.

Without this, a sub-agent can build a spec that passes `validate_spec()` and then dies at
`render()` with MissingSlotError — a failure that surfaces after the agent has already
reported success, instead of at validation time.
"""

import json
from pathlib import Path

import pytest

from shared.codegen.renderer import parse_required_slots_header

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = PROJECT_ROOT / "shared" / "templates"
CONTRACTS = PROJECT_ROOT / "contracts" / "v1"

# template_id -> spec type whose schema governs it
TEMPLATE_TO_SPEC = {
    "bronze_ingestion": "bronze",
    "silver_transform": "silver",
    "gold_aggregate": "gold",
    "quality_check": "quality",
    "airflow_dag": "dag",
}


def _template_path(template_id: str) -> Path:
    for ext in (".py.j2", ".sql.j2", ".yaml.j2"):
        path = TEMPLATES / f"{template_id}{ext}"
        if path.exists():
            return path
    pytest.fail(f"No template found for {template_id}")


def _declared_slots(template_id: str) -> set[str]:
    return parse_required_slots_header(_template_path(template_id).read_text()) or set()


def _schema(spec_type: str) -> dict:
    return json.loads((CONTRACTS / f"{spec_type}_spec.schema.json").read_text())


@pytest.mark.parametrize("template_id,spec_type", sorted(TEMPLATE_TO_SPEC.items()))
class TestTemplateSchemaAgreement:
    def test_template_declares_its_slots(self, template_id, spec_type):
        assert _declared_slots(template_id), (
            f"{template_id} declares no required slots, so render() cannot validate them"
        )

    def test_every_declared_slot_is_a_known_property(self, template_id, spec_type):
        """A slot with no property can never be supplied — the schema is closed."""
        schema = _schema(spec_type)
        unknown = _declared_slots(template_id) - set(schema.get("properties", {}))
        assert not unknown, (
            f"{template_id} requires {sorted(unknown)}, absent from "
            f"{spec_type}_spec.schema.json properties (additionalProperties is false)"
        )

    def test_every_declared_slot_is_schema_required(self, template_id, spec_type):
        """Otherwise a schema-valid spec can still raise MissingSlotError."""
        schema = _schema(spec_type)
        gap = _declared_slots(template_id) - set(schema.get("required", []))
        assert not gap, (
            f"{template_id} requires {sorted(gap)} but {spec_type}_spec.schema.json does not "
            f"list them in `required` — validation would pass and render() would fail"
        )
