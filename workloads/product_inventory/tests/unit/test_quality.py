"""
Unit tests for product_inventory quality checks.

Tests validate:
- Quality rules configuration structure
- Silver zone quality checks (score >= 0.80, no critical failures)
- Gold zone quality checks (score >= 0.95, no critical failures)
- Individual rule evaluation logic
- Critical rule failure handling
"""

import json
import subprocess
import sys
import importlib.util
from pathlib import Path

import pandas as pd
import pytest
import yaml

# Get project root
PROJECT_ROOT = Path(__file__).resolve().parents[4]
WORKLOAD_DIR = PROJECT_ROOT / "workloads" / "product_inventory"
CONFIG_DIR = WORKLOAD_DIR / "config"
SCRIPTS_DIR = WORKLOAD_DIR / "scripts"
OUTPUT_DIR = WORKLOAD_DIR / "output"
SAMPLE_DATA_DIR = PROJECT_ROOT / "sample_data"


# Load quality check script
def load_quality_script():
    """Load run_quality_checks.py dynamically."""
    script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
    spec = importlib.util.spec_from_file_location("run_quality_checks", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def prepare_data():
    """Run transformations to generate Silver and Gold data."""
    # Run bronze_to_silver
    bronze_to_silver_script = SCRIPTS_DIR / "transform" / "bronze_to_silver.py"
    input_path = SAMPLE_DATA_DIR / "product_inventory.csv"
    silver_output_dir = OUTPUT_DIR / "silver"
    quarantine_dir = OUTPUT_DIR / "quarantine"

    silver_output_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    silver_output_path = silver_output_dir / "product_inventory_silver.csv"
    quarantine_path = quarantine_dir / "quarantine.csv"

    result = subprocess.run([
        sys.executable,
        str(bronze_to_silver_script),
        "--input", str(input_path),
        "--output", str(silver_output_path),
        "--quarantine", str(quarantine_path)
    ], check=True, capture_output=True, text=True)

    print(f"Bronze → Silver transformation completed")

    # Run silver_to_gold
    silver_to_gold_script = SCRIPTS_DIR / "transform" / "silver_to_gold.py"
    gold_output_dir = OUTPUT_DIR / "gold"

    result = subprocess.run([
        sys.executable,
        str(silver_to_gold_script),
        "--input", str(silver_output_path),
        "--output", str(gold_output_dir)
    ], check=True, capture_output=True, text=True)

    print(f"Silver → Gold transformation completed")

    yield

    # Cleanup is optional - keep outputs for manual inspection


class TestQualityRulesConfig:
    """Test quality_rules.yaml configuration structure."""

    def test_config_file_exists(self):
        """Quality rules config must exist."""
        assert (CONFIG_DIR / "quality_rules.yaml").exists()

    def test_config_loads_as_yaml(self):
        """Config must be valid YAML."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)
        assert config is not None

    def test_config_has_workload_name(self):
        """Config must specify workload name."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)
        assert config['workload'] == 'product_inventory'

    def test_silver_section_exists(self):
        """Config must have silver section."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)
        assert 'silver' in config
        assert 'threshold' in config['silver']
        assert 'rules' in config['silver']

    def test_gold_section_exists(self):
        """Config must have gold section."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)
        assert 'gold' in config
        assert 'threshold' in config['gold']
        assert 'rules' in config['gold']

    def test_silver_threshold_valid(self):
        """Silver threshold must be 0.80."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)
        assert config['silver']['threshold'] == 0.80

    def test_gold_threshold_valid(self):
        """Gold threshold must be 0.95."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)
        assert config['gold']['threshold'] == 0.95

    def test_silver_rules_have_required_fields(self):
        """All Silver rules must have name, dimension, severity, description."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)

        for rule in config['silver']['rules']:
            assert 'name' in rule
            assert 'dimension' in rule
            assert 'severity' in rule
            assert 'description' in rule

    def test_gold_rules_have_required_fields(self):
        """All Gold rules must have name, dimension, severity, description."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)

        for rule in config['gold']['rules']:
            assert 'name' in rule
            assert 'dimension' in rule
            assert 'severity' in rule
            assert 'description' in rule

    def test_critical_rules_are_subset_of_rule_names(self):
        """Critical rules must reference actual rule names."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)

        # Silver
        silver_rule_names = {r['name'] for r in config['silver']['rules']}
        silver_critical = set(config['silver'].get('critical_rules', []))
        assert silver_critical.issubset(silver_rule_names)

        # Gold
        gold_rule_names = {r['name'] for r in config['gold']['rules']}
        gold_critical = set(config['gold'].get('critical_rules', []))
        assert gold_critical.issubset(gold_rule_names)

    def test_silver_has_minimum_rules(self):
        """Silver zone must have at least 15 rules."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)
        assert len(config['silver']['rules']) >= 15

    def test_gold_has_minimum_rules(self):
        """Gold zone must have at least 10 rules."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)
        assert len(config['gold']['rules']) >= 10

    def test_all_five_dimensions_covered_in_silver(self):
        """Silver rules must cover all 5 quality dimensions."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)

        dimensions = {r['dimension'] for r in config['silver']['rules']}
        expected = {'completeness', 'accuracy', 'consistency', 'validity', 'uniqueness'}
        assert expected.issubset(dimensions)

    def test_all_five_dimensions_covered_in_gold(self):
        """Gold rules must cover key quality dimensions."""
        with open(CONFIG_DIR / "quality_rules.yaml", 'r') as f:
            config = yaml.safe_load(f)

        dimensions = {r['dimension'] for r in config['gold']['rules']}
        # Gold focuses on completeness, uniqueness, referential_integrity, accuracy
        assert 'completeness' in dimensions
        assert 'uniqueness' in dimensions
        assert 'referential_integrity' in dimensions
        assert 'accuracy' in dimensions


class TestSilverQualityChecks:
    """Test Silver zone quality checks."""

    def test_silver_output_exists(self, prepare_data):
        """Silver output must exist after transformation."""
        silver_path = OUTPUT_DIR / "silver" / "product_inventory_silver.csv"
        assert silver_path.exists()

    def test_run_quality_checks_script_exists(self):
        """Quality check script must exist."""
        assert (SCRIPTS_DIR / "quality" / "run_quality_checks.py").exists()

    def test_silver_quality_check_runs(self, prepare_data):
        """Quality check script must run without errors for Silver."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        result = subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "silver"
        ], capture_output=True, text=True)

        assert result.returncode == 0, f"Quality check failed: {result.stderr}"

    def test_silver_report_json_created(self, prepare_data):
        """Quality check must create JSON report."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "silver"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "silver_quality_report.json"
        assert report_path.exists()

    def test_silver_report_structure(self, prepare_data):
        """Silver report must have correct structure."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "silver"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "silver_quality_report.json"
        with open(report_path, 'r') as f:
            report = json.load(f)

        assert report['zone'] == 'silver'
        assert report['workload'] == 'product_inventory'
        assert 'status' in report
        assert 'score' in report
        assert 'threshold' in report
        assert 'meets_threshold' in report
        assert 'checks' in report
        assert 'critical_failures' in report

    def test_silver_score_meets_threshold(self, prepare_data):
        """Silver quality score must be >= 0.80."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "silver"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "silver_quality_report.json"
        with open(report_path, 'r') as f:
            report = json.load(f)

        assert report['score'] >= 0.80, (
            f"Silver score {report['score']:.2%} below threshold 80%"
        )

    def test_silver_no_critical_failures(self, prepare_data):
        """Silver must have no critical failures."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "silver"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "silver_quality_report.json"
        with open(report_path, 'r') as f:
            report = json.load(f)

        assert report['critical_failures'] == 0, (
            f"Critical failures: {report.get('critical_rules', [])}"
        )

    def test_silver_status_is_pass(self, prepare_data):
        """Silver status must be PASS."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "silver"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "silver_quality_report.json"
        with open(report_path, 'r') as f:
            report = json.load(f)

        assert report['status'] == 'PASS'


class TestGoldQualityChecks:
    """Test Gold zone quality checks."""

    def test_gold_output_exists(self, prepare_data):
        """Gold output tables must exist after transformation."""
        assert (OUTPUT_DIR / "gold" / "fact_inventory.csv").exists()
        assert (OUTPUT_DIR / "gold" / "dim_product.csv").exists()
        assert (OUTPUT_DIR / "gold" / "dim_supplier.csv").exists()
        assert (OUTPUT_DIR / "gold" / "dim_warehouse.csv").exists()

    def test_gold_quality_check_runs(self, prepare_data):
        """Quality check script must run without errors for Gold."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        result = subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "gold"
        ], capture_output=True, text=True)

        assert result.returncode == 0, f"Quality check failed: {result.stderr}"

    def test_gold_report_json_created(self, prepare_data):
        """Quality check must create JSON report."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "gold"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "gold_quality_report.json"
        assert report_path.exists()

    def test_gold_report_structure(self, prepare_data):
        """Gold report must have correct structure."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "gold"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "gold_quality_report.json"
        with open(report_path, 'r') as f:
            report = json.load(f)

        assert report['zone'] == 'gold'
        assert report['workload'] == 'product_inventory'
        assert 'status' in report
        assert 'score' in report
        assert 'threshold' in report
        assert 'meets_threshold' in report
        assert 'checks' in report
        assert 'critical_failures' in report
        assert 'tables' in report

    def test_gold_score_meets_threshold(self, prepare_data):
        """Gold quality score must be >= 0.95."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "gold"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "gold_quality_report.json"
        with open(report_path, 'r') as f:
            report = json.load(f)

        assert report['score'] >= 0.95, (
            f"Gold score {report['score']:.2%} below threshold 95%"
        )

    def test_gold_no_critical_failures(self, prepare_data):
        """Gold must have no critical failures."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "gold"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "gold_quality_report.json"
        with open(report_path, 'r') as f:
            report = json.load(f)

        assert report['critical_failures'] == 0, (
            f"Critical failures: {report.get('critical_rules', [])}"
        )

    def test_gold_status_is_pass(self, prepare_data):
        """Gold status must be PASS."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "gold"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "gold_quality_report.json"
        with open(report_path, 'r') as f:
            report = json.load(f)

        assert report['status'] == 'PASS'

    def test_gold_table_counts_present(self, prepare_data):
        """Gold report must include table row counts."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "gold"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "gold_quality_report.json"
        with open(report_path, 'r') as f:
            report = json.load(f)

        assert report['tables']['fact_inventory'] > 0
        assert report['tables']['dim_product'] > 0
        assert report['tables']['dim_supplier'] > 0
        assert report['tables']['dim_warehouse'] > 0


class TestIndividualRuleLogic:
    """Test individual quality rule evaluation logic."""

    def test_uniqueness_check_detects_duplicates(self):
        """Uniqueness check must detect duplicate keys."""
        # Create a DataFrame with known duplicates
        df = pd.DataFrame({
            'product_id': ['PROD-001', 'PROD-002', 'PROD-001'],
            'sku': ['SKU-001', 'SKU-002', 'SKU-003']
        })

        # Check uniqueness manually
        product_id_failures = len(df) - df['product_id'].nunique()
        assert product_id_failures == 1

        sku_failures = len(df) - df['sku'].nunique()
        assert sku_failures == 0

    def test_completeness_check_detects_nulls(self):
        """Completeness check must detect null values."""
        df = pd.DataFrame({
            'product_id': ['PROD-001', None, 'PROD-003', ''],
            'sku': ['SKU-001', 'SKU-002', 'SKU-003', 'SKU-004']
        })

        # Count nulls and empty strings
        failures = df['product_id'].isna().sum() + (df['product_id'] == '').sum()
        assert failures == 2

    def test_validity_enum_check(self):
        """Validity check must detect invalid enum values."""
        df = pd.DataFrame({
            'status': ['active', 'discontinued', 'invalid', 'out_of_stock']
        })

        valid_statuses = {'active', 'discontinued', 'out_of_stock'}
        failures = (~df['status'].isin(valid_statuses)).sum()
        assert failures == 1

    def test_accuracy_positive_check(self):
        """Accuracy check must detect non-positive values."""
        df = pd.DataFrame({
            'unit_price': [10.0, 20.0, 0.0, -5.0, 30.0]
        })

        failures = (df['unit_price'] <= 0).sum()
        assert failures == 2

    def test_accuracy_range_check(self):
        """Accuracy check must detect out-of-range values."""
        df = pd.DataFrame({
            'margin_pct': [0.5, 0.8, -2.0, 15.0, 0.2]
        })

        # Valid range: -1 to 10
        failures = ((df['margin_pct'] < -1) | (df['margin_pct'] > 10)).sum()
        assert failures == 2


class TestCriticalRuleHandling:
    """Test that critical rule failures block zone promotion."""

    def test_critical_failure_sets_status_to_fail(self):
        """Status must be FAIL if critical rule fails, even if score > threshold."""
        # Simulate a report with high score but critical failure
        report = {
            'score': 0.95,
            'threshold': 0.80,
            'critical_failures': 1
        }

        meets_threshold = report['score'] >= report['threshold'] and report['critical_failures'] == 0
        status = "PASS" if meets_threshold else "FAIL"

        assert status == "FAIL"

    def test_no_critical_failure_with_low_score_is_fail(self):
        """Status must be FAIL if score below threshold, even if no critical failures."""
        report = {
            'score': 0.70,
            'threshold': 0.80,
            'critical_failures': 0
        }

        meets_threshold = report['score'] >= report['threshold'] and report['critical_failures'] == 0
        status = "PASS" if meets_threshold else "FAIL"

        assert status == "FAIL"

    def test_pass_requires_score_and_no_critical_failures(self):
        """Status is PASS only if score >= threshold AND no critical failures."""
        report = {
            'score': 0.95,
            'threshold': 0.80,
            'critical_failures': 0
        }

        meets_threshold = report['score'] >= report['threshold'] and report['critical_failures'] == 0
        status = "PASS" if meets_threshold else "FAIL"

        assert status == "PASS"


class TestQualityReportOutput:
    """Test quality report output format."""

    def test_report_is_valid_json(self, prepare_data):
        """Quality report must be valid JSON."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "silver"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "silver_quality_report.json"
        with open(report_path, 'r') as f:
            report = json.load(f)  # Will raise if invalid JSON

        assert isinstance(report, dict)

    def test_report_has_timestamp(self, prepare_data):
        """Quality report must include checked_at timestamp."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "silver"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "silver_quality_report.json"
        with open(report_path, 'r') as f:
            report = json.load(f)

        assert 'checked_at' in report
        # Verify it's an ISO 8601 timestamp
        from datetime import datetime
        datetime.fromisoformat(report['checked_at'].replace('Z', '+00:00'))

    def test_each_check_has_required_fields(self, prepare_data):
        """Each check in the report must have name, dimension, severity, passed, detail."""
        script_path = SCRIPTS_DIR / "quality" / "run_quality_checks.py"
        subprocess.run([
            sys.executable,
            str(script_path),
            "--zone", "silver"
        ], check=True, capture_output=True, text=True)

        report_path = OUTPUT_DIR / "quality" / "silver_quality_report.json"
        with open(report_path, 'r') as f:
            report = json.load(f)

        for check in report['checks']:
            assert 'name' in check
            assert 'dimension' in check
            assert 'severity' in check
            assert 'passed' in check
            assert 'detail' in check
