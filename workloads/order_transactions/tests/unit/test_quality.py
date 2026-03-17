"""Unit tests for order_transactions quality checks."""

import csv
import os
import tempfile
import importlib.util

import pytest

# Load quality modules
_bronze_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "scripts", "quality", "check_bronze.py"
)
_spec_b = importlib.util.spec_from_file_location("check_bronze", os.path.abspath(_bronze_path))
_mod_b = importlib.util.module_from_spec(_spec_b)
_spec_b.loader.exec_module(_mod_b)
check_bronze = _mod_b.check_bronze

_gold_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "scripts", "quality", "check_gold.py"
)
_spec_g = importlib.util.spec_from_file_location("check_gold", os.path.abspath(_gold_path))
_mod_g = importlib.util.module_from_spec(_spec_g)
_spec_g.loader.exec_module(_mod_g)
check_gold = _mod_g.check_gold

# Load transform for generating Gold data
_transform_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "scripts", "transform", "bronze_to_gold.py"
)
_spec_t = importlib.util.spec_from_file_location("bronze_to_gold", os.path.abspath(_transform_path))
_mod_t = importlib.util.module_from_spec(_spec_t)
_spec_t.loader.exec_module(_mod_t)
transform = _mod_t.transform

FIXTURES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "shared", "fixtures")
)
ORDERS_PATH = os.path.join(FIXTURES_DIR, "orders.csv")
CUSTOMERS_PATH = os.path.join(FIXTURES_DIR, "customers.csv")


class TestBronzeQuality:
    """Tests for Bronze zone quality checks."""

    def test_returns_report_structure(self):
        report = check_bronze(ORDERS_PATH)
        assert "zone" in report
        assert report["zone"] == "bronze"
        assert "score" in report
        assert "checks" in report
        assert "row_count" in report

    def test_score_is_between_0_and_1(self):
        report = check_bronze(ORDERS_PATH)
        assert 0 <= report["score"] <= 1

    def test_checks_have_required_fields(self):
        report = check_bronze(ORDERS_PATH)
        for check in report["checks"]:
            assert "dimension" in check
            assert "rule" in check
            assert "passed" in check
            assert "severity" in check
            assert "detail" in check

    def test_completeness_checks_present(self):
        report = check_bronze(ORDERS_PATH)
        completeness = [c for c in report["checks"] if c["dimension"] == "completeness"]
        assert len(completeness) >= 3  # order_id, customer_id, order_date at minimum

    def test_uniqueness_check_detects_duplicates(self):
        report = check_bronze(ORDERS_PATH)
        uniqueness = [c for c in report["checks"] if c["dimension"] == "uniqueness"]
        assert len(uniqueness) > 0
        # We know there are duplicates in the source data
        dup_check = uniqueness[0]
        assert not dup_check["passed"]

    def test_validity_enum_checks(self):
        report = check_bronze(ORDERS_PATH)
        validity = [c for c in report["checks"] if c["dimension"] == "validity"]
        assert len(validity) >= 3  # category, status, region

    def test_consistency_revenue_check(self):
        report = check_bronze(ORDERS_PATH)
        consistency = [c for c in report["checks"] if c["dimension"] == "consistency"]
        assert len(consistency) >= 1

    def test_row_count_matches(self):
        report = check_bronze(ORDERS_PATH)
        assert report["row_count"] == 157

    def test_clean_data_scores_high(self, tmp_path):
        """A perfectly clean dataset should score 1.0."""
        filepath = tmp_path / "clean.csv"
        rows = [
            "order_id,customer_id,order_date,product_name,category,quantity,unit_price,discount_pct,revenue,status,region",
            "ORD-001,CUST-001,2025-06-01,Widget,Electronics,10,50.00,0.1,450.00,Completed,East",
            "ORD-002,CUST-002,2025-06-02,Gadget,Furniture,5,100.00,0.0,500.00,Pending,West",
        ]
        filepath.write_text("\n".join(rows))
        report = check_bronze(str(filepath))
        assert report["score"] == 1.0


class TestGoldQuality:
    """Tests for Gold zone quality checks."""

    @pytest.fixture
    def gold_data(self):
        """Generate Gold data for quality testing."""
        with tempfile.TemporaryDirectory() as gold_dir:
            with tempfile.TemporaryDirectory() as quar_dir:
                transform(
                    orders_path=ORDERS_PATH,
                    customers_path=CUSTOMERS_PATH,
                    output_dir=gold_dir,
                    quarantine_dir=quar_dir,
                )
                yield gold_dir

    def test_returns_report_structure(self, gold_data):
        report = check_gold(gold_dir=gold_data, customers_path=CUSTOMERS_PATH)
        assert report["zone"] == "gold"
        assert "score" in report
        assert "meets_threshold" in report
        assert "tables" in report

    def test_gold_meets_threshold(self, gold_data):
        report = check_gold(gold_dir=gold_data, customers_path=CUSTOMERS_PATH)
        assert report["meets_threshold"], (
            f"Gold quality {report['score']:.2%} below threshold {report['threshold']:.0%}"
        )

    def test_no_critical_failures(self, gold_data):
        report = check_gold(gold_dir=gold_data, customers_path=CUSTOMERS_PATH)
        assert report["critical_failures"] == 0

    def test_fact_pk_unique(self, gold_data):
        report = check_gold(gold_dir=gold_data, customers_path=CUSTOMERS_PATH)
        pk_check = next(
            c for c in report["checks"] if c["rule"] == "order_fact.order_id_unique"
        )
        assert pk_check["passed"]

    def test_referential_integrity_all_pass(self, gold_data):
        report = check_gold(gold_dir=gold_data, customers_path=CUSTOMERS_PATH)
        ri_checks = [c for c in report["checks"] if c["dimension"] == "referential_integrity"]
        for check in ri_checks:
            assert check["passed"], f"RI failure: {check['rule']}: {check['detail']}"

    def test_no_future_dates(self, gold_data):
        report = check_gold(gold_dir=gold_data, customers_path=CUSTOMERS_PATH)
        date_check = next(
            c for c in report["checks"] if c["rule"] == "order_fact.no_future_dates"
        )
        assert date_check["passed"]

    def test_no_orphan_customers(self, gold_data):
        report = check_gold(gold_dir=gold_data, customers_path=CUSTOMERS_PATH)
        orphan_check = next(
            c for c in report["checks"] if c["rule"] == "order_fact.no_orphan_customers"
        )
        assert orphan_check["passed"]

    def test_table_counts_present(self, gold_data):
        report = check_gold(gold_dir=gold_data, customers_path=CUSTOMERS_PATH)
        assert report["tables"]["order_fact"] > 0
        assert report["tables"]["dim_product"] > 0
        assert report["tables"]["dim_region"] == 4
        assert report["tables"]["dim_status"] == 3

    def test_score_is_1_for_clean_data(self, gold_data):
        report = check_gold(gold_dir=gold_data, customers_path=CUSTOMERS_PATH)
        assert report["score"] == 1.0
