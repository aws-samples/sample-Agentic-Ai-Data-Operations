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


# ---------------------------------------------------------------------------
# The other direction
#
# Everything above checks template -> contract: a slot a template declares must be a
# known, required property. That is the same direction as MissingSlotError
# (renderer.py: `missing = declared - set(spec.keys())`), and it catches the template
# author's mistake — needing data the spec cannot carry.
#
# Nothing checked contract -> template: a property the contract lets a human set that
# no template reads. That failure is silent. The spec validates, render() succeeds, the
# provenance header is written and the drift validator confirms the artifact matches its
# spec — every gate green while the field does nothing at all.
#
# That is how a HIPAA masking gate came to be unenforced in a live run: the human marked
# phi_masking_applied CRITICAL and blocking, it landed in quality_spec.compliance_rules,
# and quality_check.py.j2 has no loop over compliance_rules. Nothing anywhere noticed.
# ---------------------------------------------------------------------------

# Contract properties no template reads. A RATCHET, not a permission slip: each entry is
# a known defect with the finding that proves it, adding a NEW one must fail, and the
# only correct direction is for this to shrink. Fixing a template deletes an entry.
#
# Source: adversarial verifier, session 349b40ee, 23 findings. See ADOP-RUN-ANALYSIS.md.
KNOWN_UNREAD = {
    "bronze": {
        "retention": "L6 - Bronze holds the only raw unhashed PHI and applies no retention",
        "ingestion_mode": "batch/streaming distinction never reaches the script",
        "file_pattern": "not used to filter the source read",
        "compression": "not applied on write",
        "schema_columns": "declared schema is not enforced on read",
    },
    "silver": {
        "null_handling": "M3 - never read; PK nulls are dropped unconditionally instead",
        "quarantine": "H1 - no quarantine branch; enabled/location/retention_days inert",
        "transformations": "no loop over the transformations[] array",
    },
    "gold": {
        "dimensions": "M7 - star_schema dimension tables are never created",
        "output_tables": "M7 - the fact+dimension table list is never rendered",
        "freshness_sla_hours": "declared only; no freshness check is emitted",
        "quality_threshold": "L5 - only quality_gates is rendered; this duplicate is ignored",
    },
    "dag": {
        "failure_handling": "M2 - on_failure_callback never rendered, so failures are silent",
        "sla": "M1 - deadline_minutes unenforced; quality tasks get no execution_timeout",
    },
    "quality": {
        "compliance_rules": "C1 - CRITICAL. The HIPAA masking gate never executes",
        "anomaly_detection": "no anomaly logic is emitted despite the rules being asked for",
    },
}

# Consumed by render() for the 5-line provenance header, not by any template body.
# Verified: renderer.py writes `# schema_version: {schema_version}`.
RENDERER_CONSUMED = {"schema_version"}


def _referenced_slots(template_id: str) -> set[str]:
    """Top-level names a template actually references, via the Jinja AST.

    Not a regex. A word-boundary grep counts a field named in a comment as used, and
    undercounted this by six fields on the first attempt — including gold.dimensions and
    bronze.retention, both of which are real findings.
    """
    from shared.codegen.slot_extractor import extract_slots

    return extract_slots(_template_path(template_id).read_text())


@pytest.mark.parametrize("template_id,spec_type", sorted(TEMPLATE_TO_SPEC.items()))
class TestNoContractFieldGoesUnread:
    def test_no_new_property_goes_unread(self, template_id, spec_type):
        """A field nothing reads is a question asked for nothing."""
        settable = set(_schema(spec_type).get("properties", {}))
        unread = (
            settable
            - _referenced_slots(template_id)
            - RENDERER_CONSUMED
            - set(KNOWN_UNREAD.get(spec_type, {}))
        )
        assert not unread, (
            f"{spec_type}_spec lets a human set these and {template_id} never reads them:\n  "
            + "\n  ".join(sorted(unread))
            + "\n\nRender them, or add each to KNOWN_UNREAD with the finding that justifies it."
        )

    def test_ratchet_lists_nothing_that_is_now_read(self, template_id, spec_type):
        """A stale entry is how a ratchet quietly stops ratcheting.

        Once a template reads a field, its entry is not merely redundant — it is a
        standing exemption, so re-introducing the gap later would not fail.
        """
        stale = sorted(set(KNOWN_UNREAD.get(spec_type, {})) & _referenced_slots(template_id))
        assert not stale, (
            f"{template_id} now reads these — delete them from KNOWN_UNREAD:\n  "
            + "\n  ".join(stale)
        )


def test_every_ratchet_entry_names_a_real_property():
    """A typo in the allowlist is an exemption that protects nothing."""
    bad = [
        f"{spec_type}.{field}"
        for spec_type, entries in KNOWN_UNREAD.items()
        for field in entries
        if field not in _schema(spec_type).get("properties", {})
    ]
    assert not bad, "allowlisted fields no contract defines:\n  " + "\n  ".join(bad)


def test_every_ratchet_entry_states_a_reason():
    """An undocumented exemption is indistinguishable from an oversight."""
    thin = [
        f"{spec_type}.{field}"
        for spec_type, entries in KNOWN_UNREAD.items()
        for field, reason in entries.items()
        if len(reason.strip()) < 20
    ]
    assert not thin, "ratchet entries with no usable reason:\n  " + "\n  ".join(thin)
