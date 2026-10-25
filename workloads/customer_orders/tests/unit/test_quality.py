from pathlib import Path

import yaml

from shared.codegen.spec_loader import load_spec


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
QUALITY_SCRIPT = ROOT / "scripts" / "quality" / "quality_check.py"


def _token_rule():
    quality = yaml.safe_load((CONFIG / "quality_rules.yaml").read_text())
    return next(
        rule
        for rule in quality["rules"]["validity"]
        if rule["rule_id"] == "validity_credit_card_token_present"
    )


def test_optional_pan_token_rule_is_source_conditional_and_critical():
    rule = _token_rule()
    params = rule["params"]

    assert rule["check_type"] == "custom_sql"
    assert rule["severity"] == "critical"
    assert rule["threshold"] == 1.0
    assert params["source_column"] == "credit_card_number"
    assert params["source_sql"] == "credit_card_number IS NOT NULL"
    assert params["sql"] == "credit_card_token IS NOT NULL"
    assert params["join_columns"] == ["order_id"]
    assert params["retain_pan"] is False
    assert params["retain_last_four"] is False


def test_quality_spec_validates_and_rendered_script_is_conditional():
    quality, _ = load_spec(CONFIG / "quality_rules.yaml", "quality")
    script = QUALITY_SCRIPT.read_text()

    assert any(
        rule["rule_id"] == "validity_credit_card_token_present"
        for rule in quality["rules"]["validity"]
    )
    assert "source_present_count = source_present_df.count()" in script
    assert "score = valid_count / source_present_count if source_present_count > 0 else 1.0" in script
    assert 'how="left_anti"' in script
    assert 'F.expr("credit_card_number IS NOT NULL")' in script
    assert 'F.expr("credit_card_token IS NOT NULL")' in script


def test_quality_script_does_not_use_unconditional_token_not_null_check():
    script = QUALITY_SCRIPT.read_text()

    assert '"ADOP_RUN_ID"' in script
    assert 'run_id="standalone"' not in script
    assert (
        'valid_count = df.filter(F.col("credit_card_token").isNotNull()).count()'
        not in script
    )
    assert '"severity": "critical"' in script
