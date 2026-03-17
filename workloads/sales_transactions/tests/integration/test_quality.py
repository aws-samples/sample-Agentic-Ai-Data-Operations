"""
Integration tests for sales_transactions quality checks.

Runs the full quality-check pipeline against the actual sample CSV file
and validates the report output, scores, and per-dimension breakdowns.
"""

import json
import os
import sys
import tempfile
import unittest

import yaml


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
QUALITY_RULES_PATH = os.path.join(CONFIG_DIR, "quality_rules.yaml")
CSV_PATH = os.path.join(PROJECT_ROOT, "sample_data", "sales_transactions.csv")

# Add scripts to path so we can import the runner
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts", "quality")
sys.path.insert(0, SCRIPTS_DIR)

import run_quality_checks as runner  # noqa: E402

EXPECTED_DIMENSIONS = {"completeness", "accuracy", "consistency", "validity", "uniqueness"}

BRONZE_TO_SILVER_THRESHOLD = 0.80


class TestQualityCheckIntegration(unittest.TestCase):
    """Integration tests: run quality checks against the real sample CSV."""

    @classmethod
    def setUpClass(cls):
        """Run the full quality pipeline once for all tests."""
        cls.rules_config = runner.load_rules()
        cls.rows = runner.load_csv(CSV_PATH)
        cls.report = runner.run_all_checks(cls.rules_config, cls.rows)

        # Write report to a temp directory for file-generation tests
        cls.temp_dir = tempfile.mkdtemp(prefix="quality_report_test_")
        cls.report_path = runner.write_report(cls.report, report_dir=cls.temp_dir)

    # ------------------------------------------------------------------
    # Score threshold tests
    # ------------------------------------------------------------------

    def test_overall_score_above_bronze_threshold(self):
        """Overall quality score must be >= 0.80 (Bronze->Silver threshold)."""
        score = self.report["overall"]["score"]
        self.assertGreaterEqual(
            score,
            BRONZE_TO_SILVER_THRESHOLD,
            f"Overall score {score} is below Bronze->Silver threshold "
            f"({BRONZE_TO_SILVER_THRESHOLD})",
        )

    def test_overall_score_is_between_zero_and_one(self):
        """Score must be in [0.0, 1.0]."""
        score = self.report["overall"]["score"]
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    # ------------------------------------------------------------------
    # Critical failure tests
    # ------------------------------------------------------------------

    def test_no_critical_rule_failures(self):
        """No critical rules should fail on the sample data."""
        self.assertFalse(
            self.report["has_critical_failures"],
            f"Critical failures detected: "
            f"{[cf['rule_id'] for cf in self.report['critical_failures']]}",
        )

    def test_critical_failures_list_is_empty(self):
        """The critical_failures list must be empty for the sample data."""
        self.assertEqual(
            len(self.report["critical_failures"]),
            0,
            f"Expected 0 critical failures, got {len(self.report['critical_failures'])}",
        )

    # ------------------------------------------------------------------
    # Per-dimension breakdown tests
    # ------------------------------------------------------------------

    def test_all_dimensions_in_report(self):
        """Report must contain all 5 quality dimensions."""
        report_dims = set(self.report["dimensions"].keys())
        self.assertEqual(
            report_dims,
            EXPECTED_DIMENSIONS,
            f"Expected dimensions {EXPECTED_DIMENSIONS}, got {report_dims}",
        )

    def test_each_dimension_has_score(self):
        """Every dimension entry must include a score."""
        for dim_name, dim_data in self.report["dimensions"].items():
            self.assertIn(
                "score",
                dim_data,
                f"Dimension '{dim_name}' missing 'score' field",
            )

    def test_each_dimension_has_passed_and_total(self):
        """Every dimension must report passed and total counts."""
        for dim_name, dim_data in self.report["dimensions"].items():
            self.assertIn("passed", dim_data)
            self.assertIn("total", dim_data)
            self.assertGreater(
                dim_data["total"], 0,
                f"Dimension '{dim_name}' has 0 total rules",
            )

    def test_each_dimension_has_rules_list(self):
        """Every dimension must include a 'rules' list with per-rule results."""
        for dim_name, dim_data in self.report["dimensions"].items():
            self.assertIn("rules", dim_data)
            self.assertIsInstance(dim_data["rules"], list)
            self.assertGreater(len(dim_data["rules"]), 0)

    def test_dimension_scores_are_valid(self):
        """Every dimension score must be in [0.0, 1.0]."""
        for dim_name, dim_data in self.report["dimensions"].items():
            self.assertGreaterEqual(
                dim_data["score"], 0.0,
                f"Dimension '{dim_name}' score is negative",
            )
            self.assertLessEqual(
                dim_data["score"], 1.0,
                f"Dimension '{dim_name}' score exceeds 1.0",
            )

    # ------------------------------------------------------------------
    # JSON report file tests
    # ------------------------------------------------------------------

    def test_report_file_exists(self):
        """JSON report file must be written to disk."""
        self.assertTrue(
            os.path.isfile(self.report_path),
            f"Report file not found at {self.report_path}",
        )

    def test_report_file_is_valid_json(self):
        """Report file must parse as valid JSON."""
        with open(self.report_path, "r") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)

    def test_report_file_matches_in_memory_report(self):
        """Written report must match the in-memory report structure."""
        with open(self.report_path, "r") as f:
            written = json.load(f)
        self.assertEqual(written["overall"]["score"], self.report["overall"]["score"])
        self.assertEqual(written["overall"]["passed"], self.report["overall"]["passed"])
        self.assertEqual(written["overall"]["total"], self.report["overall"]["total"])

    def test_report_has_workload_name(self):
        """Report must include the workload name."""
        self.assertEqual(self.report["workload"], "sales_transactions")

    def test_report_has_generated_at(self):
        """Report must include a generated_at timestamp."""
        self.assertIn("generated_at", self.report)
        self.assertIsInstance(self.report["generated_at"], str)
        self.assertGreater(len(self.report["generated_at"]), 0)

    def test_report_has_row_count(self):
        """Report must include the row_count."""
        self.assertEqual(self.report["row_count"], 50)

    def test_report_has_thresholds(self):
        """Report must echo the configured thresholds."""
        self.assertIn("thresholds", self.report)
        self.assertIn("bronze_to_silver", self.report["thresholds"])
        self.assertIn("silver_to_gold", self.report["thresholds"])

    # ------------------------------------------------------------------
    # Specific rule result spot-checks
    # ------------------------------------------------------------------

    def test_order_id_uniqueness_passes(self):
        """order_id uniqueness rule must pass on sample data."""
        uniq_rules = self.report["dimensions"]["uniqueness"]["rules"]
        uniq_rule = [r for r in uniq_rules if r["rule_id"] == "UNQ-001"][0]
        self.assertTrue(uniq_rule["passed"])

    def test_email_null_rate_passes(self):
        """email null rate (6%) must be within the 10% threshold."""
        comp_rules = self.report["dimensions"]["completeness"]["rules"]
        email_rule = [r for r in comp_rules if r["rule_id"] == "COMP-002"][0]
        self.assertTrue(email_rule["passed"])

    def test_phone_null_rate_passes(self):
        """phone null rate (2%) must be within the 5% threshold."""
        comp_rules = self.report["dimensions"]["completeness"]["rules"]
        phone_rule = [r for r in comp_rules if r["rule_id"] == "COMP-003"][0]
        self.assertTrue(phone_rule["passed"])

    def test_pending_orders_consistency_passes(self):
        """pending orders must have null ship_date in sample data."""
        con_rules = self.report["dimensions"]["consistency"]["rules"]
        pending_rule = [r for r in con_rules if r["rule_id"] == "CON-001"][0]
        self.assertTrue(pending_rule["passed"])

    def test_all_sample_data_rules_pass(self):
        """All rules should pass on the clean sample data."""
        score = self.report["overall"]["score"]
        self.assertEqual(
            score,
            1.0,
            f"Expected perfect score on clean sample data, got {score}",
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    @classmethod
    def tearDownClass(cls):
        """Remove the temporary report file."""
        if os.path.isfile(cls.report_path):
            os.remove(cls.report_path)
        if os.path.isdir(cls.temp_dir):
            os.rmdir(cls.temp_dir)


if __name__ == "__main__":
    unittest.main()
