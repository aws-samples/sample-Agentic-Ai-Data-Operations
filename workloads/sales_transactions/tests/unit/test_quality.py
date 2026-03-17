"""
Unit tests for sales_transactions quality rules and score calculation.

Validates that quality_rules.yaml is well-formed, covers all five quality
dimensions, marks critical rules appropriately, references only columns that
exist in semantic.yaml, and that score calculation logic is correct.
"""

import os
import sys
import unittest

import yaml


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
QUALITY_RULES_PATH = os.path.join(CONFIG_DIR, "quality_rules.yaml")
SEMANTIC_YAML_PATH = os.path.join(CONFIG_DIR, "semantic.yaml")

# Add scripts to path so we can import the runner
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts", "quality")
sys.path.insert(0, SCRIPTS_DIR)

import run_quality_checks as runner  # noqa: E402

EXPECTED_DIMENSIONS = {"completeness", "accuracy", "consistency", "validity", "uniqueness"}


class TestQualityRulesYaml(unittest.TestCase):
    """Tests for config/quality_rules.yaml structure."""

    @classmethod
    def setUpClass(cls):
        with open(QUALITY_RULES_PATH, "r") as f:
            cls.config = yaml.safe_load(f)

    def test_quality_rules_file_exists(self):
        """quality_rules.yaml must exist on disk."""
        self.assertTrue(
            os.path.isfile(QUALITY_RULES_PATH),
            f"quality_rules.yaml not found at {QUALITY_RULES_PATH}",
        )

    def test_quality_rules_is_valid_yaml(self):
        """quality_rules.yaml must parse without errors."""
        self.assertIsInstance(self.config, dict)

    def test_has_quality_rules_section(self):
        """Top-level 'quality_rules' key must be present."""
        self.assertIn("quality_rules", self.config)

    def test_has_dimensions_section(self):
        """quality_rules must contain a 'dimensions' mapping."""
        self.assertIn("dimensions", self.config["quality_rules"])

    def test_all_five_dimensions_present(self):
        """All 5 quality dimensions must be present."""
        dimensions = set(self.config["quality_rules"]["dimensions"].keys())
        self.assertEqual(
            dimensions,
            EXPECTED_DIMENSIONS,
            f"Expected {EXPECTED_DIMENSIONS}, got {dimensions}",
        )

    def test_every_dimension_has_at_least_one_rule(self):
        """Each dimension must contain at least one rule."""
        for dim_name, rules in self.config["quality_rules"]["dimensions"].items():
            self.assertIsInstance(rules, list, f"Dimension '{dim_name}' rules is not a list")
            self.assertGreater(
                len(rules), 0, f"Dimension '{dim_name}' has no rules"
            )

    def test_every_rule_has_required_fields(self):
        """Every rule must have rule_id, name, description, check, severity."""
        for dim_name, rules in self.config["quality_rules"]["dimensions"].items():
            for rule in rules:
                for field in ("rule_id", "name", "description", "check", "severity"):
                    self.assertIn(
                        field,
                        rule,
                        f"Rule in '{dim_name}' missing field '{field}': {rule}",
                    )

    def test_severity_values_valid(self):
        """Every rule's severity must be 'critical' or 'warning'."""
        for dim_name, rules in self.config["quality_rules"]["dimensions"].items():
            for rule in rules:
                self.assertIn(
                    rule["severity"],
                    ("critical", "warning"),
                    f"Rule {rule.get('rule_id')} has invalid severity: {rule['severity']}",
                )

    def test_critical_rules_exist(self):
        """At least one critical rule must be defined."""
        critical_count = 0
        for rules in self.config["quality_rules"]["dimensions"].values():
            for rule in rules:
                if rule["severity"] == "critical":
                    critical_count += 1
        self.assertGreater(
            critical_count, 0, "No critical rules found in quality_rules.yaml"
        )

    def test_rule_ids_unique(self):
        """All rule_id values must be unique across all dimensions."""
        rule_ids = []
        for rules in self.config["quality_rules"]["dimensions"].values():
            for rule in rules:
                rule_ids.append(rule["rule_id"])
        self.assertEqual(
            len(rule_ids),
            len(set(rule_ids)),
            f"Duplicate rule_ids found: {[rid for rid in rule_ids if rule_ids.count(rid) > 1]}",
        )

    def test_thresholds_present(self):
        """Thresholds for bronze_to_silver and silver_to_gold must be defined."""
        thresholds = self.config["quality_rules"].get("thresholds", {})
        self.assertIn("bronze_to_silver", thresholds)
        self.assertIn("silver_to_gold", thresholds)
        self.assertGreaterEqual(thresholds["bronze_to_silver"], 0.0)
        self.assertLessEqual(thresholds["silver_to_gold"], 1.0)


class TestRulesReferenceSemanticColumns(unittest.TestCase):
    """Verify that every column referenced by a rule exists in semantic.yaml."""

    @classmethod
    def setUpClass(cls):
        with open(QUALITY_RULES_PATH, "r") as f:
            cls.rules_config = yaml.safe_load(f)
        with open(SEMANTIC_YAML_PATH, "r") as f:
            cls.semantic_config = yaml.safe_load(f)
        cls.semantic_columns = {
            col["name"] for col in cls.semantic_config["columns"]
        }

    def test_all_column_references_valid(self):
        """Every 'column' field in a rule must match a column in semantic.yaml."""
        for dim_name, rules in self.rules_config["quality_rules"]["dimensions"].items():
            for rule in rules:
                col = rule.get("column")
                if col is not None:
                    self.assertIn(
                        col,
                        self.semantic_columns,
                        f"Rule {rule['rule_id']} references column '{col}' "
                        f"which is not in semantic.yaml",
                    )


class TestScoreCalculation(unittest.TestCase):
    """Test the score calculation logic using mock data."""

    def _make_row(self, **overrides):
        """Create a default valid row, then apply overrides."""
        defaults = {
            "order_id": "ORD-99999",
            "customer_id": "CUST-999",
            "customer_name": "Test User",
            "email": "test@example.com",
            "phone": "555-9999",
            "order_date": "2024-06-01",
            "ship_date": "2024-06-05",
            "region": "East",
            "product_category": "Electronics",
            "product_name": "Widget",
            "quantity": "2",
            "unit_price": "50.00",
            "discount_pct": "0.1",
            "revenue": "90.00",
            "payment_method": "credit_card",
            "status": "completed",
        }
        defaults.update(overrides)
        return defaults

    def test_all_pass_score_is_one(self):
        """When all rows are clean, overall score should be 1.0."""
        rows = [
            self._make_row(order_id="ORD-00001"),
            self._make_row(order_id="ORD-00002"),
        ]
        rules_config = runner.load_rules()
        report = runner.run_all_checks(rules_config, rows)
        self.assertEqual(report["overall"]["score"], 1.0)
        self.assertFalse(report["has_critical_failures"])

    def test_score_decreases_with_failures(self):
        """Injecting a bad row should lower the score below 1.0."""
        rows = [
            self._make_row(order_id="ORD-00001"),
            self._make_row(order_id="ORD-00002", region="InvalidRegion"),
        ]
        rules_config = runner.load_rules()
        report = runner.run_all_checks(rules_config, rows)
        self.assertLess(report["overall"]["score"], 1.0)

    def test_critical_failure_flagged(self):
        """A critical rule failure must be reported."""
        rows = [
            self._make_row(order_id="ORD-00001"),
            self._make_row(order_id="ORD-00002", region="InvalidRegion"),
        ]
        rules_config = runner.load_rules()
        report = runner.run_all_checks(rules_config, rows)
        self.assertTrue(report["has_critical_failures"])
        crit_ids = [cf["rule_id"] for cf in report["critical_failures"]]
        self.assertIn("CON-002", crit_ids)

    def test_score_calculation_math(self):
        """Score should equal passed / total."""
        rows = [self._make_row(order_id="ORD-00001")]
        rules_config = runner.load_rules()
        report = runner.run_all_checks(rules_config, rows)
        expected = report["overall"]["passed"] / report["overall"]["total"]
        self.assertAlmostEqual(report["overall"]["score"], expected, places=4)

    def test_per_dimension_scores_exist(self):
        """Report must include scores for all 5 dimensions."""
        rows = [self._make_row(order_id="ORD-00001")]
        rules_config = runner.load_rules()
        report = runner.run_all_checks(rules_config, rows)
        for dim in EXPECTED_DIMENSIONS:
            self.assertIn(dim, report["dimensions"])
            self.assertIn("score", report["dimensions"][dim])
            self.assertIn("passed", report["dimensions"][dim])
            self.assertIn("total", report["dimensions"][dim])

    def test_duplicate_order_id_lowers_uniqueness(self):
        """Duplicate order_id should fail the uniqueness rule."""
        rows = [
            self._make_row(order_id="ORD-00001"),
            self._make_row(order_id="ORD-00001"),  # duplicate
        ]
        rules_config = runner.load_rules()
        report = runner.run_all_checks(rules_config, rows)
        uniq_score = report["dimensions"]["uniqueness"]["score"]
        self.assertLess(uniq_score, 1.0)

    def test_null_email_within_threshold_still_passes(self):
        """3 nulls in 50 rows (6%) is within the 10% email threshold."""
        rows = [self._make_row(order_id=f"ORD-{i:05d}") for i in range(50)]
        # Null out 3 emails (6%)
        for i in range(3):
            rows[i]["email"] = ""
        rules_config = runner.load_rules()
        report = runner.run_all_checks(rules_config, rows)
        # Find the email null rate rule result
        comp_rules = report["dimensions"]["completeness"]["rules"]
        email_rule = [r for r in comp_rules if r["rule_id"] == "COMP-002"][0]
        self.assertTrue(email_rule["passed"])

    def test_warning_failure_does_not_create_critical(self):
        """A warning-only failure should not appear in critical_failures."""
        rows = [self._make_row(order_id="ORD-00001")]
        rows[0]["email"] = ""  # 100% null rate for email (warning rule)
        rules_config = runner.load_rules()
        report = runner.run_all_checks(rules_config, rows)
        crit_ids = [cf["rule_id"] for cf in report["critical_failures"]]
        self.assertNotIn("COMP-002", crit_ids)


if __name__ == "__main__":
    unittest.main()
