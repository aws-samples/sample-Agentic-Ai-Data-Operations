"""
Unit tests for sales_transactions transformation artifacts.

Validates that:
  - transformations.yaml is valid YAML with all required sections
  - Deduplication logic correctly detects and removes duplicates
  - String trimming works on all string columns
  - Email lowercasing works
  - Null PK quarantine logic isolates bad rows
  - PII masking logic correctly hashes / redacts sensitive fields
"""

import hashlib
import os
import sys
import unittest

import yaml

# ---------------------------------------------------------------------------
# Path setup — allow imports from the scripts directory
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts", "transform")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
TRANSFORMATIONS_YAML = os.path.join(CONFIG_DIR, "transformations.yaml")

# Add the scripts/transform directory so we can import the module
sys.path.insert(0, SCRIPTS_DIR)
import bronze_to_silver as b2s  # noqa: E402


# ---------------------------------------------------------------------------
# Test: transformations.yaml structure
# ---------------------------------------------------------------------------
class TestTransformationsYaml(unittest.TestCase):
    """Validate transformations.yaml is well-formed and complete."""

    @classmethod
    def setUpClass(cls):
        with open(TRANSFORMATIONS_YAML, "r") as f:
            cls.config = yaml.safe_load(f)

    def test_file_exists(self):
        self.assertTrue(os.path.isfile(TRANSFORMATIONS_YAML))

    def test_is_valid_yaml(self):
        self.assertIsInstance(self.config, dict)

    def test_has_workload_name(self):
        self.assertEqual(self.config.get("workload"), "sales_transactions")

    def test_has_bronze_to_silver_section(self):
        self.assertIn("bronze_to_silver", self.config)

    def test_has_deduplication(self):
        b2s_cfg = self.config["bronze_to_silver"]
        self.assertIn("deduplication", b2s_cfg)
        dedup = b2s_cfg["deduplication"]
        self.assertTrue(dedup.get("enabled"))
        self.assertEqual(dedup.get("key"), "order_id")
        self.assertEqual(dedup.get("strategy"), "keep_first")

    def test_has_quarantine(self):
        b2s_cfg = self.config["bronze_to_silver"]
        self.assertIn("quarantine", b2s_cfg)
        self.assertTrue(b2s_cfg["quarantine"].get("enabled"))

    def test_has_string_normalization(self):
        b2s_cfg = self.config["bronze_to_silver"]
        self.assertIn("string_normalization", b2s_cfg)
        sn = b2s_cfg["string_normalization"]
        self.assertIn("trim_whitespace", sn)
        self.assertIn("lowercase", sn)

    def test_has_date_validation(self):
        b2s_cfg = self.config["bronze_to_silver"]
        self.assertIn("date_validation", b2s_cfg)
        rules = b2s_cfg["date_validation"]["rules"]
        self.assertGreaterEqual(len(rules), 2)

    def test_has_type_casting(self):
        b2s_cfg = self.config["bronze_to_silver"]
        self.assertIn("type_casting", b2s_cfg)

    def test_has_null_handling(self):
        b2s_cfg = self.config["bronze_to_silver"]
        self.assertIn("null_handling", b2s_cfg)

    def test_has_pii_masking(self):
        b2s_cfg = self.config["bronze_to_silver"]
        self.assertIn("pii_masking", b2s_cfg)
        pii = b2s_cfg["pii_masking"]
        self.assertTrue(pii.get("enabled"))
        masked_cols = {r["column"] for r in pii.get("rules", [])}
        self.assertIn("email", masked_cols)
        self.assertIn("phone", masked_cols)
        self.assertIn("customer_name", masked_cols)

    def test_has_output_section(self):
        b2s_cfg = self.config["bronze_to_silver"]
        self.assertIn("output", b2s_cfg)

    def test_has_silver_to_gold_section(self):
        self.assertIn("silver_to_gold", self.config)


# ---------------------------------------------------------------------------
# Test: deduplication logic
# ---------------------------------------------------------------------------
class TestDeduplication(unittest.TestCase):
    """Verify dedup by order_id keeps only the first occurrence."""

    def test_no_duplicates(self):
        rows = [
            {"order_id": "ORD-001", "name": "A"},
            {"order_id": "ORD-002", "name": "B"},
        ]
        result, dup_count = b2s.deduplicate(rows, "order_id", "keep_first")
        self.assertEqual(len(result), 2)
        self.assertEqual(dup_count, 0)

    def test_with_duplicates(self):
        rows = [
            {"order_id": "ORD-001", "name": "first"},
            {"order_id": "ORD-001", "name": "second"},
            {"order_id": "ORD-002", "name": "third"},
        ]
        result, dup_count = b2s.deduplicate(rows, "order_id", "keep_first")
        self.assertEqual(len(result), 2)
        self.assertEqual(dup_count, 1)
        # Kept the first occurrence
        self.assertEqual(result[0]["name"], "first")

    def test_all_duplicates(self):
        rows = [
            {"order_id": "ORD-001", "name": "A"},
            {"order_id": "ORD-001", "name": "B"},
            {"order_id": "ORD-001", "name": "C"},
        ]
        result, dup_count = b2s.deduplicate(rows, "order_id", "keep_first")
        self.assertEqual(len(result), 1)
        self.assertEqual(dup_count, 2)
        self.assertEqual(result[0]["name"], "A")

    def test_empty_input(self):
        result, dup_count = b2s.deduplicate([], "order_id", "keep_first")
        self.assertEqual(len(result), 0)
        self.assertEqual(dup_count, 0)


# ---------------------------------------------------------------------------
# Test: string trimming
# ---------------------------------------------------------------------------
class TestStringTrimming(unittest.TestCase):
    """Verify whitespace trimming on string columns."""

    def test_leading_trailing_spaces(self):
        rows = [{"name": "  Alice  ", "email": " alice@test.com "}]
        result = b2s.trim_whitespace(rows, ["name", "email"])
        self.assertEqual(result[0]["name"], "Alice")
        self.assertEqual(result[0]["email"], "alice@test.com")

    def test_no_whitespace(self):
        rows = [{"name": "Alice"}]
        result = b2s.trim_whitespace(rows, ["name"])
        self.assertEqual(result[0]["name"], "Alice")

    def test_tabs_and_newlines(self):
        rows = [{"name": "\tAlice\n"}]
        result = b2s.trim_whitespace(rows, ["name"])
        self.assertEqual(result[0]["name"], "Alice")

    def test_empty_string(self):
        rows = [{"name": "   "}]
        result = b2s.trim_whitespace(rows, ["name"])
        self.assertEqual(result[0]["name"], "")

    def test_non_target_columns_untouched(self):
        rows = [{"name": "  Alice  ", "quantity": "5"}]
        result = b2s.trim_whitespace(rows, ["name"])
        self.assertEqual(result[0]["name"], "Alice")
        self.assertEqual(result[0]["quantity"], "5")


# ---------------------------------------------------------------------------
# Test: email lowercasing
# ---------------------------------------------------------------------------
class TestEmailLowercasing(unittest.TestCase):
    """Verify email addresses are lowercased."""

    def test_mixed_case(self):
        rows = [{"email": "Alice.J@Email.COM"}]
        result = b2s.lowercase_columns(rows, ["email"])
        self.assertEqual(result[0]["email"], "alice.j@email.com")

    def test_already_lowercase(self):
        rows = [{"email": "alice@test.com"}]
        result = b2s.lowercase_columns(rows, ["email"])
        self.assertEqual(result[0]["email"], "alice@test.com")

    def test_uppercase(self):
        rows = [{"email": "BOB@EXAMPLE.ORG"}]
        result = b2s.lowercase_columns(rows, ["email"])
        self.assertEqual(result[0]["email"], "bob@example.org")

    def test_empty_email(self):
        rows = [{"email": ""}]
        result = b2s.lowercase_columns(rows, ["email"])
        self.assertEqual(result[0]["email"], "")

    def test_none_email(self):
        rows = [{"email": None}]
        result = b2s.lowercase_columns(rows, ["email"])
        self.assertIsNone(result[0]["email"])


# ---------------------------------------------------------------------------
# Test: null PK quarantine
# ---------------------------------------------------------------------------
class TestNullPkQuarantine(unittest.TestCase):
    """Verify rows with null/empty primary key are quarantined."""

    def test_null_pk(self):
        rows = [
            {"order_id": "ORD-001", "name": "A"},
            {"order_id": "", "name": "B"},
            {"order_id": "ORD-003", "name": "C"},
        ]
        clean, quarantined = b2s.quarantine_null_pk(rows, "order_id")
        self.assertEqual(len(clean), 2)
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0]["name"], "B")

    def test_whitespace_only_pk(self):
        rows = [{"order_id": "   ", "name": "whitespace"}]
        clean, quarantined = b2s.quarantine_null_pk(rows, "order_id")
        self.assertEqual(len(clean), 0)
        self.assertEqual(len(quarantined), 1)

    def test_none_pk(self):
        rows = [{"order_id": None, "name": "null"}]
        clean, quarantined = b2s.quarantine_null_pk(rows, "order_id")
        self.assertEqual(len(clean), 0)
        self.assertEqual(len(quarantined), 1)

    def test_all_valid(self):
        rows = [
            {"order_id": "ORD-001"},
            {"order_id": "ORD-002"},
        ]
        clean, quarantined = b2s.quarantine_null_pk(rows, "order_id")
        self.assertEqual(len(clean), 2)
        self.assertEqual(len(quarantined), 0)

    def test_missing_pk_column(self):
        rows = [{"name": "no order_id key"}]
        clean, quarantined = b2s.quarantine_null_pk(rows, "order_id")
        self.assertEqual(len(clean), 0)
        self.assertEqual(len(quarantined), 1)


# ---------------------------------------------------------------------------
# Test: PII masking
# ---------------------------------------------------------------------------
class TestPiiMasking(unittest.TestCase):
    """Verify PII masking logic for email, phone, and customer_name."""

    def setUp(self):
        self.pii_rules = [
            {"column": "email", "strategy": "hash_sha256"},
            {"column": "phone", "strategy": "redact", "replacement": "***-****"},
            {"column": "customer_name", "strategy": "hash_sha256"},
        ]

    def test_email_is_hashed(self):
        rows = [{"email": "alice@test.com", "phone": "555-0101", "customer_name": "Alice"}]
        result = b2s.apply_pii_masking(rows, self.pii_rules)
        expected_hash = hashlib.sha256("alice@test.com".encode("utf-8")).hexdigest()
        self.assertEqual(result[0]["email"], expected_hash)

    def test_phone_is_redacted(self):
        rows = [{"email": "a@b.com", "phone": "555-0101", "customer_name": "Alice"}]
        result = b2s.apply_pii_masking(rows, self.pii_rules)
        self.assertEqual(result[0]["phone"], "***-****")

    def test_customer_name_is_hashed(self):
        rows = [{"email": "a@b.com", "phone": "555-0101", "customer_name": "Alice Johnson"}]
        result = b2s.apply_pii_masking(rows, self.pii_rules)
        expected_hash = hashlib.sha256("Alice Johnson".encode("utf-8")).hexdigest()
        self.assertEqual(result[0]["customer_name"], expected_hash)

    def test_empty_email_not_hashed(self):
        rows = [{"email": "", "phone": "555-0101", "customer_name": "Alice"}]
        result = b2s.apply_pii_masking(rows, self.pii_rules)
        self.assertEqual(result[0]["email"], "")

    def test_none_phone_not_redacted(self):
        rows = [{"email": "a@b.com", "phone": None, "customer_name": "Alice"}]
        result = b2s.apply_pii_masking(rows, self.pii_rules)
        self.assertIsNone(result[0]["phone"])

    def test_hash_is_deterministic(self):
        """Same input always produces the same hash (idempotency)."""
        rows1 = [{"email": "test@test.com", "phone": "555-0000", "customer_name": "Bob"}]
        rows2 = [{"email": "test@test.com", "phone": "555-0000", "customer_name": "Bob"}]
        r1 = b2s.apply_pii_masking(rows1, self.pii_rules)
        r2 = b2s.apply_pii_masking(rows2, self.pii_rules)
        self.assertEqual(r1[0]["email"], r2[0]["email"])
        self.assertEqual(r1[0]["customer_name"], r2[0]["customer_name"])


# ---------------------------------------------------------------------------
# Test: date validation
# ---------------------------------------------------------------------------
class TestDateValidation(unittest.TestCase):
    """Verify date validation rules."""

    def test_valid_date(self):
        self.assertTrue(b2s.validate_date("2024-06-01", "%Y-%m-%d"))

    def test_invalid_date_format(self):
        self.assertFalse(b2s.validate_date("06/01/2024", "%Y-%m-%d"))

    def test_invalid_date_value(self):
        self.assertFalse(b2s.validate_date("2024-13-01", "%Y-%m-%d"))

    def test_empty_string(self):
        self.assertFalse(b2s.validate_date("", "%Y-%m-%d"))


if __name__ == "__main__":
    unittest.main()
