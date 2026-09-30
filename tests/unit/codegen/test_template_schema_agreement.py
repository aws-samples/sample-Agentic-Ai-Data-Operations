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
        # quarantine was here (H1). drop_exact_duplicates_only now writes PK conflicts to
        # quarantine.location, so the template reads it and the entry had to go — which is
        # the ratchet working: fixing a template makes its exemption fail as stale.
        # retention_days remains declarative (L6); no template applies a lifecycle rule.
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


# ---------------------------------------------------------------------------
# A third direction: guidance -> contract -> template
#
# The two checks above keep the contracts and templates honest with each other. Neither
# looks at the prose the model actually reads. `regulation/hipaa.md` recommended a masking
# method per PHI column type, and of its six recommendations two were absent from the
# method enum (spec validation failure), one was in the enum but unimplemented (render
# refused, and before that refusal existed it emitted no masking at all), and two named
# plain `hash` for SSN and date of birth, whose input spaces are ~10^9 and ~40,000 — a
# rainbow-table lookup rather than a one-way function.
#
# Found by `claude plugin eval`: the hipaa-phi-controls case failed
# `phi-masked-in-silver` 3-0 because the model correctly followed the runbook to a method
# the system could not deliver. A contract value nothing recommends is inert; a
# recommendation the contract rejects is worse.
# ---------------------------------------------------------------------------

MASKING_GUIDANCE_DOCS = [
    "runbooks/data-onboarding-agent/regulation/hipaa.md",
]

# Methods a doc may name while telling the reader NOT to use them. The "Not available"
# table is the point of that section, so its entries must be allowed to appear.
_NEGATIVE_SECTION_MARKERS = ("Not available", "do not name these")


def _masking_enum() -> set[str]:
    schema = _schema("silver")
    return set(
        schema["properties"]["pii_masking"]["properties"]["columns"]["items"]
        ["properties"]["method"]["enum"]
    )


def _implemented_masking_methods() -> set[str]:
    import re

    source = _template_path("silver_transform").read_text()
    return set(re.findall(r'col_mask\.method == "([a-z_]+)"', source))


@pytest.mark.parametrize("doc", MASKING_GUIDANCE_DOCS)
def test_recommended_masking_methods_exist_and_are_implemented(doc):
    """Every method a guidance doc recommends must validate AND render.

    Only the recommendation table is checked — the section that lists unavailable methods
    has to be able to name them.
    """
    import re

    text = (PROJECT_ROOT / doc).read_text()
    # Everything before the "Not available" heading is recommendation.
    cut = len(text)
    for marker in _NEGATIVE_SECTION_MARKERS:
        i = text.find(marker)
        if i != -1:
            cut = min(cut, i)
    recommending = text[:cut]

    # Methods appear as `backticked` values in the table's Method column.
    named = set(re.findall(r"`([a-z_]{4,24})`", recommending))
    candidates = named & (
        _masking_enum() | {"mask_email", "generalize", "anonymize", "pseudonymize", "encrypt_kms"}
    )

    not_in_contract = sorted(candidates - _masking_enum())
    assert not not_in_contract, (
        f"{doc} recommends masking methods the contract rejects: {not_in_contract}\n"
        f"A spec naming one of these fails validation. Enum: {sorted(_masking_enum())}"
    )

    unimplemented = sorted(candidates & _masking_enum() - _implemented_masking_methods())
    assert not unimplemented, (
        f"{doc} recommends methods silver_transform.py.j2 has no branch for: "
        f"{unimplemented}\nThe render is refused. Implemented: "
        f"{sorted(_implemented_masking_methods())}"
    )


@pytest.mark.parametrize("doc", MASKING_GUIDANCE_DOCS)
def test_guidance_does_not_recommend_plain_hash_for_an_enumerable_identifier(doc):
    """`hash` on an SSN or a date of birth is a lookup, not a one-way function.

    ~10^9 and ~40,000 candidates respectively. `hash_salted` exists for these, and a
    guidance table that names plain `hash` beside `ssn` or `dob` will be followed.
    """
    text = (PROJECT_ROOT / doc).read_text()
    cut = len(text)
    for marker in _NEGATIVE_SECTION_MARKERS:
        i = text.find(marker)
        if i != -1:
            cut = min(cut, i)

    offenders = []
    for line in text[:cut].splitlines():
        if not line.strip().startswith("|"):
            continue
        low = line.lower()
        names_enumerable = any(c in low for c in ("ssn", "dob", "date_of_birth", "member_id"))
        # `hash` but not `hash_salted`
        plain_hash = "`hash`" in line or "hash (sha-256)" in low
        if names_enumerable and plain_hash:
            offenders.append(line.strip()[:90])

    assert not offenders, (
        f"{doc} recommends plain `hash` for an enumerable identifier:\n  "
        + "\n  ".join(offenders)
        + "\nUse hash_salted, which requires salt_secret_id."
    )


def test_hash_salted_is_discoverable_by_the_model():
    """A contract value nothing recommends is very nearly no value at all.

    hash_salted was added to the enum and the template, and for a while appeared in
    neither the runbooks, the agents, the skills nor the README — so the model kept
    choosing `hash` from the guidance it does read, and the eval kept failing.

    Scans the repo's own guidance only. `plugins/claude-code/` is excluded deliberately:
    its runbooks are byte-identical vendored copies, so counting them lets the source
    guidance lose the mention while the test still passes on the duplicate. Mutation
    testing found exactly that — removing hash_salted from the repo runbook left this
    green, because the plugin's copy still had it.
    """
    searched = 0
    hits = []
    for sub in ("runbooks", "skills", "agents", ".claude", "docs"):
        root = PROJECT_ROOT / sub
        if not root.is_dir():
            continue
        for p in root.rglob("*.md"):
            if "plugins" in p.parts or ".git" in p.parts:
                continue
            searched += 1
            if "hash_salted" in p.read_text(errors="ignore"):
                hits.append(p.relative_to(PROJECT_ROOT).as_posix())

    assert searched > 0, "scanned no guidance files — the paths are wrong, not the guidance"
    assert hits, (
        f"hash_salted appears in none of the {searched} guidance files the model reads "
        f"(excluding the plugin's vendored copies). Add it to the HIPAA runbook's masking "
        f"table at minimum, or nothing will ever select it over plain hash."
    )
