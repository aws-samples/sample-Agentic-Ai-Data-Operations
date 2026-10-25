"""Regression tests for natural-language regulation detection."""

import pytest

from shared.compliance.regulation_detector import detect_regulations


def test_detects_gdpr_from_plain_language():
    result = detect_regulations("This new workload must follow GDPR requirements.")

    assert result.active == ("GDPR",)
    assert result.as_human_answer() == ["GDPR"]
    assert result.has_explicit_selection is True


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Apply the General Data Protection Regulation controls.", ("GDPR",)),
        ("Use CCPA and GDPR for this workload.", ("CCPA", "GDPR")),
        ("This is HIPAA compliant.", ("HIPAA",)),
        ("Apply Sarbanes-Oxley controls.", ("SOX",)),
        ("The workload is PCI-DSS scoped.", ("PCI",)),
    ],
)
def test_detects_supported_aliases_and_preserves_mention_order(text, expected):
    assert detect_regulations(text).active == expected


def test_duplicate_mentions_are_normalized():
    result = detect_regulations("GDPR is required. GDPR controls must be applied.")

    assert result.active == ("GDPR",)
    assert len(result.matches) == 2


@pytest.mark.parametrize(
    "text",
    [
        "GDPR is not required for this workload.",
        "Do not apply GDPR.",
        "This workload is without PCI DSS.",
    ],
)
def test_negated_mentions_do_not_activate_a_regulation(text):
    result = detect_regulations(text)

    assert result.active == ()
    assert result.excluded
    assert all(match.negated for match in result.matches)


def test_schema_columns_do_not_activate_regulations():
    result = detect_regulations(
        "The CSV contains customer_email and credit_card_number columns."
    )

    assert result.active == ()
    assert result.matches == ()


def test_non_string_input_is_rejected():
    with pytest.raises(TypeError):
        detect_regulations(None)  # type: ignore[arg-type]
