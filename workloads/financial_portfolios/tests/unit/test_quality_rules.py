"""
Unit tests for financial_portfolios quality rules
Tests YAML structure, rule definitions, and configuration validity
"""

import pytest
import yaml
from pathlib import Path


@pytest.fixture
def quality_rules():
    """Load quality rules YAML"""
    rules_path = Path(__file__).parent.parent.parent / "config" / "quality_rules.yaml"
    with open(rules_path) as f:
        return yaml.safe_load(f)


class TestQualityRulesStructure:
    """Test YAML structure and required fields"""

    def test_yaml_is_valid(self, quality_rules):
        """quality_rules.yaml is valid YAML"""
        assert quality_rules is not None
        assert isinstance(quality_rules, dict)

    def test_has_required_top_level_fields(self, quality_rules):
        """Has workload, version, compliance, retention_years"""
        assert quality_rules['workload'] == 'financial_portfolios'
        assert 'version' in quality_rules
        assert 'compliance' in quality_rules
        assert 'retention_years' in quality_rules

    def test_sox_compliance_tag(self, quality_rules):
        """SOX compliance tag is present"""
        assert 'SOX' in quality_rules['compliance']

    def test_retention_policy(self, quality_rules):
        """Retention policy is 7 years for SOX"""
        assert quality_rules['retention_years'] == 7

    def test_has_quality_thresholds(self, quality_rules):
        """Quality thresholds are defined"""
        thresholds = quality_rules['quality_thresholds']
        assert 'completeness' in thresholds
        assert 'uniqueness' in thresholds
        assert 'validity' in thresholds
        assert 'consistency' in thresholds
        assert 'overall_score' in thresholds
        assert 'critical_score' in thresholds


class TestTableDefinitions:
    """Test all 3 tables are properly defined"""

    def test_all_tables_defined(self, quality_rules):
        """stocks, portfolios, positions tables are defined"""
        tables = quality_rules['tables']
        assert 'stocks' in tables
        assert 'portfolios' in tables
        assert 'positions' in tables

    def test_all_tables_have_primary_key(self, quality_rules):
        """Each table has a primary_key defined"""
        for table_name, table_def in quality_rules['tables'].items():
            assert 'primary_key' in table_def, f"{table_name} missing primary_key"

    def test_primary_keys_are_correct(self, quality_rules):
        """Primary keys match expected columns"""
        tables = quality_rules['tables']
        assert tables['stocks']['primary_key'] == 'ticker'
        assert tables['portfolios']['primary_key'] == 'portfolio_id'
        assert tables['positions']['primary_key'] == 'position_id'


class TestQualityDimensions:
    """Test all 5 quality dimensions are covered"""

    def test_completeness_rules_exist(self, quality_rules):
        """All tables have completeness rules"""
        for table_name, table_def in quality_rules['tables'].items():
            assert 'completeness_rules' in table_def, f"{table_name} missing completeness_rules"
            assert len(table_def['completeness_rules']) > 0

    def test_uniqueness_rules_exist(self, quality_rules):
        """All tables have uniqueness rules"""
        for table_name, table_def in quality_rules['tables'].items():
            assert 'uniqueness_rules' in table_def, f"{table_name} missing uniqueness_rules"
            assert len(table_def['uniqueness_rules']) > 0

    def test_validity_rules_exist(self, quality_rules):
        """All tables have validity rules"""
        for table_name, table_def in quality_rules['tables'].items():
            assert 'validity_rules' in table_def, f"{table_name} missing validity_rules"
            assert len(table_def['validity_rules']) > 0

    def test_anomaly_detection_exists(self, quality_rules):
        """All tables have anomaly detection rules"""
        for table_name, table_def in quality_rules['tables'].items():
            assert 'anomaly_detection' in table_def, f"{table_name} missing anomaly_detection"
            assert len(table_def['anomaly_detection']) > 0

    def test_consistency_rules_exist_for_complex_tables(self, quality_rules):
        """portfolios and positions have consistency rules"""
        assert 'consistency_rules' in quality_rules['tables']['portfolios']
        assert 'consistency_rules' in quality_rules['tables']['positions']


class TestCriticalRules:
    """Test critical rules for quarantine scenarios"""

    def test_positions_has_foreign_keys(self, quality_rules):
        """positions table has FK integrity rules"""
        positions = quality_rules['tables']['positions']
        assert 'foreign_keys' in positions
        fks = positions['foreign_keys']
        assert len(fks) == 2  # portfolio_id and ticker

        # Check both FKs are present
        fk_columns = [fk['column'] for fk in fks]
        assert 'portfolio_id' in fk_columns
        assert 'ticker' in fk_columns

    def test_foreign_keys_are_critical(self, quality_rules):
        """FK violations are critical and trigger quarantine"""
        positions = quality_rules['tables']['positions']
        for fk in positions['foreign_keys']:
            assert fk['severity'] == 'critical'
            assert fk['action'] == 'quarantine'

    def test_missing_ticker_rule(self, quality_rules):
        """Missing ticker in positions is critical"""
        positions = quality_rules['tables']['positions']
        completeness_rules = positions['completeness_rules']

        ticker_rule = None
        for rule in completeness_rules:
            if 'ticker' in rule['columns']:
                ticker_rule = rule
                break

        assert ticker_rule is not None
        assert ticker_rule['severity'] == 'critical'
        assert ticker_rule['action'] == 'quarantine'

    def test_negative_shares_rule(self, quality_rules):
        """Negative shares trigger quarantine"""
        positions = quality_rules['tables']['positions']
        validity_rules = positions['validity_rules']

        shares_rule = None
        for rule in validity_rules:
            if rule['column'] == 'shares':
                shares_rule = rule
                break

        assert shares_rule is not None
        assert shares_rule['rule'] == 'greater_than'
        assert shares_rule['value'] == 0
        assert shares_rule['severity'] == 'critical'
        assert shares_rule['action'] == 'quarantine'

    def test_duplicate_pk_rejection(self, quality_rules):
        """Duplicate PKs trigger rejection"""
        for table_name, table_def in quality_rules['tables'].items():
            uniqueness_rules = table_def['uniqueness_rules']
            pk_rule = uniqueness_rules[0]
            assert pk_rule['severity'] == 'critical'
            assert pk_rule['action'] in ['reject', 'quarantine']


class TestThresholdValues:
    """Test threshold values are reasonable"""

    def test_thresholds_are_in_valid_range(self, quality_rules):
        """All thresholds are between 0 and 1"""
        thresholds = quality_rules['quality_thresholds']
        for key, value in thresholds.items():
            assert 0 <= value <= 1, f"{key} threshold {value} is out of range [0, 1]"

    def test_completeness_threshold_is_high(self, quality_rules):
        """Completeness threshold is >= 95%"""
        assert quality_rules['quality_thresholds']['completeness'] >= 0.95

    def test_uniqueness_threshold_is_perfect(self, quality_rules):
        """Uniqueness threshold is 100%"""
        assert quality_rules['quality_thresholds']['uniqueness'] == 1.0

    def test_consistency_threshold_is_perfect(self, quality_rules):
        """Consistency threshold is 100% (FKs must match)"""
        assert quality_rules['quality_thresholds']['consistency'] == 1.0


class TestAnomalyDetection:
    """Test anomaly detection configuration"""

    def test_anomaly_methods_are_valid(self, quality_rules):
        """Anomaly detection methods are z_score or interquartile_range"""
        valid_methods = ['z_score', 'interquartile_range']

        for table_name, table_def in quality_rules['tables'].items():
            for rule in table_def.get('anomaly_detection', []):
                assert rule['method'] in valid_methods, \
                    f"Invalid anomaly method {rule['method']} in {table_name}"

    def test_z_score_threshold_is_reasonable(self, quality_rules):
        """Z-score thresholds are typically 3.0"""
        for table_name, table_def in quality_rules['tables'].items():
            for rule in table_def.get('anomaly_detection', []):
                if rule['method'] == 'z_score':
                    assert 2.0 <= rule['threshold'] <= 4.0, \
                        f"Z-score threshold {rule['threshold']} is unusual"


class TestAlerts:
    """Test alert configuration"""

    def test_alerts_defined(self, quality_rules):
        """Alert configuration exists"""
        assert 'alerts' in quality_rules
        alerts = quality_rules['alerts']
        assert 'critical_failure' in alerts
        assert 'warning' in alerts
        assert 'sox_audit' in alerts

    def test_sox_audit_alerts_to_compliance(self, quality_rules):
        """SOX audit alerts go to compliance team"""
        sox_alert = quality_rules['alerts']['sox_audit']
        assert 'compliance@company.com' in sox_alert['recipients']


class TestQuarantine:
    """Test quarantine configuration"""

    def test_quarantine_enabled(self, quality_rules):
        """Quarantine is enabled"""
        assert 'quarantine' in quality_rules
        assert quality_rules['quarantine']['enabled'] is True

    def test_quarantine_retention(self, quality_rules):
        """Quarantine has retention policy"""
        quarantine = quality_rules['quarantine']
        assert 'retention_days' in quarantine
        assert quarantine['retention_days'] > 0


class TestRuleReasons:
    """Test that critical rules have reasons"""

    def test_critical_rules_have_reasons(self, quality_rules):
        """All critical rules should have a reason field"""
        for table_name, table_def in quality_rules['tables'].items():
            # Check completeness rules
            for rule in table_def.get('completeness_rules', []):
                if rule['severity'] == 'critical':
                    assert 'reason' in rule, \
                        f"{table_name} completeness rule missing reason"

            # Check uniqueness rules
            for rule in table_def.get('uniqueness_rules', []):
                if rule['severity'] == 'critical':
                    assert 'reason' in rule, \
                        f"{table_name} uniqueness rule missing reason"

            # Check validity rules
            for rule in table_def.get('validity_rules', []):
                if rule['severity'] == 'critical':
                    assert 'reason' in rule, \
                        f"{table_name} validity rule missing reason"

            # Check FK rules
            for rule in table_def.get('foreign_keys', []):
                if rule['severity'] == 'critical':
                    assert 'reason' in rule, \
                        f"{table_name} FK rule missing reason"
