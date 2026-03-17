"""
Integration tests for sales_transactions metadata artifacts.

Validates that the metadata in YAML files is consistent with the actual
CSV source data file on disk.
"""

import csv
import os
import unittest

import yaml


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
SOURCE_YAML_PATH = os.path.join(CONFIG_DIR, "source.yaml")
SEMANTIC_YAML_PATH = os.path.join(CONFIG_DIR, "semantic.yaml")
CSV_PATH = os.path.join(PROJECT_ROOT, "sample_data", "sales_transactions.csv")

EXPECTED_PII_COLUMNS = {"customer_id", "customer_name", "email", "phone"}


class TestCsvFileIntegrity(unittest.TestCase):
    """Integration tests: CSV file vs metadata."""

    @classmethod
    def setUpClass(cls):
        """Load the CSV and YAML files."""
        # Load CSV
        with open(CSV_PATH, "r") as f:
            reader = csv.DictReader(f)
            cls.csv_rows = list(reader)
            cls.csv_columns = list(cls.csv_rows[0].keys()) if cls.csv_rows else []

        # Load source.yaml
        with open(SOURCE_YAML_PATH, "r") as f:
            cls.source_config = yaml.safe_load(f)

        # Load semantic.yaml
        with open(SEMANTIC_YAML_PATH, "r") as f:
            cls.semantic_config = yaml.safe_load(f)

    def test_csv_file_exists(self):
        """The source CSV file must exist and be readable."""
        self.assertTrue(
            os.path.isfile(CSV_PATH),
            f"CSV file not found at {CSV_PATH}",
        )

    def test_csv_is_readable(self):
        """CSV must be parseable and return rows."""
        self.assertGreater(
            len(self.csv_rows),
            0,
            "CSV file has no data rows",
        )

    def test_row_count_matches_profiled(self):
        """Number of rows in CSV must match the profiled row_count."""
        profiled_count = self.source_config["source"]["row_count"]
        actual_count = len(self.csv_rows)
        self.assertEqual(
            actual_count,
            profiled_count,
            f"CSV has {actual_count} rows but source.yaml says {profiled_count}",
        )

    def test_column_names_match_source_schema(self):
        """Column names in CSV header must match schema in source.yaml."""
        schema_columns = [
            col["name"]
            for col in self.source_config["source"]["schema"]["columns"]
        ]
        self.assertEqual(
            self.csv_columns,
            schema_columns,
            f"CSV columns {self.csv_columns} do not match "
            f"source.yaml schema {schema_columns}",
        )

    def test_column_names_match_semantic_schema(self):
        """Column names in CSV header must match columns in semantic.yaml."""
        semantic_columns = [
            col["name"] for col in self.semantic_config["columns"]
        ]
        self.assertEqual(
            self.csv_columns,
            semantic_columns,
            f"CSV columns do not match semantic.yaml columns",
        )

    def test_column_count_matches(self):
        """Number of columns in CSV must match the profiled column_count."""
        profiled_count = self.source_config["source"]["column_count"]
        actual_count = len(self.csv_columns)
        self.assertEqual(
            actual_count,
            profiled_count,
            f"CSV has {actual_count} columns but source.yaml says {profiled_count}",
        )

    def test_pii_columns_detected_match_confirmation(self):
        """PII columns in semantic.yaml must match the confirmed set."""
        pii_in_semantic = set(
            self.semantic_config["pii_summary"]["columns_with_pii"]
        )
        self.assertEqual(
            pii_in_semantic,
            EXPECTED_PII_COLUMNS,
            f"PII columns mismatch: semantic.yaml has {pii_in_semantic}, "
            f"expected {EXPECTED_PII_COLUMNS}",
        )

    def test_pii_columns_flagged_in_column_definitions(self):
        """Each PII column must be individually flagged pii=true in columns list."""
        sem_columns = {
            col["name"]: col for col in self.semantic_config["columns"]
        }
        for pii_col in EXPECTED_PII_COLUMNS:
            self.assertTrue(
                sem_columns[pii_col].get("pii", False),
                f"Column '{pii_col}' not flagged as PII in semantic.yaml columns",
            )

    def test_email_null_count_matches_csv(self):
        """Null count for email in semantic.yaml must match actual CSV nulls."""
        actual_nulls = sum(
            1 for row in self.csv_rows if row["email"].strip() == ""
        )
        sem_columns = {
            col["name"]: col for col in self.semantic_config["columns"]
        }
        profiled_nulls = sem_columns["email"]["null_count"]
        self.assertEqual(
            actual_nulls,
            profiled_nulls,
            f"email nulls: CSV has {actual_nulls}, semantic.yaml says {profiled_nulls}",
        )

    def test_phone_null_count_matches_csv(self):
        """Null count for phone in semantic.yaml must match actual CSV nulls."""
        actual_nulls = sum(
            1 for row in self.csv_rows if row["phone"].strip() == ""
        )
        sem_columns = {
            col["name"]: col for col in self.semantic_config["columns"]
        }
        profiled_nulls = sem_columns["phone"]["null_count"]
        self.assertEqual(
            actual_nulls,
            profiled_nulls,
            f"phone nulls: CSV has {actual_nulls}, semantic.yaml says {profiled_nulls}",
        )

    def test_ship_date_null_count_matches_csv(self):
        """Null count for ship_date in semantic.yaml must match actual CSV nulls."""
        actual_nulls = sum(
            1 for row in self.csv_rows if row["ship_date"].strip() == ""
        )
        sem_columns = {
            col["name"]: col for col in self.semantic_config["columns"]
        }
        profiled_nulls = sem_columns["ship_date"]["null_count"]
        self.assertEqual(
            actual_nulls,
            profiled_nulls,
            f"ship_date nulls: CSV has {actual_nulls}, semantic.yaml says {profiled_nulls}",
        )

    def test_order_id_uniqueness_in_csv(self):
        """order_id must be unique in the actual CSV data."""
        order_ids = [row["order_id"] for row in self.csv_rows]
        self.assertEqual(
            len(order_ids),
            len(set(order_ids)),
            "order_id is not unique in the CSV data",
        )

    def test_pending_orders_have_null_ship_date(self):
        """All pending orders should have a null ship_date."""
        pending_rows = [
            row for row in self.csv_rows if row["status"] == "pending"
        ]
        for row in pending_rows:
            self.assertEqual(
                row["ship_date"].strip(),
                "",
                f"Pending order {row['order_id']} has ship_date={row['ship_date']}",
            )

    def test_revenue_is_positive(self):
        """All revenue values must be positive."""
        for row in self.csv_rows:
            revenue = float(row["revenue"])
            self.assertGreater(
                revenue,
                0,
                f"Order {row['order_id']} has non-positive revenue: {revenue}",
            )


if __name__ == "__main__":
    unittest.main()
