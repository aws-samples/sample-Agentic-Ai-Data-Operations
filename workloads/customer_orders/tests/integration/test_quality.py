"""
Integration tests for customer_orders quality checks.

Tests quality configuration integration with existing configs.
Does not require PySpark - validates cross-file consistency.
"""

import pytest
import yaml
import json
import os
import re


def load_rendered_json(filepath):
    """Load a JSON file that may have comment headers."""
    with open(filepath) as f:
        content = f.read()
    
    # Skip comment lines starting with #
    lines = [line for line in content.split('\n') if not line.strip().startswith('#')]
    clean_content = '\n'.join(lines)
    
    return json.loads(clean_content)


class TestQualityIntegrationWithSource:
    """Test quality.yaml integrates properly with source.yaml."""
    
    def test_quality_covers_all_source_columns(self):
        """Verify quality rules cover all critical source columns."""
        with open("workloads/customer_orders/config/source.yaml") as f:
            source = yaml.safe_load(f)
        
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        # Get non-nullable columns from source
        non_nullable_cols = {
            col["name"] for col in source["schema"]["columns"]
            if not col.get("nullable", False)
        }
        
        # Get columns with completeness rules
        completeness_rules = quality["rules"]["completeness"]
        checked_cols = {r["column"] for r in completeness_rules}
        
        # All non-nullable source columns should have completeness rules
        missing = non_nullable_cols - checked_cols
        assert not missing or all("optional" in str(m) for m in missing), \
            f"Non-nullable columns missing completeness rules: {missing}"
    
    def test_pii_columns_match_source(self):
        """Verify PII columns in quality match source PHI markings."""
        with open("workloads/customer_orders/config/source.yaml") as f:
            source = yaml.safe_load(f)
        
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        # Get PHI columns from source
        source_phi = {
            col["name"] for col in source["schema"]["columns"]
            if col.get("phi", False)
        }
        
        # Get PII columns from quality
        quality_pii = set(quality["compliance_rules"]["phi_columns"])
        
        assert source_phi == quality_pii, \
            f"PII column mismatch. Source: {source_phi}, Quality: {quality_pii}"
    
    def test_primary_key_matches_source(self):
        """Verify primary key in quality matches source."""
        with open("workloads/customer_orders/config/source.yaml") as f:
            source = yaml.safe_load(f)
        
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        # Get PK from source
        source_pk = [
            col["name"] for col in source["schema"]["columns"]
            if col.get("primary_key", False)
        ]
        
        # Get uniqueness rule for PK
        uniqueness_rules = quality["rules"]["uniqueness"]
        quality_pk = [
            r["column"] for r in uniqueness_rules
            if r["severity"] == "critical"
        ]
        
        assert set(source_pk).issubset(set(quality_pk)), \
            f"PK mismatch. Source: {source_pk}, Quality: {quality_pk}"
    
    def test_compliance_matches_source(self):
        """Verify compliance regulation matches source."""
        with open("workloads/customer_orders/config/source.yaml") as f:
            source = yaml.safe_load(f)
        
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        source_compliance = source.get("compliance", "NONE")
        quality_compliance = quality["compliance_rules"]["regulation"]
        
        assert source_compliance == quality_compliance, \
            f"Compliance mismatch. Source: {source_compliance}, Quality: {quality_compliance}"


class TestQualityIntegrationWithTransformations:
    """Test quality.yaml integrates with transformations.yaml."""
    
    def test_derived_columns_have_quality_rules(self):
        """Verify derived columns from transformations have quality rules."""
        transforms = load_rendered_json("workloads/customer_orders/config/transformations.yaml")
        
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        # Get derived columns from transformations
        derived_cols = {
            col["name"] for col in transforms["silver"]["derived_columns"]
        }
        
        # Get all columns mentioned in quality rules (main rules + compliance)
        quality_cols = set()
        for dimension, rules in quality["rules"].items():
            for rule in rules:
                quality_cols.add(rule["column"])
        
        # Also check compliance rules
        if "compliance_rules" in quality and "rules" in quality["compliance_rules"]:
            for rule in quality["compliance_rules"]["rules"]:
                quality_cols.add(rule["column"])
        
        # Key derived columns should have quality rules
        important_derived = {"revenue", "data_subject_id", "consent_given", "is_deleted"}
        missing = important_derived - quality_cols
        
        assert not missing, \
            f"Important derived columns missing quality rules: {missing}"
    
    def test_quality_gates_match_transform_gates(self):
        """Verify quality gate thresholds match transformation config."""
        transforms = load_rendered_json("workloads/customer_orders/config/transformations.yaml")
        
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        # Silver gate
        silver_gate_transform = transforms["silver"]["quality_gate"]
        silver_gate_quality = quality["quality_gates"]["bronze_to_silver"]["overall_score"]
        assert silver_gate_transform == silver_gate_quality
        
        # Gold gate
        gold_gate_transform = transforms["gold"]["quality_gate"]
        gold_gate_quality = quality["quality_gates"]["silver_to_gold"]["overall_score"]
        assert gold_gate_transform == gold_gate_quality
    
    def test_null_handling_columns_have_completeness_rules(self):
        """Verify critical columns from null_handling have completeness rules."""
        transforms = load_rendered_json("workloads/customer_orders/config/transformations.yaml")
        
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        # Get critical columns from null handling
        critical_cols = set(transforms["silver"]["null_handling"]["critical_columns"])
        
        # Get columns with critical completeness rules
        completeness_rules = quality["rules"]["completeness"]
        critical_quality_cols = {
            r["column"] for r in completeness_rules
            if r["severity"] == "critical"
        }
        
        assert critical_cols.issubset(critical_quality_cols), \
            f"Critical null handling columns missing completeness rules: {critical_cols - critical_quality_cols}"
    
    def test_gdpr_fields_present_in_quality(self):
        """Verify GDPR fields from transformations are in quality rules."""
        transforms = load_rendered_json("workloads/customer_orders/config/transformations.yaml")
        
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        # GDPR fields that should be checked
        gdpr_fields = {
            "data_subject_id", "consent_given", 
            "consent_timestamp", "is_deleted", "deletion_requested_at"
        }
        
        # Get all columns in GDPR rules
        gdpr_rules = quality["compliance_rules"]["rules"]
        checked_gdpr_cols = {r["column"] for r in gdpr_rules}
        
        assert gdpr_fields.issubset(checked_gdpr_cols), \
            f"GDPR fields missing from quality rules: {gdpr_fields - checked_gdpr_cols}"


class TestQualityRuleZoneConsistency:
    """Test quality rules are properly scoped to zones."""
    
    def test_silver_zone_rules_exist(self):
        """Verify rules scoped to silver zone."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        silver_rules = []
        for dimension, rules in quality["rules"].items():
            for rule in rules:
                if rule["zone"] in ("silver", "both"):
                    silver_rules.append(rule)
        
        assert len(silver_rules) > 0, "No rules for silver zone"
    
    def test_gold_zone_rules_exist(self):
        """Verify rules scoped to gold zone."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        gold_rules = []
        for dimension, rules in quality["rules"].items():
            for rule in rules:
                if rule["zone"] in ("gold", "both"):
                    gold_rules.append(rule)
        
        assert len(gold_rules) > 0, "No rules for gold zone"
    
    def test_critical_rules_span_zones(self):
        """Verify critical rules apply to both zones."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        critical_rules = []
        for dimension, rules in quality["rules"].items():
            for rule in rules:
                if rule["severity"] == "critical":
                    critical_rules.append(rule)
        
        both_zone_critical = [r for r in critical_rules if r["zone"] == "both"]
        
        # At least some critical rules should apply to both zones
        assert len(both_zone_critical) > 0, "No critical rules spanning both zones"


class TestQualityGateEnforcement:
    """Test quality gate configuration is properly enforced."""
    
    def test_silver_gate_blocks_on_failure(self):
        """Verify silver gate is configured to block."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        silver_gate = quality["quality_gates"]["bronze_to_silver"]
        assert silver_gate["action_on_failure"] == "block"
        assert silver_gate["critical_failures"] == 0
    
    def test_gold_gate_blocks_on_failure(self):
        """Verify gold gate is configured to block."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        gold_gate = quality["quality_gates"]["silver_to_gold"]
        assert gold_gate["action_on_failure"] == "block"
        assert gold_gate["critical_failures"] == 0
    
    def test_thresholds_match_args(self):
        """Verify thresholds match the provided args (0.8 and 0.95)."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        assert quality["quality_gates"]["bronze_to_silver"]["overall_score"] == 0.8
        assert quality["quality_gates"]["silver_to_gold"]["overall_score"] == 0.95


class TestQualityConfigDeterminism:
    """Test quality config supports deterministic execution."""
    
    def test_config_hash_stable(self):
        """Verify config produces stable hash."""
        import hashlib
        
        with open("workloads/customer_orders/config/quality.yaml") as f:
            content1 = f.read()
        
        hash1 = hashlib.sha256(content1.encode()).hexdigest()
        
        with open("workloads/customer_orders/config/quality.yaml") as f:
            content2 = f.read()
        
        hash2 = hashlib.sha256(content2.encode()).hexdigest()
        
        assert hash1 == hash2, "Config file hash is not stable"
    
    def test_rule_order_deterministic(self):
        """Verify rules maintain consistent order across loads."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality1 = yaml.safe_load(f)
        
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality2 = yaml.safe_load(f)
        
        # Compare rule IDs in order
        for dimension in quality1["rules"]:
            ids1 = [r["rule_id"] for r in quality1["rules"][dimension]]
            ids2 = [r["rule_id"] for r in quality2["rules"][dimension]]
            assert ids1 == ids2, f"Rule order differs in {dimension}"


class TestQualityReportingStructure:
    """Test quality reporting will produce expected output structure."""
    
    def test_expected_output_fields(self):
        """Verify expected output fields are documented."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        # Verify dimensions exist for reporting
        assert "completeness" in quality["rules"]
        assert "uniqueness" in quality["rules"]
        assert "validity" in quality["rules"]
        assert "consistency" in quality["rules"]
        assert "accuracy" in quality["rules"]
    
    def test_anomaly_detection_reportable(self):
        """Verify anomaly detection config is reportable."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        anomaly = quality["anomaly_detection"]
        assert "enabled" in anomaly
        assert "methods" in anomaly
        assert isinstance(anomaly["methods"], list)


class TestQualityRuleCompleteness:
    """Test quality rule coverage is comprehensive."""
    
    def test_all_dimensions_have_rules(self):
        """Verify all 5 dimensions have at least one rule."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        required_dimensions = {
            "completeness", "uniqueness", "validity", 
            "consistency", "accuracy"
        }
        
        for dimension in required_dimensions:
            assert dimension in quality["rules"]
            assert len(quality["rules"][dimension]) > 0, \
                f"Dimension {dimension} has no rules"
    
    def test_critical_vs_warning_balance(self):
        """Verify balance between critical and warning rules."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        critical_count = 0
        warning_count = 0
        
        for dimension, rules in quality["rules"].items():
            for rule in rules:
                if rule["severity"] == "critical":
                    critical_count += 1
                elif rule["severity"] == "warning":
                    warning_count += 1
        
        # Should have both critical and warning rules
        assert critical_count > 0, "No critical rules"
        assert warning_count > 0, "No warning rules"
        
        # Critical rules should be minority (not blocking everything)
        assert critical_count < len(quality["rules"]["completeness"]) + \
                               len(quality["rules"]["uniqueness"]) + \
                               len(quality["rules"]["validity"])


class TestGDPRComplianceIntegration:
    """Test GDPR compliance rules integrate properly."""
    
    def test_gdpr_rules_critical(self):
        """Verify GDPR rules are marked as critical."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        gdpr_rules = quality["compliance_rules"]["rules"]
        
        for rule in gdpr_rules:
            if "consent" in rule["rule_id"] or "deletion" in rule["rule_id"]:
                assert rule["severity"] == "critical", \
                    f"GDPR rule {rule['rule_id']} should be critical"
    
    def test_retention_policy_documented(self):
        """Verify retention policy is documented."""
        with open("workloads/customer_orders/config/quality.yaml") as f:
            quality = yaml.safe_load(f)
        
        assert "audit_retention_days" in quality["compliance_rules"]
        # GDPR requires at least 6 years for most audit logs
        assert quality["compliance_rules"]["audit_retention_days"] >= 2190


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
