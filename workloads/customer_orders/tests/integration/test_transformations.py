"""
Integration tests for customer_orders transformation artifacts.

Validates that all generated specs, scripts, and configs are internally consistent.
"""

import re
from pathlib import Path

import yaml

from shared.codegen.spec_loader import load_spec


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
SPECS = ROOT / "specs"
SCRIPTS = ROOT / "scripts" / "transform"
SQL = ROOT / "sql"


def test_specs_basic_consistency():
    """Test that silver and gold specs are consistent."""
    # Load specs from the specs/ directory
    silver_spec = yaml.safe_load((SPECS / "silver_spec.json").read_text())
    gold_spec = yaml.safe_load((SPECS / "gold_spec.json").read_text())
    source = yaml.safe_load((CONFIG / "source.yaml").read_text())
    semantic = yaml.safe_load((CONFIG / "semantic.yaml").read_text())
    quality = yaml.safe_load((CONFIG / "quality_rules.yaml").read_text())
    
    # Dataset names should match
    assert source["dataset_name"] == silver_spec["dataset_name"] == gold_spec["dataset_name"]
    assert semantic["dataset"]["name"] == source["dataset_name"]
    
    # Quality thresholds should match
    assert quality["quality_gates"]["bronze_to_silver"]["overall_score"] == 0.8
    assert quality["quality_gates"]["silver_to_gold"]["overall_score"] == 0.95
    assert silver_spec["quality_threshold"] == 0.8
    assert gold_spec["quality_threshold"] == 0.95


def test_silver_script_has_required_elements():
    """Test that the Silver transformation script contains required elements."""
    silver_script = (SCRIPTS / "landing_to_staging.py").read_text()
    
    # Should reference primary key
    assert "order_id" in silver_script
    
    # Should handle PII masking
    assert "customer_email" in silver_script or "pii" in silver_script.lower()
    
    # Should reference Silver table
    assert "silver_customer_orders" in silver_script
    
    # Should reference database
    assert "customer_orders_db" in silver_script


def test_gold_script_has_required_elements():
    """Test that the Gold transformation script contains required elements."""
    gold_script = (SCRIPTS / "staging_to_publish.py").read_text()
    
    # Should read from Silver
    assert "silver_customer_orders" in gold_script
    
    # Should write to Gold
    assert "gold_customer_orders" in gold_script
    
    # Should reference GDPR compliance fields
    for field in ["data_subject_id", "consent_given", "is_deleted"]:
        assert field in gold_script


def test_pii_not_in_gold_script():
    """Test that PII columns are not referenced in Gold script."""
    gold_script = (SCRIPTS / "staging_to_publish.py").read_text()
    
    # Raw PII should NOT appear in Gold
    pii_columns = [
        "customer_email",
        "customer_phone", 
        "customer_name",
        "shipping_address",
        "city",
        "state",
        "zip_code",
        "credit_card_number",
        "credit_card_token"  # Token also not needed in Gold for this workload
    ]
    
    for col in pii_columns:
        assert col not in gold_script


def test_generated_scripts_have_provenance_headers():
    """Test that generated scripts have the required 5-line provenance header."""
    scripts = [
        SCRIPTS / "landing_to_staging.py",
        SCRIPTS / "staging_to_publish.py",
    ]
    
    for script_path in scripts:
        lines = script_path.read_text().splitlines()[:5]
        assert len(lines) == 5, f"{script_path.name} missing 5-line header"
        assert "spec_hash:" in lines[0], f"{script_path.name} line 1 missing spec_hash"
        assert "template_id:" in lines[1], f"{script_path.name} line 2 missing template_id"
        assert "template_hash:" in lines[2], f"{script_path.name} line 3 missing template_hash"
        assert "schema_version:" in lines[3], f"{script_path.name} line 4 missing schema_version"
        assert "rendered_at:" in lines[4], f"{script_path.name} line 5 missing rendered_at"


def test_no_hardcoded_infrastructure_in_scripts():
    """Test that scripts don't contain hardcoded account IDs, regions, or ARNs."""
    scripts = [
        SCRIPTS / "landing_to_staging.py",
        SCRIPTS / "staging_to_publish.py",
    ]
    
    for script_path in scripts:
        content = script_path.read_text()
        
        # Should NOT have hardcoded ARNs
        assert not re.search(r"arn:aws:[^'\"$\s]+", content), f"{script_path.name} has hardcoded ARN"
        
        # Should NOT have hardcoded account IDs (except in precision/scale, which are OK)
        # 12-digit numbers that aren't part of DECIMAL specifications
        account_pattern = r'\b\d{12}\b(?![\,\)])'  # Not followed by comma or paren
        matches = re.findall(account_pattern, content)
        if matches:
            # Check if they're in DECIMAL context
            for match in matches:
                context = content[max(0, content.find(match)-20):content.find(match)+30]
                assert "DECIMAL" in context or "precision" in context.lower(), \
                    f"{script_path.name} may have hardcoded account ID: {match}"


def test_specs_reference_correct_tables():
    """Test that specs reference the correct source and target tables."""
    silver_spec = yaml.safe_load((SPECS / "silver_spec.json").read_text())
    gold_spec = yaml.safe_load((SPECS / "gold_spec.json").read_text())
    
    # Silver should read from Bronze
    assert "bronze_customer_orders" in silver_spec["source_table"]
    
    # Silver should write to Silver
    assert silver_spec["iceberg_table"] == "silver_customer_orders"
    assert silver_spec["iceberg_database"] == "customer_orders_db"
    
    # Gold should read from Silver
    assert "silver_customer_orders" in gold_spec["source_table"]
    
    # Gold should write to Gold
    assert gold_spec["iceberg_table"] == "gold_customer_orders"
    assert gold_spec["iceberg_database"] == "customer_orders_db"


def test_dedup_strategy_consistency():
    """Test that dedup_strategy='none' is consistently applied."""
    silver_spec = yaml.safe_load((SPECS / "silver_spec.json").read_text())
    
    # Should have dedup_strategy='none' as specified
    assert silver_spec["dedup_strategy"] == "none"
    
    # Should NOT have dedup_order_by since strategy is 'none'
    assert "dedup_order_by" not in silver_spec or silver_spec.get("dedup_order_by") is None


def test_gdpr_compliance_fields_in_specs():
    """Test that GDPR compliance fields are present in transformation specs."""
    silver_spec = yaml.safe_load((SPECS / "silver_spec.json").read_text())
    
    # Silver should add GDPR fields
    gdpr_fields = ["data_subject_id", "consent_given", "consent_timestamp", "is_deleted", "deletion_requested_at"]
    derived_columns = [col["name"] for col in silver_spec["derived_columns"]]
    
    for field in gdpr_fields:
        assert field in derived_columns, f"GDPR field {field} not in Silver derived_columns"


def test_pii_masking_configuration():
    """Test that PII masking is properly configured in silver_spec."""
    silver_spec = yaml.safe_load((SPECS / "silver_spec.json").read_text())
    
    # PII masking should be enabled
    assert silver_spec["pii_masking"]["enabled"] is True
    
    # Should have masking for all PII columns
    masked_columns = {col["name"] for col in silver_spec["pii_masking"]["columns"]}
    expected_pii = {
        "customer_email", "customer_phone", "credit_card_number",
        "customer_name", "shipping_address", "city", "state", "zip_code"
    }
    
    assert masked_columns == expected_pii


def test_quarantine_configuration():
    """Test that quarantine is properly configured."""
    silver_spec = yaml.safe_load((SPECS / "silver_spec.json").read_text())
    
    # Quarantine should be enabled
    assert silver_spec["quarantine"]["enabled"] is True
    
    # Should reference environment variable
    assert "CUSTOMER_ORDERS_QUARANTINE_URI" in silver_spec["quarantine"]["location"]
    
    # Should have retention policy
    assert silver_spec["quarantine"]["retention_days"] == 365
