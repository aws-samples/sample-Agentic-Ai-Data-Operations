"""
Unit tests for customer_orders metadata validation.

Tests verify:
- Schema YAML is valid and parseable
- All columns have required metadata fields
- PII classifications are properly flagged
- GDPR compliance columns are present
- No raw data values in schema definitions
"""

import pytest
import yaml
from pathlib import Path


WORKLOAD_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = WORKLOAD_DIR / "config"


def test_source_yaml_exists():
    """Verify source.yaml file exists."""
    source_file = CONFIG_DIR / "source.yaml"
    assert source_file.exists(), "source.yaml must exist"


def test_source_yaml_valid():
    """Verify source.yaml is valid YAML."""
    source_file = CONFIG_DIR / "source.yaml"
    with open(source_file) as f:
        data = yaml.safe_load(f)
    assert data is not None, "source.yaml must be valid YAML"
    assert isinstance(data, dict), "source.yaml must be a dictionary"


def test_source_yaml_required_fields():
    """Verify source.yaml has all required fields."""
    source_file = CONFIG_DIR / "source.yaml"
    with open(source_file) as f:
        data = yaml.safe_load(f)
    
    required_fields = ["dataset_name", "version", "compliance", "source", "schema"]
    for field in required_fields:
        assert field in data, f"source.yaml must have '{field}' field"


def test_source_yaml_dataset_name():
    """Verify dataset_name is correct."""
    source_file = CONFIG_DIR / "source.yaml"
    with open(source_file) as f:
        data = yaml.safe_load(f)
    
    assert data["dataset_name"] == "customer_orders"


def test_source_yaml_compliance():
    """Verify compliance regulation is set."""
    source_file = CONFIG_DIR / "source.yaml"
    with open(source_file) as f:
        data = yaml.safe_load(f)
    
    assert data["compliance"] == "GDPR"


def test_source_yaml_columns_schema():
    """Verify all columns have required fields."""
    source_file = CONFIG_DIR / "source.yaml"
    with open(source_file) as f:
        data = yaml.safe_load(f)
    
    columns = data["schema"]["columns"]
    assert len(columns) > 0, "Schema must have at least one column"
    
    required_column_fields = ["name", "type", "role", "nullable", "phi", "sensitivity"]
    for col in columns:
        for field in required_column_fields:
            assert field in col, f"Column {col.get('name', 'unknown')} must have '{field}' field"


def test_source_yaml_primary_key_defined():
    """Verify primary key is defined."""
    source_file = CONFIG_DIR / "source.yaml"
    with open(source_file) as f:
        data = yaml.safe_load(f)
    
    columns = data["schema"]["columns"]
    pk_columns = [col for col in columns if col.get("primary_key", False)]
    
    assert len(pk_columns) > 0, "At least one column must be marked as primary_key"
    assert pk_columns[0]["name"] == "order_id"


def test_source_yaml_pii_columns_flagged():
    """Verify PII columns are properly flagged."""
    source_file = CONFIG_DIR / "source.yaml"
    with open(source_file) as f:
        data = yaml.safe_load(f)
    
    expected_pii = [
        "customer_email",
        "customer_phone",
        "credit_card_number",
        "customer_name",
        "shipping_address",
        "city",
        "state",
        "zip_code"
    ]
    
    columns = data["schema"]["columns"]
    pii_columns = [col["name"] for col in columns if col.get("phi", False)]
    
    for expected in expected_pii:
        assert expected in pii_columns, f"Column '{expected}' must be flagged as PII"


def test_source_yaml_pii_types_set():
    """Verify PII columns have phi_type defined."""
    source_file = CONFIG_DIR / "source.yaml"
    with open(source_file) as f:
        data = yaml.safe_load(f)
    
    columns = data["schema"]["columns"]
    pii_columns = [col for col in columns if col.get("phi", False)]
    
    for col in pii_columns:
        assert "phi_type" in col, f"PII column '{col['name']}' must have phi_type"
        assert col["phi_type"] in [
            "EMAIL", "PHONE", "ACCOUNT", "NAME", "ADDRESS"
        ], f"Invalid phi_type for column '{col['name']}'"


def test_source_yaml_sensitivity_levels():
    """Verify sensitivity levels are valid."""
    source_file = CONFIG_DIR / "source.yaml"
    with open(source_file) as f:
        data = yaml.safe_load(f)
    
    valid_levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    columns = data["schema"]["columns"]
    
    for col in columns:
        assert col["sensitivity"] in valid_levels, \
            f"Column '{col['name']}' has invalid sensitivity level"


def test_source_yaml_encryption_configured():
    """Verify encryption is configured for all zones."""
    source_file = CONFIG_DIR / "source.yaml"
    with open(source_file) as f:
        data = yaml.safe_load(f)
    
    assert "encryption" in data, "Encryption configuration must be present"
    
    zones = ["landing", "staging", "publish"]
    for zone in zones:
        assert zone in data["encryption"], f"Encryption for {zone} zone must be configured"
        assert "kms_key_alias" in data["encryption"][zone]
        assert data["encryption"][zone]["algorithm"] == "AES-256"
        assert data["encryption"][zone]["transport"] == "TLS_1_3"


def test_source_yaml_key_rotation_enabled():
    """Verify KMS key rotation is enabled."""
    source_file = CONFIG_DIR / "source.yaml"
    with open(source_file) as f:
        data = yaml.safe_load(f)
    
    assert data["encryption"]["key_rotation"]["enabled"] is True
    assert data["encryption"]["key_rotation"]["frequency"] == "annual"


def test_semantic_yaml_exists():
    """Verify semantic.yaml file exists."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    assert semantic_file.exists(), "semantic.yaml must exist"


def test_semantic_yaml_valid():
    """Verify semantic.yaml is valid YAML."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    with open(semantic_file) as f:
        data = yaml.safe_load(f)
    assert data is not None, "semantic.yaml must be valid YAML"
    assert isinstance(data, dict), "semantic.yaml must be a dictionary"


def test_semantic_yaml_dataset_metadata():
    """Verify dataset-level metadata is present."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    with open(semantic_file) as f:
        data = yaml.safe_load(f)
    
    assert "dataset" in data
    required_dataset_fields = ["name", "description", "domain", "owner", "grain", "compliance"]
    for field in required_dataset_fields:
        assert field in data["dataset"], f"Dataset metadata must include '{field}'"


def test_semantic_yaml_column_roles():
    """Verify columns are categorized by role."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    with open(semantic_file) as f:
        data = yaml.safe_load(f)
    
    assert "columns" in data
    required_roles = ["measures", "dimensions", "temporal", "identifiers", "pii"]
    for role in required_roles:
        assert role in data["columns"], f"Columns must include '{role}' category"


def test_semantic_yaml_measures_aggregation():
    """Verify measures have default aggregation defined."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    with open(semantic_file) as f:
        data = yaml.safe_load(f)
    
    measures = data["columns"]["measures"]
    for measure in measures:
        assert "default_aggregation" in measure, \
            f"Measure '{measure['name']}' must have default_aggregation"
        assert measure["default_aggregation"] in [
            "SUM", "AVG", "COUNT", "MIN", "MAX", "COUNT_DISTINCT"
        ]


def test_semantic_yaml_temporal_primary_flag():
    """Verify primary temporal column is flagged."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    with open(semantic_file) as f:
        data = yaml.safe_load(f)
    
    temporal = data["columns"]["temporal"]
    primary_temporal = [col for col in temporal if col.get("is_primary_temporal", False)]
    
    assert len(primary_temporal) == 1, "Exactly one temporal column must be primary"
    assert primary_temporal[0]["name"] == "order_date"


def test_semantic_yaml_pii_masking_methods():
    """Verify PII columns have masking methods defined."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    with open(semantic_file) as f:
        data = yaml.safe_load(f)
    
    pii = data["columns"]["pii"]
    valid_methods = ["hash", "mask_partial", "redact", "tokenize", "encrypt"]
    
    for col in pii:
        assert "masking" in col, f"PII column '{col['name']}' must have masking method"
        assert col["masking"] in valid_methods


def test_semantic_yaml_gdpr_compliance_columns():
    """Verify GDPR compliance columns are defined."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    with open(semantic_file) as f:
        data = yaml.safe_load(f)
    
    assert "gdpr_compliance" in data["columns"]
    gdpr_cols = data["columns"]["gdpr_compliance"]
    
    required_gdpr = [
        "data_subject_id",
        "consent_given",
        "consent_timestamp",
        "is_deleted",
        "deletion_requested_at"
    ]
    
    gdpr_col_names = [col["name"] for col in gdpr_cols]
    for expected in required_gdpr:
        assert expected in gdpr_col_names, \
            f"GDPR compliance column '{expected}' must be defined"


def test_semantic_yaml_business_terms():
    """Verify business terms are defined."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    with open(semantic_file) as f:
        data = yaml.safe_load(f)
    
    assert "business_terms" in data
    assert len(data["business_terms"]) > 0
    
    for term in data["business_terms"]:
        assert "term" in term
        assert "definition" in term
        assert "sql_expression" in term


def test_semantic_yaml_time_intelligence():
    """Verify time intelligence configuration is present."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    with open(semantic_file) as f:
        data = yaml.safe_load(f)
    
    assert "time_intelligence" in data
    ti = data["time_intelligence"]
    
    required_fields = ["fiscal_year_start", "week_starts_on", "timezone", "data_freshness"]
    for field in required_fields:
        assert field in ti, f"Time intelligence must include '{field}'"


def test_semantic_yaml_no_raw_data_values():
    """Verify no raw data values are exposed in semantic.yaml."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    with open(semantic_file) as f:
        content = f.read()
    
    # Check for patterns that might indicate raw PII
    forbidden_patterns = [
        "@gmail.com",
        "@yahoo.com",
        "555-",
        "123 Main St",
        "john.doe",
        "jane.smith"
    ]
    
    for pattern in forbidden_patterns:
        assert pattern.lower() not in content.lower(), \
            f"Raw data pattern '{pattern}' found in semantic.yaml"


def test_semantic_yaml_gdpr_metadata():
    """Verify GDPR compliance metadata section."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    with open(semantic_file) as f:
        data = yaml.safe_load(f)
    
    assert "gdpr_compliance" in data
    gdpr = data["gdpr_compliance"]
    
    required_gdpr_fields = [
        "lawful_basis",
        "data_subject_identifier",
        "retention_period_days",
        "right_to_erasure",
        "right_to_access"
    ]
    
    for field in required_gdpr_fields:
        assert field in gdpr, f"GDPR compliance must include '{field}'"


def test_semantic_yaml_encryption_zones():
    """Verify encryption configuration for all zones."""
    semantic_file = CONFIG_DIR / "semantic.yaml"
    with open(semantic_file) as f:
        data = yaml.safe_load(f)
    
    assert "encryption" in data
    assert "zones" in data["encryption"]
    
    zones = ["landing", "staging", "publish"]
    for zone in zones:
        assert zone in data["encryption"]["zones"], \
            f"Encryption configuration for {zone} zone must be present"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
