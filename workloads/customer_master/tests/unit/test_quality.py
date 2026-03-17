"""Unit tests for check_bronze.py and check_gold.py quality checks."""

import importlib.util
import os

import pytest

# Load modules by path
_base = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "quality")

_spec_bronze = importlib.util.spec_from_file_location(
    "check_bronze", os.path.join(_base, "check_bronze.py")
)
_bronze_mod = importlib.util.module_from_spec(_spec_bronze)
_spec_bronze.loader.exec_module(_bronze_mod)

_spec_gold = importlib.util.spec_from_file_location(
    "check_gold", os.path.join(_base, "check_gold.py")
)
_gold_mod = importlib.util.module_from_spec(_spec_gold)
_spec_gold.loader.exec_module(_gold_mod)

# Also load transform for generating gold output
_spec_transform = importlib.util.spec_from_file_location(
    "bronze_to_gold",
    os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "transform", "bronze_to_gold.py"),
)
_transform_mod = importlib.util.module_from_spec(_spec_transform)
_spec_transform.loader.exec_module(_transform_mod)

FIXTURES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "shared", "fixtures"
)
CSV_PATH = os.path.join(FIXTURES_DIR, "customers.csv")


# ---- Bronze Quality Check Functions ----

class TestBronzeCheckFunctions:
    @pytest.fixture
    def rows(self):
        return _bronze_mod.read_csv(CSV_PATH)

    def test_check_not_null_customer_id(self, rows):
        r = _bronze_mod.check_not_null(rows, "customer_id")
        assert r["rate"] == 1.0

    def test_check_not_null_email_has_nulls(self, rows):
        r = _bronze_mod.check_not_null(rows, "email")
        assert r["rate"] < 1.0
        assert r["non_null"] < r["total"]

    def test_check_unique_has_dupes(self, rows):
        r = _bronze_mod.check_unique(rows, "customer_id")
        assert r["duplicates"] == 2

    def test_check_regex_pk_format(self, rows):
        r = _bronze_mod.check_regex(rows, "customer_id", r"^CUST-\d{3}$")
        assert r["failures"] == 0

    def test_check_in_set_segment(self, rows):
        r = _bronze_mod.check_in_set(rows, "segment", {"Enterprise", "SMB", "Individual"})
        assert r["invalid"] == 0

    def test_check_in_set_status(self, rows):
        r = _bronze_mod.check_in_set(rows, "status", {"Active", "Inactive", "Churned"})
        assert r["invalid"] == 0

    def test_check_gte_annual_value(self, rows):
        r = _bronze_mod.check_gte(rows, "annual_value", 0)
        assert r["failing"] == 0


class TestBronzeReport:
    def test_full_bronze_report(self):
        report = _bronze_mod.run_bronze_checks(CSV_PATH)
        assert report["total_rows"] == 52
        assert report["total_rules"] == 9
        # pk_unique will fail because raw data has dupes
        # but it's noted as expected, so gate should still pass
        assert report["score"] > 0
        assert isinstance(report["rules"], list)
        assert len(report["rules"]) == 9

    def test_bronze_all_rules_have_name(self):
        report = _bronze_mod.run_bronze_checks(CSV_PATH)
        for rule in report["rules"]:
            assert "name" in rule
            assert "severity" in rule
            assert "passed" in rule

    def test_bronze_deterministic(self):
        r1 = _bronze_mod.run_bronze_checks(CSV_PATH)
        r2 = _bronze_mod.run_bronze_checks(CSV_PATH)
        assert r1["score"] == r2["score"]
        assert r1["passed_rules"] == r2["passed_rules"]


# ---- Gold Quality Check Functions ----

class TestGoldCheckFunctions:
    def test_check_unique(self):
        rows = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        r = _gold_mod.check_unique(rows, "id")
        assert r["duplicates"] == 0

    def test_check_unique_with_dupes(self):
        rows = [{"id": "A"}, {"id": "A"}]
        r = _gold_mod.check_unique(rows, "id")
        assert r["duplicates"] == 1

    def test_check_not_null(self):
        rows = [{"x": "a"}, {"x": "b"}, {"x": ""}]
        r = _gold_mod.check_not_null(rows, "x")
        assert r["non_null"] == 2

    def test_referential_integrity_pass(self):
        parent = [{"code": "A"}, {"code": "B"}]
        child = [{"val": "A"}, {"val": "B"}]
        r = _gold_mod.check_referential_integrity(parent, "code", child, "val")
        assert r["orphan_count"] == 0

    def test_referential_integrity_fail(self):
        parent = [{"code": "A"}]
        child = [{"val": "A"}, {"val": "B"}]
        r = _gold_mod.check_referential_integrity(parent, "code", child, "val")
        assert r["orphan_count"] == 1
        assert "B" in r["orphans"]

    def test_no_at_in_hash(self):
        rows = [{"h": "abc123def"}, {"h": "xyz789"}]
        r = _gold_mod.check_no_at_in_hash(rows, "h")
        assert r["has_at_symbol"] == 0

    def test_at_detected_in_unhashed(self):
        rows = [{"h": "test@example.com"}]
        r = _gold_mod.check_no_at_in_hash(rows, "h")
        assert r["has_at_symbol"] == 1

    def test_mask_chars_detected(self):
        rows = [{"p": "******1234"}]
        r = _gold_mod.check_mask_chars(rows, "p")
        assert r["masked"] == 1


class TestGoldReport:
    @pytest.fixture
    def gold_dir(self, tmp_path):
        _transform_mod.transform(
            file_path=CSV_PATH,
            output_dir=str(tmp_path),
            upload=False,
        )
        return str(tmp_path)

    def test_full_gold_report(self, gold_dir):
        report = _gold_mod.run_gold_checks(gold_dir)
        assert report["fact_row_count"] == 50
        assert report["total_rules"] == 9
        assert report["score"] >= 0.95
        assert report["gate_passed"] is True
        assert report["critical_failures"] == 0

    def test_gold_all_rules_pass(self, gold_dir):
        report = _gold_mod.run_gold_checks(gold_dir)
        for rule in report["rules"]:
            assert rule["passed"] is True, f"Rule {rule['name']} failed: {rule.get('details')}"

    def test_gold_deterministic(self, gold_dir):
        r1 = _gold_mod.run_gold_checks(gold_dir)
        r2 = _gold_mod.run_gold_checks(gold_dir)
        assert r1["score"] == r2["score"]
