"""Unit tests for customer_master quality rules configuration."""
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def quality_config():
    config_path = PROJECT_ROOT / "workloads" / "customer_master" / "config" / "quality.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


class TestQualityGates:
    def test_silver_gate_threshold(self, quality_config):
        gate = quality_config["quality_gates"]["bronze_to_silver"]
        assert gate["overall_score"] == 0.80
        assert gate["critical_failures"] == 0
        assert gate["action_on_failure"] == "block"

    def test_gold_gate_threshold(self, quality_config):
        gate = quality_config["quality_gates"]["silver_to_gold"]
        assert gate["overall_score"] == 0.95
        assert gate["critical_failures"] == 0
        assert gate["action_on_failure"] == "block"


class TestCompletenessRules:
    def test_critical_columns_have_full_completeness(self, quality_config):
        completeness_rules = quality_config["rules"]["completeness"]
        critical_rules = [r for r in completeness_rules if r["severity"] == "critical"]
        critical_cols = [r["column"] for r in critical_rules]
        assert "customer_id" in critical_cols
        assert "email" in critical_cols
        assert "last_name" in critical_cols
        assert "ssn" in critical_cols
        for rule in critical_rules:
            assert rule["threshold"] == 1.0


class TestValidityRules:
    def test_credit_score_range(self, quality_config):
        validity_rules = quality_config["rules"]["validity"]
        credit_rule = next(r for r in validity_rules if r["rule_id"] == "valid_credit_score_range")
        assert credit_rule["params"]["min"] == 300
        assert credit_rule["params"]["max"] == 850
        assert credit_rule["severity"] == "critical"

    def test_income_positive(self, quality_config):
        validity_rules = quality_config["rules"]["validity"]
        income_rule = next(r for r in validity_rules if r["rule_id"] == "valid_annual_income_positive")
        assert income_rule["params"]["min"] == 1

    def test_ssn_format_validated(self, quality_config):
        validity_rules = quality_config["rules"]["validity"]
        ssn_rule = next(r for r in validity_rules if r["rule_id"] == "valid_ssn_format")
        assert ssn_rule["check_type"] == "regex"
        assert ssn_rule["severity"] == "critical"

    def test_zip_code_format_validated(self, quality_config):
        validity_rules = quality_config["rules"]["validity"]
        zip_rule = next(r for r in validity_rules if r["rule_id"] == "valid_zip_code_format")
        assert zip_rule["check_type"] == "regex"
        assert zip_rule["severity"] == "critical"

    def test_email_format_validated(self, quality_config):
        validity_rules = quality_config["rules"]["validity"]
        email_rule = next(r for r in validity_rules if r["rule_id"] == "valid_email_format")
        assert email_rule["check_type"] == "regex"

    def test_date_of_birth_bounds(self, quality_config):
        validity_rules = quality_config["rules"]["validity"]
        dob_rule = next(r for r in validity_rules if r["rule_id"] == "valid_date_of_birth")
        assert dob_rule["params"]["min"] == "1920-01-01"
        assert dob_rule["params"]["max"] == "2008-01-01"

    def test_account_open_date_not_future(self, quality_config):
        validity_rules = quality_config["rules"]["validity"]
        open_rule = next(r for r in validity_rules if r["rule_id"] == "valid_account_open_date")
        assert open_rule["params"]["max"] == "today"


class TestAnomalyDetection:
    def test_anomaly_detection_enabled(self, quality_config):
        assert quality_config["anomaly_detection"]["enabled"] is True

    def test_volume_threshold(self, quality_config):
        assert quality_config["anomaly_detection"]["volume_threshold_pct"] == 20
