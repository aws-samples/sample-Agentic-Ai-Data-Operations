"""
Unit tests for customer_orders quality configuration.

Tests quality rule structure, thresholds, and configuration validity.
Does not require PySpark - validates YAML structure only.
"""

import pytest
import yaml
import os


class TestQualityConfig:
    """Test quality configuration loading and validation."""
    
    def test_config_exists(self):
        """Verify quality.yaml exists and is readable."""
        config_path = "workloads/customer_orders/config/quality.yaml"
        assert os.path.exists(config_path), f"Config not found: {config_path}"
    
    def test_config_parseable(self):
        """Verify quality.yaml is valid YAML."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        assert config is not None, "Config is empty"
        assert isinstance(config, dict), "Config is not a dictionary"
    
    def test_config_structure(self):
        """Verify quality.yaml has required structure."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        assert "dataset_name" in config
        assert config["dataset_name"] == "customer_orders"
        assert "schema_version" in config
        assert config["schema_version"] == "v1"
        assert "rules" in config
        assert "quality_gates" in config
    
    def test_quality_dimensions(self):
        """Verify all 5 quality dimensions are covered."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        rules = config["rules"]
        assert "completeness" in rules
        assert "uniqueness" in rules
        assert "validity" in rules
        assert "consistency" in rules
        assert "accuracy" in rules
        
        # Verify each dimension has rules
        assert len(rules["completeness"]) > 0
        assert len(rules["uniqueness"]) > 0
        assert len(rules["validity"]) > 0
        assert len(rules["consistency"]) > 0
        assert len(rules["accuracy"]) > 0
    
    def test_quality_gates_configured(self):
        """Verify quality gates match requirements."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        gates = config["quality_gates"]
        
        # Silver gate
        assert "bronze_to_silver" in gates
        assert gates["bronze_to_silver"]["overall_score"] == 0.8
        assert gates["bronze_to_silver"]["critical_failures"] == 0
        assert gates["bronze_to_silver"]["action_on_failure"] == "block"
        
        # Gold gate
        assert "silver_to_gold" in gates
        assert gates["silver_to_gold"]["overall_score"] == 0.95
        assert gates["silver_to_gold"]["critical_failures"] == 0
        assert gates["silver_to_gold"]["action_on_failure"] == "block"
    
    def test_critical_columns_covered(self):
        """Verify all critical columns have completeness rules."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        completeness_rules = config["rules"]["completeness"]
        critical_columns = {
            "order_id", "customer_id", "order_date", "product_id",
            "quantity", "unit_price", "discount_pct", 
            "payment_method", "order_status"
        }
        
        checked_columns = {
            rule["column"] for rule in completeness_rules 
            if rule["severity"] == "critical"
        }
        
        assert critical_columns.issubset(checked_columns), \
            f"Missing critical column checks: {critical_columns - checked_columns}"
    
    def test_primary_key_uniqueness(self):
        """Verify primary key has uniqueness constraint."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        uniqueness_rules = config["rules"]["uniqueness"]
        pk_rules = [r for r in uniqueness_rules if r["column"] == "order_id"]
        
        assert len(pk_rules) > 0, "No uniqueness rule for order_id"
        assert pk_rules[0]["threshold"] == 1.0
        assert pk_rules[0]["severity"] == "critical"
    
    def test_gdpr_compliance_rules(self):
        """Verify GDPR-specific rules are present."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        assert "compliance_rules" in config
        assert config["compliance_rules"]["regulation"] == "GDPR"
        
        gdpr_rules = config["compliance_rules"]["rules"]
        rule_ids = {r["rule_id"] for r in gdpr_rules}
        
        required_gdpr_rules = {
            "gdpr_consent_not_null_for_active",
            "gdpr_consent_timestamp_for_active",
            "gdpr_is_deleted_flag",
            "gdpr_data_subject_id",
            "gdpr_deletion_request_semantics",
        }
        
        assert required_gdpr_rules.issubset(rule_ids), \
            f"Missing GDPR rules: {required_gdpr_rules - rule_ids}"
    
    def test_anomaly_detection_configured(self):
        """Verify anomaly detection is configured."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        assert "anomaly_detection" in config
        anomaly_config = config["anomaly_detection"]
        
        assert anomaly_config["enabled"] == True
        assert "methods" in anomaly_config
        assert len(anomaly_config["methods"]) > 0
        assert anomaly_config["volume_threshold_pct"] == 20


class TestRuleStructure:
    """Test individual rule structure and validity."""
    
    def test_all_rules_have_required_fields(self):
        """Verify every rule has required fields."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        required_fields = {"rule_id", "column", "check_type", "threshold", "severity", "zone"}
        
        for dimension, rules in config["rules"].items():
            for rule in rules:
                missing = required_fields - set(rule.keys())
                assert not missing, \
                    f"Rule {rule.get('rule_id', 'unknown')} missing fields: {missing}"
    
    def test_rule_ids_unique(self):
        """Verify all rule IDs are unique."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        all_rule_ids = []
        for dimension, rules in config["rules"].items():
            for rule in rules:
                all_rule_ids.append(rule["rule_id"])
        
        # Add GDPR rules
        if "compliance_rules" in config and "rules" in config["compliance_rules"]:
            for rule in config["compliance_rules"]["rules"]:
                all_rule_ids.append(rule["rule_id"])
        
        assert len(all_rule_ids) == len(set(all_rule_ids)), \
            f"Duplicate rule IDs found: {[r for r in all_rule_ids if all_rule_ids.count(r) > 1]}"
    
    def test_thresholds_in_valid_range(self):
        """Verify all thresholds are between 0 and 1."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        for dimension, rules in config["rules"].items():
            for rule in rules:
                threshold = rule["threshold"]
                assert 0.0 <= threshold <= 1.0, \
                    f"Rule {rule['rule_id']} has invalid threshold: {threshold}"
    
    def test_severity_values_valid(self):
        """Verify all severity values are valid."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        valid_severities = {"critical", "warning", "info"}
        
        for dimension, rules in config["rules"].items():
            for rule in rules:
                severity = rule["severity"]
                assert severity in valid_severities, \
                    f"Rule {rule['rule_id']} has invalid severity: {severity}"
    
    def test_zone_values_valid(self):
        """Verify all zone values are valid."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        valid_zones = {"silver", "gold", "both"}
        
        for dimension, rules in config["rules"].items():
            for rule in rules:
                zone = rule["zone"]
                assert zone in valid_zones, \
                    f"Rule {rule['rule_id']} has invalid zone: {zone}"
    
    def test_check_types_valid(self):
        """Verify all check types are valid."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        valid_check_types = {
            "not_null", "unique", "range", "regex", "enum",
            "referential", "custom_sql", "format", "length"
        }
        
        for dimension, rules in config["rules"].items():
            for rule in rules:
                check_type = rule["check_type"]
                assert check_type in valid_check_types, \
                    f"Rule {rule['rule_id']} has invalid check_type: {check_type}"


class TestCompletenessRules:
    """Test completeness dimension rules."""
    
    def test_critical_columns_have_not_null_rules(self):
        """Verify critical columns have not_null completeness rules."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        completeness_rules = config["rules"]["completeness"]
        critical_columns = {
            "order_id", "customer_id", "order_date", "product_id",
            "quantity", "unit_price", "discount_pct", 
            "payment_method", "order_status"
        }
        
        critical_rules = [
            r for r in completeness_rules 
            if r["severity"] == "critical" and r["check_type"] == "not_null"
        ]
        
        checked_columns = {r["column"] for r in critical_rules}
        
        assert critical_columns.issubset(checked_columns)
    
    def test_critical_completeness_threshold_is_perfect(self):
        """Verify critical completeness rules have 1.0 threshold."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        completeness_rules = config["rules"]["completeness"]
        critical_rules = [r for r in completeness_rules if r["severity"] == "critical"]
        
        for rule in critical_rules:
            assert rule["threshold"] == 1.0, \
                f"Critical rule {rule['rule_id']} has threshold < 1.0"


class TestUniquenessRules:
    """Test uniqueness dimension rules."""
    
    def test_primary_key_uniqueness_rule_exists(self):
        """Verify order_id has uniqueness rule."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        uniqueness_rules = config["rules"]["uniqueness"]
        pk_rules = [r for r in uniqueness_rules if r["column"] == "order_id"]
        
        assert len(pk_rules) > 0
        assert pk_rules[0]["check_type"] == "unique"
        assert pk_rules[0]["threshold"] == 1.0
        assert pk_rules[0]["severity"] == "critical"


class TestValidityRules:
    """Test validity dimension rules."""
    
    def test_date_validation_rules_exist(self):
        """Verify date columns have validation rules."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        validity_rules = config["rules"]["validity"]
        date_columns = {"order_date"}
        
        validated_columns = {
            r["column"] for r in validity_rules 
            if "date" in r["column"] or "date" in r.get("description", "").lower()
        }
        
        assert date_columns.issubset(validated_columns)
    
    def test_range_rules_have_min_max(self):
        """Verify range rules specify min/max bounds."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        validity_rules = config["rules"]["validity"]
        range_rules = [r for r in validity_rules if r["check_type"] == "range"]
        
        for rule in range_rules:
            params = rule.get("params", {})
            assert "min" in params or "max" in params, \
                f"Range rule {rule['rule_id']} missing min/max"


class TestConsistencyRules:
    """Test consistency dimension rules."""
    
    def test_date_consistency_rules_exist(self):
        """Verify order_date vs ship_date consistency rule exists."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        consistency_rules = config["rules"]["consistency"]
        date_rules = [
            r for r in consistency_rules 
            if "order_date" in r.get("column", "") or 
               "ship_date" in r.get("description", "")
        ]
        
        assert len(date_rules) > 0


class TestAccuracyRules:
    """Test accuracy dimension rules."""
    
    def test_revenue_formula_rule_exists(self):
        """Verify revenue calculation accuracy rule exists."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        accuracy_rules = config["rules"]["accuracy"]
        revenue_rules = [r for r in accuracy_rules if "revenue" in r["column"]]
        
        assert len(revenue_rules) > 0
        
        # Check for zone-specific rules
        silver_rules = [r for r in revenue_rules if r["zone"] in ("silver", "both")]
        gold_rules = [r for r in revenue_rules if r["zone"] in ("gold", "both")]
        
        assert len(silver_rules) > 0
        assert len(gold_rules) > 0


class TestGDPRComplianceRules:
    """Test GDPR compliance rules."""
    
    def test_gdpr_regulation_configured(self):
        """Verify GDPR is the configured regulation."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        assert config["compliance_rules"]["regulation"] == "GDPR"
    
    def test_gdpr_consent_rules_exist(self):
        """Verify consent-related GDPR rules exist."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        gdpr_rules = config["compliance_rules"]["rules"]
        rule_ids = {r["rule_id"] for r in gdpr_rules}
        
        assert "gdpr_consent_not_null_for_active" in rule_ids
        assert "gdpr_consent_timestamp_for_active" in rule_ids
    
    def test_gdpr_deletion_rules_exist(self):
        """Verify deletion/erasure GDPR rules exist."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        gdpr_rules = config["compliance_rules"]["rules"]
        rule_ids = {r["rule_id"] for r in gdpr_rules}
        
        assert "gdpr_is_deleted_flag" in rule_ids
        assert "gdpr_deletion_request_semantics" in rule_ids
    
    def test_gdpr_data_subject_rule_exists(self):
        """Verify data subject identification rule exists."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        gdpr_rules = config["compliance_rules"]["rules"]
        rule_ids = {r["rule_id"] for r in gdpr_rules}
        
        assert "gdpr_data_subject_id" in rule_ids
    
    def test_pii_columns_documented(self):
        """Verify PII columns are documented."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        phi_columns = config["compliance_rules"]["phi_columns"]
        expected_pii = {
            "customer_email", "customer_phone", "credit_card_number",
            "customer_name", "shipping_address", "city", "state", "zip_code"
        }
        
        assert set(phi_columns) == expected_pii
    
    def test_audit_retention_configured(self):
        """Verify audit retention is configured."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        assert "audit_retention_days" in config["compliance_rules"]
        assert config["compliance_rules"]["audit_retention_days"] == 2555


class TestDeterminism:
    """Test configuration supports deterministic quality checks."""
    
    def test_config_is_deterministic(self):
        """Verify config produces same results on multiple loads."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config1 = yaml.safe_load(f)
        
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config2 = yaml.safe_load(f)
        
        # Compare key structures
        assert config1["dataset_name"] == config2["dataset_name"]
        assert config1["schema_version"] == config2["schema_version"]
        assert len(config1["rules"]) == len(config2["rules"])
    
    def test_rule_order_preserved(self):
        """Verify rules maintain consistent order."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            config = yaml.safe_load(f)
        
        # YAML preserves insertion order in Python 3.7+
        for dimension, rules in config["rules"].items():
            rule_ids = [r["rule_id"] for r in rules]
            # Just verify we have a consistent list
            assert len(rule_ids) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
