"""
Unit tests for sales_transactions metadata artifacts.

Validates that source.yaml and semantic.yaml are well-formed,
contain all required fields, and correctly classify columns.
"""

import os
import unittest

import yaml


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
SOURCE_YAML_PATH = os.path.join(CONFIG_DIR, "source.yaml")
SEMANTIC_YAML_PATH = os.path.join(CONFIG_DIR, "semantic.yaml")

EXPECTED_COLUMNS = [
    "order_id", "customer_id", "customer_name", "email", "phone",
    "order_date", "ship_date", "region", "product_category", "product_name",
    "quantity", "unit_price", "discount_pct", "revenue", "payment_method", "status",
]

EXPECTED_PII_COLUMNS = {"customer_id", "customer_name", "email", "phone"}

VALID_DATA_TYPES = {"string", "integer", "double", "date"}


class TestSourceYaml(unittest.TestCase):
    """Tests for config/source.yaml."""

    @classmethod
    def setUpClass(cls):
        with open(SOURCE_YAML_PATH, "r") as f:
            cls.config = yaml.safe_load(f)

    def test_source_yaml_exists(self):
        """source.yaml file must exist on disk."""
        self.assertTrue(
            os.path.isfile(SOURCE_YAML_PATH),
            f"source.yaml not found at {SOURCE_YAML_PATH}",
        )

    def test_source_yaml_is_valid_yaml(self):
        """source.yaml must parse without errors."""
        self.assertIsInstance(self.config, dict)

    def test_has_source_section(self):
        """source.yaml must have a top-level 'source' key."""
        self.assertIn("source", self.config)

    def test_has_required_source_fields(self):
        """source section must contain name, format, delimiter, schema."""
        source = self.config["source"]
        for field in ("name", "format", "delimiter", "schema"):
            self.assertIn(field, source, f"Missing required field: {field}")

    def test_has_location(self):
        """source section must have a location block."""
        self.assertIn("location", self.config["source"])

    def test_has_connection(self):
        """source section must have a connection block."""
        self.assertIn("connection", self.config["source"])

    def test_schema_has_columns(self):
        """schema must contain a columns list."""
        schema = self.config["source"]["schema"]
        self.assertIn("columns", schema)
        self.assertIsInstance(schema["columns"], list)

    def test_all_columns_present_in_schema(self):
        """All 16 expected columns must be present in the schema."""
        schema_columns = [
            col["name"] for col in self.config["source"]["schema"]["columns"]
        ]
        for col_name in EXPECTED_COLUMNS:
            self.assertIn(
                col_name,
                schema_columns,
                f"Column '{col_name}' missing from source.yaml schema",
            )

    def test_column_count(self):
        """Schema must have exactly 16 columns."""
        cols = self.config["source"]["schema"]["columns"]
        self.assertEqual(len(cols), 16, f"Expected 16 columns, got {len(cols)}")

    def test_every_column_has_data_type(self):
        """Every column in the schema must have a data_type field."""
        for col in self.config["source"]["schema"]["columns"]:
            self.assertIn(
                "data_type",
                col,
                f"Column '{col.get('name', 'UNKNOWN')}' missing data_type",
            )

    def test_data_types_are_valid(self):
        """Every column data_type must be one of the valid types."""
        for col in self.config["source"]["schema"]["columns"]:
            self.assertIn(
                col["data_type"],
                VALID_DATA_TYPES,
                f"Column '{col['name']}' has invalid data_type: {col['data_type']}",
            )


class TestSemanticYaml(unittest.TestCase):
    """Tests for config/semantic.yaml."""

    @classmethod
    def setUpClass(cls):
        with open(SEMANTIC_YAML_PATH, "r") as f:
            cls.config = yaml.safe_load(f)

    def test_semantic_yaml_exists(self):
        """semantic.yaml file must exist on disk."""
        self.assertTrue(
            os.path.isfile(SEMANTIC_YAML_PATH),
            f"semantic.yaml not found at {SEMANTIC_YAML_PATH}",
        )

    def test_semantic_yaml_is_valid_yaml(self):
        """semantic.yaml must parse without errors."""
        self.assertIsInstance(self.config, dict)

    def test_has_dataset_section(self):
        """semantic.yaml must have a top-level 'dataset' key."""
        self.assertIn("dataset", self.config)

    def test_has_columns_section(self):
        """semantic.yaml must have a top-level 'columns' key."""
        self.assertIn("columns", self.config)

    def test_all_columns_classified(self):
        """All 16 columns must be present and classified with a business_role."""
        sem_columns = {col["name"]: col for col in self.config["columns"]}
        for col_name in EXPECTED_COLUMNS:
            self.assertIn(
                col_name,
                sem_columns,
                f"Column '{col_name}' missing from semantic.yaml",
            )
            col = sem_columns[col_name]
            self.assertIn(
                "business_role",
                col,
                f"Column '{col_name}' missing business_role classification",
            )

    def test_every_column_has_data_type(self):
        """Every column in semantic.yaml must have a data_type."""
        for col in self.config["columns"]:
            self.assertIn(
                "data_type",
                col,
                f"Column '{col.get('name', 'UNKNOWN')}' missing data_type",
            )

    def test_pii_columns_flagged(self):
        """All expected PII columns must be flagged with pii=true."""
        sem_columns = {col["name"]: col for col in self.config["columns"]}
        for pii_col in EXPECTED_PII_COLUMNS:
            self.assertIn(pii_col, sem_columns, f"PII column '{pii_col}' not found")
            self.assertTrue(
                sem_columns[pii_col].get("pii", False),
                f"Column '{pii_col}' should be flagged as PII but is not",
            )

    def test_pii_columns_have_pii_type(self):
        """All PII columns must have a pii_type specified."""
        sem_columns = {col["name"]: col for col in self.config["columns"]}
        for pii_col in EXPECTED_PII_COLUMNS:
            col = sem_columns[pii_col]
            if col.get("pii"):
                self.assertIn(
                    "pii_type",
                    col,
                    f"PII column '{pii_col}' missing pii_type",
                )

    def test_non_pii_columns_not_flagged(self):
        """Columns not in the PII list must not be flagged as PII."""
        sem_columns = {col["name"]: col for col in self.config["columns"]}
        non_pii_columns = set(EXPECTED_COLUMNS) - EXPECTED_PII_COLUMNS
        for col_name in non_pii_columns:
            self.assertFalse(
                sem_columns[col_name].get("pii", False),
                f"Column '{col_name}' should not be flagged as PII",
            )

    def test_order_id_is_primary_key(self):
        """order_id must be classified as a primary_key identifier."""
        sem_columns = {col["name"]: col for col in self.config["columns"]}
        order_id = sem_columns["order_id"]
        self.assertEqual(
            order_id.get("business_role"),
            "identifier",
            "order_id must have business_role=identifier",
        )
        self.assertEqual(
            order_id.get("identifier_type"),
            "primary_key",
            "order_id must have identifier_type=primary_key",
        )

    def test_customer_id_is_foreign_key(self):
        """customer_id must be classified as a foreign_key identifier."""
        sem_columns = {col["name"]: col for col in self.config["columns"]}
        cust_id = sem_columns["customer_id"]
        self.assertEqual(
            cust_id.get("business_role"),
            "identifier",
            "customer_id must have business_role=identifier",
        )
        self.assertEqual(
            cust_id.get("identifier_type"),
            "foreign_key",
            "customer_id must have identifier_type=foreign_key",
        )

    def test_measures_present(self):
        """Business context must list the expected measure columns."""
        measures = self.config.get("business_context", {}).get("measures", [])
        expected_measures = {"revenue", "quantity", "unit_price", "discount_pct"}
        self.assertEqual(
            set(measures),
            expected_measures,
            f"Expected measures {expected_measures}, got {set(measures)}",
        )

    def test_dimensions_present(self):
        """Business context must list the expected dimension columns."""
        dimensions = self.config.get("business_context", {}).get("dimensions", [])
        expected_dims = {"region", "product_category", "product_name", "payment_method", "status"}
        self.assertEqual(
            set(dimensions),
            expected_dims,
            f"Expected dimensions {expected_dims}, got {set(dimensions)}",
        )

    def test_temporal_present(self):
        """Business context must list temporal columns."""
        temporal = self.config.get("business_context", {}).get("temporal", [])
        expected_temporal = {"order_date", "ship_date"}
        self.assertEqual(
            set(temporal),
            expected_temporal,
            f"Expected temporal {expected_temporal}, got {set(temporal)}",
        )

    def test_pii_summary_present(self):
        """semantic.yaml must include a pii_summary section."""
        self.assertIn("pii_summary", self.config)
        pii_summary = self.config["pii_summary"]
        self.assertIn("columns_with_pii", pii_summary)
        self.assertEqual(
            set(pii_summary["columns_with_pii"]),
            EXPECTED_PII_COLUMNS,
        )

    def test_seed_sql_examples_present(self):
        """semantic.yaml must include seed SQL examples."""
        self.assertIn("seed_sql_examples", self.config)
        examples = self.config["seed_sql_examples"]
        self.assertGreaterEqual(len(examples), 2, "Must have at least 2 seed SQL examples")
        for ex in examples:
            self.assertIn("name", ex)
            self.assertIn("sql", ex)

    def test_dataset_domain(self):
        """Dataset domain must be 'sales'."""
        self.assertEqual(self.config["dataset"].get("domain"), "sales")

    def test_null_statistics(self):
        """Columns with known nulls must have correct null_count."""
        sem_columns = {col["name"]: col for col in self.config["columns"]}
        self.assertEqual(sem_columns["email"]["null_count"], 3)
        self.assertEqual(sem_columns["phone"]["null_count"], 1)
        self.assertEqual(sem_columns["ship_date"]["null_count"], 7)


if __name__ == "__main__":
    unittest.main()
