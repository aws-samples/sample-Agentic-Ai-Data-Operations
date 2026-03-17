"""Integration tests for order_transactions end-to-end pipeline."""

import csv
import os
import tempfile
import importlib.util
from datetime import date

import pytest

# Load modules
_base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

_transform_path = os.path.join(_base, "scripts", "transform", "bronze_to_gold.py")
_spec_t = importlib.util.spec_from_file_location("bronze_to_gold", _transform_path)
_mod_t = importlib.util.module_from_spec(_spec_t)
_spec_t.loader.exec_module(_mod_t)
transform = _mod_t.transform

_bronze_qpath = os.path.join(_base, "scripts", "quality", "check_bronze.py")
_spec_bq = importlib.util.spec_from_file_location("check_bronze", _bronze_qpath)
_mod_bq = importlib.util.module_from_spec(_spec_bq)
_spec_bq.loader.exec_module(_mod_bq)
check_bronze = _mod_bq.check_bronze

_gold_qpath = os.path.join(_base, "scripts", "quality", "check_gold.py")
_spec_gq = importlib.util.spec_from_file_location("check_gold", _gold_qpath)
_mod_gq = importlib.util.module_from_spec(_spec_gq)
_spec_gq.loader.exec_module(_mod_gq)
check_gold = _mod_gq.check_gold

FIXTURES_DIR = os.path.abspath(os.path.join(_base, "..", "..", "shared", "fixtures"))
ORDERS_PATH = os.path.join(FIXTURES_DIR, "orders.csv")
CUSTOMERS_PATH = os.path.join(FIXTURES_DIR, "customers.csv")


class TestEndToEndPipeline:
    """End-to-end pipeline integration tests."""

    @pytest.fixture
    def pipeline_output(self):
        """Run the full pipeline and return outputs."""
        with tempfile.TemporaryDirectory() as gold_dir:
            with tempfile.TemporaryDirectory() as quar_dir:
                bronze_report = check_bronze(ORDERS_PATH)
                stats = transform(
                    orders_path=ORDERS_PATH,
                    customers_path=CUSTOMERS_PATH,
                    output_dir=gold_dir,
                    quarantine_dir=quar_dir,
                )
                gold_report = check_gold(
                    gold_dir=gold_dir,
                    customers_path=CUSTOMERS_PATH,
                )
                yield {
                    "bronze_report": bronze_report,
                    "stats": stats,
                    "gold_report": gold_report,
                    "gold_dir": gold_dir,
                    "quar_dir": quar_dir,
                }

    def test_pipeline_completes(self, pipeline_output):
        assert pipeline_output["stats"]["clean_records"] > 0

    def test_bronze_quality_runs(self, pipeline_output):
        assert pipeline_output["bronze_report"]["row_count"] == 157

    def test_gold_quality_meets_threshold(self, pipeline_output):
        assert pipeline_output["gold_report"]["meets_threshold"]

    def test_gold_no_critical_failures(self, pipeline_output):
        assert pipeline_output["gold_report"]["critical_failures"] == 0

    def test_quarantine_accounts_for_all_records(self, pipeline_output):
        stats = pipeline_output["stats"]
        deduped = stats["total_raw"] - stats["duplicates_removed"]
        assert stats["clean_records"] + stats["quarantine_count"] == deduped

    def test_seven_duplicate_order_ids_removed(self, pipeline_output):
        assert pipeline_output["stats"]["duplicates_removed"] == 7

    def test_five_orphan_customers_quarantined(self, pipeline_output):
        # 5 orphan customer_ids: CUST-945, CUST-989, CUST-915, CUST-940, CUST-914
        assert pipeline_output["stats"]["orphan_fk_quarantined"] >= 5

    def test_future_dates_quarantined(self, pipeline_output):
        assert pipeline_output["stats"]["future_date_quarantined"] > 0

    def test_star_schema_complete(self, pipeline_output):
        tables = pipeline_output["gold_report"]["tables"]
        assert tables["order_fact"] > 0
        assert tables["dim_product"] > 0
        assert tables["dim_region"] == 4
        assert tables["dim_status"] == 3

    def test_gold_score_is_perfect(self, pipeline_output):
        assert pipeline_output["gold_report"]["score"] == 1.0


class TestDataIntegrity:
    """Tests for data integrity across the pipeline."""

    def test_revenue_values_positive_in_gold(self):
        with tempfile.TemporaryDirectory() as gold_dir:
            with tempfile.TemporaryDirectory() as quar_dir:
                transform(
                    orders_path=ORDERS_PATH,
                    customers_path=CUSTOMERS_PATH,
                    output_dir=gold_dir,
                    quarantine_dir=quar_dir,
                )
                with open(os.path.join(gold_dir, "order_fact.csv")) as f:
                    for row in csv.DictReader(f):
                        assert float(row["revenue"]) > 0

    def test_quantity_values_positive_in_gold(self):
        with tempfile.TemporaryDirectory() as gold_dir:
            with tempfile.TemporaryDirectory() as quar_dir:
                transform(
                    orders_path=ORDERS_PATH,
                    customers_path=CUSTOMERS_PATH,
                    output_dir=gold_dir,
                    quarantine_dir=quar_dir,
                )
                with open(os.path.join(gold_dir, "order_fact.csv")) as f:
                    for row in csv.DictReader(f):
                        assert int(row["quantity"]) > 0

    def test_discount_pct_in_range(self):
        with tempfile.TemporaryDirectory() as gold_dir:
            with tempfile.TemporaryDirectory() as quar_dir:
                transform(
                    orders_path=ORDERS_PATH,
                    customers_path=CUSTOMERS_PATH,
                    output_dir=gold_dir,
                    quarantine_dir=quar_dir,
                )
                with open(os.path.join(gold_dir, "order_fact.csv")) as f:
                    for row in csv.DictReader(f):
                        d = float(row["discount_pct"])
                        assert 0 <= d <= 1

    def test_no_empty_product_names(self):
        with tempfile.TemporaryDirectory() as gold_dir:
            with tempfile.TemporaryDirectory() as quar_dir:
                transform(
                    orders_path=ORDERS_PATH,
                    customers_path=CUSTOMERS_PATH,
                    output_dir=gold_dir,
                    quarantine_dir=quar_dir,
                )
                with open(os.path.join(gold_dir, "dim_product.csv")) as f:
                    for row in csv.DictReader(f):
                        assert row["product_name"].strip()

    def test_summary_revenue_matches_fact(self):
        with tempfile.TemporaryDirectory() as gold_dir:
            with tempfile.TemporaryDirectory() as quar_dir:
                transform(
                    orders_path=ORDERS_PATH,
                    customers_path=CUSTOMERS_PATH,
                    output_dir=gold_dir,
                    quarantine_dir=quar_dir,
                )
                # Total revenue from fact
                with open(os.path.join(gold_dir, "order_fact.csv")) as f:
                    fact_revenue = sum(float(r["revenue"]) for r in csv.DictReader(f))
                # Total revenue from summary
                with open(os.path.join(gold_dir, "order_summary.csv")) as f:
                    summary_revenue = sum(float(r["total_revenue"]) for r in csv.DictReader(f))
                assert abs(fact_revenue - summary_revenue) < 0.1
