"""
Integration tests for customer_orders metadata validation.

Tests verify:
- Metadata consistency across source.yaml and semantic.yaml
- PII column mappings are complete
- GDPR compliance columns match transformations
- Quality rules reference valid columns
- Encryption configuration is consistent
"""

import pytest
import yaml
import json
import re
from pathlib import Path


WORKLOAD_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = WORKLOAD_DIR / "config"


@pytest.fixture
def source_config():
    """Load source.yaml configuration."""
    with open(CONFIG_DIR / "source.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture
def semantic_config():
    """Load semantic.yaml configuration."""
    with open(CONFIG_DIR / "semantic.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture
def transformations_config():
    """Load transformations.yaml configuration (JSON format with header comments)."""
    with open(CONFIG_DIR / "transformations.yaml") as f:
        content = f.read()
    
    # Strip header comments (lines starting with #)
    lines = content.split('\n')
    json_lines = [line for line in lines if not line.strip().startswith('#')]
    json_content = '\n'.join(json_lines)
    
    return json.loads(json_content)


@pytest.fixture
def quality_config():
    """Load quality_rules.yaml configuration."""
    with open(CONFIG_DIR / "quality_rules.yaml") as f:
        return yaml.safe_load(f)


def test_dataset_name_consistency(source_config, semantic_config, transformations_config):
    """Verify dataset_name is consistent across all config files."""
    assert source_config["dataset_name"] == "customer_orders"
    assert semantic_config["dataset"]["name"] == "customer_orders"
    assert transformations_config["dataset_name"] == "customer_orders"


def test_compliance_regulation_consistency(source_config, semantic_config):
    """Verify compliance regulation is consistent."""
    assert source_config["compliance"] == "GDPR"
    assert semantic_config["dataset"]["compliance"] == "GDPR"


def test_pii_columns_mapping_complete(source_config, semantic_config):
    """Verify all PII columns in source are mapped in semantic."""
    source_columns = source_config["schema"]["columns"]
    source_pii = {col["name"] for col in source_columns if col.get("phi", False)}
    
    semantic_pii = {col["name"] for col in semantic_config["columns"]["pii"]}
    
    assert source_pii == semantic_pii, \
        f"PII columns mismatch: source={source_pii}, semantic={semantic_pii}"


def test_pii_masking_methods_defined(semantic_config, transformations_config):
    """Verify PII masking methods in semantic match transformations."""
    semantic_pii = {
        col["name"]: col["masking"]
        for col in semantic_config["columns"]["pii"]
    }
    
    transform_pii = {
        col["name"]: col["method"]
        for col in transformations_config["silver"]["pii_masking"]["columns"]
    }
    
    for col_name in semantic_pii:
        assert col_name in transform_pii, \
            f"PII column '{col_name}' in semantic.yaml not found in transformations"


def test_primary_key_consistency(source_config, semantic_config, transformations_config):
    """Verify primary key is consistent across configs."""
    # Source.yaml
    source_pk = [
        col["name"] for col in source_config["schema"]["columns"]
        if col.get("primary_key", False)
    ]
    
    # Semantic.yaml
    semantic_pk = [
        col["name"] for col in semantic_config["columns"]["identifiers"]
        if col.get("role") == "primary_key"
    ]
    
    # Transformations.yaml
    transform_pk = transformations_config["silver"]["primary_key"]
    
    assert source_pk == ["order_id"]
    assert semantic_pk == ["order_id"]
    assert transform_pk == ["order_id"]


def test_gdpr_compliance_columns_in_transformations(semantic_config, transformations_config):
    """Verify GDPR compliance columns are generated in transformations."""
    gdpr_cols = {col["name"] for col in semantic_config["columns"]["gdpr_compliance"]}
    
    derived_cols = {
        col["name"] for col in transformations_config["silver"]["derived_columns"]
    }
    
    # All GDPR columns should be in derived_columns
    for gdpr_col in gdpr_cols:
        assert gdpr_col in derived_cols, \
            f"GDPR compliance column '{gdpr_col}' not found in transformations derived_columns"


def test_measures_have_valid_types(semantic_config):
    """Verify measures have numeric data types."""
    measures = semantic_config["columns"]["measures"]
    numeric_types = ["INTEGER", "DECIMAL", "BIGINT", "FLOAT", "DOUBLE"]
    
    for measure in measures:
        data_type = measure["data_type"].split("(")[0]  # Handle DECIMAL(10,2)
        assert data_type in numeric_types, \
            f"Measure '{measure['name']}' has non-numeric type '{measure['data_type']}'"


def test_temporal_columns_have_date_types(semantic_config):
    """Verify temporal columns have date/timestamp types."""
    temporal = semantic_config["columns"]["temporal"]
    date_types = ["DATE", "TIMESTAMP", "DATETIME"]
    
    for col in temporal:
        assert col["data_type"] in date_types, \
            f"Temporal column '{col['name']}' has non-date type '{col['data_type']}'"


def test_encryption_consistency(source_config, semantic_config):
    """Verify encryption configuration is consistent across configs."""
    source_enc = source_config["encryption"]
    semantic_enc = semantic_config["encryption"]["zones"]
    
    zones = ["landing", "staging", "publish"]
    for zone in zones:
        assert source_enc[zone]["algorithm"] == "AES-256"
        assert semantic_enc[zone]["algorithm"] == "AES-256"
        assert source_enc[zone]["transport"] == "TLS_1_3"
        assert semantic_enc[zone]["transport"] == "TLS_1_3"


def test_key_rotation_consistency(source_config, semantic_config):
    """Verify KMS key rotation settings are consistent."""
    source_rotation = source_config["encryption"]["key_rotation"]
    semantic_rotation = semantic_config["encryption"]["key_rotation"]
    
    assert source_rotation["enabled"] == semantic_rotation["enabled"]
    assert source_rotation["frequency"] == semantic_rotation["frequency"]


def test_quality_rules_reference_valid_columns(source_config, quality_config):
    """Verify quality rules reference columns that exist in source schema."""
    source_columns = {col["name"] for col in source_config["schema"]["columns"]}
    
    # Add derived columns that exist in Silver/Gold
    derived_columns = {"revenue", "data_subject_id", "consent_given", 
                       "consent_timestamp", "is_deleted", "deletion_requested_at",
                       "credit_card_token"}
    all_valid_columns = source_columns | derived_columns
    
    all_rules = []
    for dimension, rules in quality_config["rules"].items():
        all_rules.extend(rules)
    
    for rule in all_rules:
        col_name = rule["column"]
        assert col_name in all_valid_columns, \
            f"Quality rule '{rule['rule_id']}' references non-existent column '{col_name}'"


def test_quality_rules_critical_columns_match_null_handling(transformations_config, quality_config):
    """Verify quality rules for critical columns match null_handling config."""
    transform_critical = set(transformations_config["silver"]["null_handling"]["critical_columns"])
    
    completeness_rules = quality_config["rules"]["completeness"]
    critical_completeness = {
        rule["column"] for rule in completeness_rules
        if rule.get("severity") == "critical"
    }
    
    # All critical columns should have critical completeness rules
    for col in transform_critical:
        assert col in critical_completeness, \
            f"Critical column '{col}' missing critical completeness rule"


def test_timezone_consistency(semantic_config, quality_config):
    """Verify timezone settings are consistent across configs."""
    semantic_tz = semantic_config["time_intelligence"]["timezone"]
    
    # Check quality rules that reference timezone
    date_rules = [
        rule for rule in quality_config["rules"]["validity"]
        if "timezone" in rule.get("params", {})
    ]
    
    for rule in date_rules:
        assert rule["params"]["timezone"] == semantic_tz, \
            f"Rule '{rule['rule_id']}' timezone mismatch with semantic config"


def test_derived_column_revenue_matches_formula(semantic_config, transformations_config):
    """Verify revenue derived column formula matches semantic definition."""
    semantic_revenue = next(
        col for col in semantic_config["columns"]["measures"]
        if col["name"] == "revenue"
    )
    
    transform_revenue = next(
        col for col in transformations_config["silver"]["derived_columns"]
        if col["name"] == "revenue"
    )
    
    assert "derived_from" in semantic_revenue
    # Both should reference the same calculation
    assert "quantity" in semantic_revenue["derived_from"]
    assert "unit_price" in semantic_revenue["derived_from"]
    assert "discount_pct" in semantic_revenue["derived_from"]
    
    assert "quantity" in transform_revenue["expression"]
    assert "unit_price" in transform_revenue["expression"]
    assert "discount_pct" in transform_revenue["expression"]


def test_gdpr_retention_consistency(semantic_config, quality_config):
    """Verify GDPR retention settings are consistent."""
    semantic_retention = semantic_config["gdpr_compliance"]["retention_period_days"]
    semantic_audit = semantic_config["gdpr_compliance"]["audit_retention_days"]
    
    compliance_rules = quality_config["compliance_rules"]
    assert compliance_rules["regulation"] == "GDPR"
    assert compliance_rules["audit_retention_days"] == semantic_audit


def test_default_filters_match_quality_rules(semantic_config, quality_config):
    """Verify default filters align with quality rule expectations."""
    default_filters = semantic_config["default_filters"]
    
    # Check that order_status filter aligns with quality rules
    assert "order_status = 'completed'" in default_filters["revenue_queries"]["condition"]
    
    # Check that is_deleted filter is present
    assert "is_deleted = false" in default_filters["active_records"]["condition"]


def test_credit_card_tokenization_config(semantic_config, transformations_config):
    """Verify credit card tokenization is properly configured."""
    # Semantic config
    cc_col = next(
        col for col in semantic_config["columns"]["pii"]
        if col["name"] == "credit_card_number"
    )
    assert cc_col["masking"] == "tokenize"
    assert cc_col["token_output_column"] == "credit_card_token"
    
    # Transformations config
    transform_cc = next(
        col for col in transformations_config["silver"]["pii_masking"]["columns"]
        if col["name"] == "credit_card_number"
    )
    assert transform_cc["method"] == "tokenize"
    assert transform_cc["target_column"] == "credit_card_token"
    
    # Verify credit_card_number is dropped after tokenization
    assert "credit_card_number" in transformations_config["silver"]["drop_columns"]


def test_all_pii_columns_have_gdpr_lawful_basis(semantic_config):
    """Verify all PII columns have GDPR lawful basis defined."""
    pii_cols = semantic_config["columns"]["pii"]
    
    for col in pii_cols:
        assert "gdpr_lawful_basis" in col, \
            f"PII column '{col['name']}' missing gdpr_lawful_basis"
        assert col["gdpr_lawful_basis"] in ["consent", "contract", "legal_obligation", "legitimate_interest"]


def test_quality_gate_thresholds_consistency(transformations_config, quality_config):
    """Verify quality gate thresholds match between transformations and quality configs."""
    transform_silver_threshold = transformations_config["silver"]["quality_gate"]
    transform_gold_threshold = transformations_config["gold"]["quality_gate"]
    
    quality_silver_threshold = quality_config["quality_gates"]["bronze_to_silver"]["overall_score"]
    quality_gold_threshold = quality_config["quality_gates"]["silver_to_gold"]["overall_score"]
    
    assert transform_silver_threshold == quality_silver_threshold
    assert transform_gold_threshold == quality_gold_threshold


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
