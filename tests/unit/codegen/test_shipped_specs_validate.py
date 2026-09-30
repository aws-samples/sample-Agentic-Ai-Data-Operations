"""Every spec shipped under workloads/*/config/ must validate against its contract.

Nothing checked this. The drift validator re-renders artifacts and compares hashes, so it only
sees specs that produced an artifact — and `customer_master/config/quality.yaml` produced none,
because that workload's `scripts/quality/` holds only a hand-written `glue_data_quality.py`.
An invalid spec whose template was never run is invisible to every gate in the repo: the
contract is not consulted, the renderer is not called, and there is no artifact to drift.

It was found by validating the shipped specs by hand while looking for something else, which is
not a mechanism. This test is the mechanism.

The same shape as EXEMPT_HEADERLESS in drift_validator.py: known-bad entries are named with
their errors, a NEW invalid spec fails immediately, and the list can only shrink.
"""

from pathlib import Path

import pytest
import yaml

from shared.codegen.spec_loader import validate_spec

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKLOADS = PROJECT_ROOT / "workloads"

# spec filename -> the spec type whose contract governs it
SPEC_TYPES = {
    "bronze.yaml": "bronze",
    "silver.yaml": "silver",
    "gold.yaml": "gold",
    "quality.yaml": "quality",
    "dag.yaml": "dag",
}

# Specs that do not validate today. A RATCHET: each entry names the substrings of the errors it
# is allowed to produce, so a DIFFERENT error in the same file still fails.
KNOWN_INVALID = {
    "customer_master/config/quality.yaml": {
        "errors": ["date_range", "conditional", "'column' is a required property"],
        "reason": (
            "Two rules use check_type 'date_range' and one uses 'conditional'; neither is in "
            "the quality_rule enum, and one rule omits the required 'column'. Predates the "
            "contract. Never noticed because customer_master has no rendered quality artifact "
            "at all — scripts/quality/ holds only the hand-written glue_data_quality.py — so "
            "the spec was never passed to validate_spec by anything. Fixing it means choosing "
            "what those two rules should be, which is a data-owner decision: 'date_range' is "
            "probably 'range' on a date column, but 'conditional' has no obvious equivalent "
            "and may need custom_sql."
        ),
    },
}


def _shipped_specs():
    if not WORKLOADS.is_dir():
        return []
    out = []
    for workload in sorted(WORKLOADS.iterdir()):
        config = workload / "config"
        if not config.is_dir():
            continue
        for filename, spec_type in sorted(SPEC_TYPES.items()):
            path = config / filename
            if path.exists():
                out.append((path.relative_to(WORKLOADS).as_posix(), spec_type))
    return out


SHIPPED = _shipped_specs()


def test_there_are_specs_to_check():
    """Otherwise every test below passes by iterating nothing."""
    assert len(SHIPPED) >= 5, f"only found {len(SHIPPED)} shipped specs; the glob is wrong"


@pytest.mark.parametrize("rel,spec_type", SHIPPED, ids=[r for r, _ in SHIPPED])
def test_shipped_spec_validates(rel, spec_type):
    errors = validate_spec(yaml.safe_load((WORKLOADS / rel).read_text()), spec_type)
    known = KNOWN_INVALID.get(rel)

    if known is None:
        assert not errors, (
            f"workloads/{rel} does not satisfy {spec_type}_spec.schema.json:\n  "
            + "\n  ".join(dict.fromkeys(errors))
            + "\n\nFix the spec, or add it to KNOWN_INVALID with the reason it cannot be fixed."
        )
        return

    assert errors, (
        f"workloads/{rel} now validates — remove it from KNOWN_INVALID. A stale entry is a "
        f"standing exemption, so re-introducing the problem later would not fail."
    )
    unexpected = [
        e for e in dict.fromkeys(errors)
        if not any(frag in e for frag in known["errors"])
    ]
    assert not unexpected, (
        f"workloads/{rel} has a NEW error beyond the ones it is exempted for:\n  "
        + "\n  ".join(unexpected)
    )


def test_every_known_invalid_entry_names_a_real_file():
    missing = sorted(k for k in KNOWN_INVALID if not (WORKLOADS / k).exists())
    assert not missing, "KNOWN_INVALID names files that do not exist:\n  " + "\n  ".join(missing)


def test_every_known_invalid_entry_states_a_reason():
    thin = sorted(k for k, v in KNOWN_INVALID.items() if len(v["reason"].strip()) < 60)
    assert not thin, "exemptions with no usable reason:\n  " + "\n  ".join(thin)


def test_the_list_only_shrinks():
    """One entry when this test was written. Fix a spec to lower it; never raise it."""
    assert len(KNOWN_INVALID) <= 1, (
        f"KNOWN_INVALID has grown to {len(KNOWN_INVALID)}. A new spec should validate, not be "
        f"exempted."
    )
