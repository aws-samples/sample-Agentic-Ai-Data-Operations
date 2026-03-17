"""
Integration tests for sales_transactions transformation pipeline.

Runs the full bronze_to_silver.py and silver_to_gold.py against the
real sample CSV and verifies end-to-end correctness:
  - Output row count matches expectations
  - No null order_ids in Silver output
  - All emails are lowercase (or empty) in Silver output
  - Quarantine file exists (even if empty)
  - Gold output exists and contains aggregated rows
"""

import csv
import os
import shutil
import sys
import tempfile
import unittest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts", "transform")
CONFIG_PATH = os.path.join(BASE_DIR, "config", "transformations.yaml")
SOURCE_CSV = os.path.join(PROJECT_ROOT, "sample_data", "sales_transactions.csv")

sys.path.insert(0, SCRIPTS_DIR)
import bronze_to_silver as b2s  # noqa: E402
import silver_to_gold as s2g  # noqa: E402


class TestBronzeToSilverIntegration(unittest.TestCase):
    """Run bronze_to_silver against the real sample CSV and verify outputs."""

    @classmethod
    def setUpClass(cls):
        """Run the pipeline once into a temp directory."""
        cls.tmp_dir = tempfile.mkdtemp(prefix="test_b2s_")
        cls.silver_output = os.path.join(cls.tmp_dir, "silver", "sales_transactions_clean.csv")
        cls.quarantine_output = os.path.join(cls.tmp_dir, "quarantine", "quarantined_records.csv")

        cls.summary = b2s.run(
            config_path=CONFIG_PATH,
            source_csv=SOURCE_CSV,
            silver_output=cls.silver_output,
            quarantine_output=cls.quarantine_output,
        )

        # Read the Silver output for row-level assertions
        with open(cls.silver_output, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cls.silver_rows = list(reader)

    @classmethod
    def tearDownClass(cls):
        """Remove temp directory."""
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    # -- row count --------------------------------------------------------
    def test_output_row_count(self):
        """Silver output should have 50 rows (no duplicates in sample)."""
        self.assertEqual(
            len(self.silver_rows),
            50,
            f"Expected 50 rows in Silver, got {len(self.silver_rows)}",
        )

    def test_summary_silver_rows(self):
        """Summary dict should report 50 silver rows."""
        self.assertEqual(self.summary["silver_rows"], 50)

    def test_no_duplicates_removed(self):
        """Sample data has no duplicates, so count should be 0."""
        self.assertEqual(self.summary["duplicates_removed"], 0)

    # -- no null order_ids ------------------------------------------------
    def test_no_null_order_ids_in_silver(self):
        """Every row in Silver output must have a non-empty order_id."""
        for row in self.silver_rows:
            self.assertTrue(
                row["order_id"].strip(),
                f"Found null/empty order_id in Silver output: {row}",
            )

    # -- emails are lowercase ---------------------------------------------
    def test_all_emails_lowercase(self):
        """Every non-empty email in Silver output must be lowercase."""
        for row in self.silver_rows:
            email = row.get("email", "")
            if email.strip():
                # After PII masking, emails are SHA-256 hex (already lowercase)
                self.assertEqual(
                    email,
                    email.lower(),
                    f"Email not lowercase in Silver output: {email}",
                )

    # -- quarantine file exists -------------------------------------------
    def test_quarantine_file_exists(self):
        """Quarantine CSV must exist (even if it has zero data rows)."""
        self.assertTrue(
            os.path.isfile(self.quarantine_output),
            "Quarantine file was not created",
        )

    def test_quarantine_has_header(self):
        """Quarantine file must at least have a CSV header."""
        with open(self.quarantine_output, "r") as f:
            header = f.readline().strip()
        self.assertTrue(len(header) > 0, "Quarantine file has no header")

    def test_quarantine_row_count(self):
        """Sample data has no null PKs, so quarantine should be empty."""
        self.assertEqual(self.summary["quarantined_rows"], 0)

    # -- PII masking applied ----------------------------------------------
    def test_emails_are_masked(self):
        """Non-empty emails should be SHA-256 hashes (64 hex chars)."""
        for row in self.silver_rows:
            email = row.get("email", "")
            if email.strip():
                self.assertEqual(
                    len(email),
                    64,
                    f"Email does not look like a SHA-256 hash: {email}",
                )

    def test_phones_are_redacted(self):
        """Non-empty phones should be redacted to '***-****'."""
        for row in self.silver_rows:
            phone = row.get("phone", "")
            if phone.strip():
                self.assertEqual(
                    phone,
                    "***-****",
                    f"Phone not properly redacted: {phone}",
                )

    def test_customer_names_are_masked(self):
        """Customer names should be SHA-256 hashes (64 hex chars)."""
        for row in self.silver_rows:
            name = row.get("customer_name", "")
            if name.strip():
                self.assertEqual(
                    len(name),
                    64,
                    f"Customer name does not look like a SHA-256 hash: {name}",
                )

    # -- idempotency ------------------------------------------------------
    def test_idempotency(self):
        """Running the pipeline twice produces identical Silver output."""
        # Run a second time into a different temp dir
        tmp2 = tempfile.mkdtemp(prefix="test_b2s_idem_")
        silver2 = os.path.join(tmp2, "silver", "sales_transactions_clean.csv")
        quarantine2 = os.path.join(tmp2, "quarantine", "quarantined_records.csv")
        try:
            b2s.run(
                config_path=CONFIG_PATH,
                source_csv=SOURCE_CSV,
                silver_output=silver2,
                quarantine_output=quarantine2,
            )
            with open(self.silver_output, "r") as f1, open(silver2, "r") as f2:
                self.assertEqual(f1.read(), f2.read(), "Silver outputs differ between runs")
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)


class TestSilverToGoldIntegration(unittest.TestCase):
    """Run silver_to_gold against real Silver output and verify Gold."""

    @classmethod
    def setUpClass(cls):
        """Run bronze_to_silver first, then silver_to_gold."""
        cls.tmp_dir = tempfile.mkdtemp(prefix="test_s2g_")
        cls.silver_output = os.path.join(cls.tmp_dir, "silver", "sales_transactions_clean.csv")
        cls.quarantine_output = os.path.join(cls.tmp_dir, "quarantine", "quarantined_records.csv")
        cls.gold_output = os.path.join(cls.tmp_dir, "gold", "sales_summary_by_region_category.csv")

        # Bronze -> Silver
        b2s.run(
            config_path=CONFIG_PATH,
            source_csv=SOURCE_CSV,
            silver_output=cls.silver_output,
            quarantine_output=cls.quarantine_output,
        )

        # Silver -> Gold
        cls.gold_summary = s2g.run(
            config_path=CONFIG_PATH,
            silver_input=cls.silver_output,
            gold_output=cls.gold_output,
        )

        # Read Gold output
        with open(cls.gold_output, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cls.gold_rows = list(reader)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_gold_file_exists(self):
        """Gold CSV must be created."""
        self.assertTrue(os.path.isfile(self.gold_output))

    def test_gold_has_rows(self):
        """Gold output must have at least 1 aggregated row."""
        self.assertGreater(len(self.gold_rows), 0)

    def test_gold_row_count(self):
        """With 4 regions x 3 categories, expect up to 12 groups.
        The sample has a specific distribution; verify it matches."""
        # 4 regions * 3 categories = 12 max; some combos may be missing
        self.assertGreaterEqual(len(self.gold_rows), 8)
        self.assertLessEqual(len(self.gold_rows), 12)

    def test_gold_has_required_columns(self):
        """Gold output must include all aggregation columns."""
        expected = {
            "region", "product_category",
            "total_revenue", "avg_revenue", "min_revenue", "max_revenue",
            "total_quantity", "order_count",
        }
        actual = set(self.gold_rows[0].keys())
        self.assertEqual(actual, expected)

    def test_gold_order_count_sums_to_total(self):
        """Sum of order_count across all groups should equal Silver row count."""
        total_orders = sum(int(r["order_count"]) for r in self.gold_rows)
        self.assertEqual(
            total_orders,
            50,
            f"Gold order_count sum is {total_orders}, expected 50",
        )

    def test_gold_total_quantity_positive(self):
        """Every group must have a positive total_quantity."""
        for row in self.gold_rows:
            self.assertGreater(
                int(row["total_quantity"]),
                0,
                f"Group {row['region']}/{row['product_category']} has non-positive quantity",
            )

    def test_gold_total_revenue_positive(self):
        """Every group must have a positive total_revenue."""
        for row in self.gold_rows:
            self.assertGreater(
                float(row["total_revenue"]),
                0,
                f"Group {row['region']}/{row['product_category']} has non-positive revenue",
            )


if __name__ == "__main__":
    unittest.main()
