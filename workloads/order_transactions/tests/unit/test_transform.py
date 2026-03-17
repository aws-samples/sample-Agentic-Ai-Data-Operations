"""Unit tests for order_transactions Bronze-to-Gold transformation."""

import csv
import os
import tempfile
import importlib.util
from datetime import date

import pytest

# Load module directly
_transform_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "scripts", "transform", "bronze_to_gold.py"
)
_spec = importlib.util.spec_from_file_location("bronze_to_gold", os.path.abspath(_transform_path))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

transform = _mod.transform
load_orders = _mod.load_orders
load_valid_customer_ids = _mod.load_valid_customer_ids
_build_star_schema = _mod._build_star_schema

FIXTURES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "shared", "fixtures")
)
ORDERS_PATH = os.path.join(FIXTURES_DIR, "orders.csv")
CUSTOMERS_PATH = os.path.join(FIXTURES_DIR, "customers.csv")


@pytest.fixture
def temp_dirs():
    """Create temporary output directories."""
    with tempfile.TemporaryDirectory() as gold_dir:
        with tempfile.TemporaryDirectory() as quar_dir:
            yield gold_dir, quar_dir


@pytest.fixture
def sample_csv(tmp_path):
    """Create a minimal sample CSV for testing."""
    filepath = tmp_path / "sample.csv"
    rows = [
        "order_id,customer_id,order_date,product_name,category,quantity,unit_price,discount_pct,revenue,status,region",
        "ORD-001,CUST-001,2025-06-01,Widget,Electronics,10,50.00,0.1,450.00,Completed,East",
        "ORD-002,CUST-002,2025-06-02,Gadget,Furniture,5,100.00,0.0,500.00,Pending,West",
        "ORD-003,CUST-003,2025-06-03,Gizmo,Supplies,3,20.00,0.05,57.00,Cancelled,South",
    ]
    filepath.write_text("\n".join(rows))
    return str(filepath)


@pytest.fixture
def sample_customers(tmp_path):
    """Create a minimal customers CSV."""
    filepath = tmp_path / "customers.csv"
    rows = [
        "customer_id,name,email,phone,segment,industry,country,status,join_date,annual_value,credit_limit",
        "CUST-001,Alice,a@x.com,555-1234,Enterprise,Tech,US,Active,2024-01-01,100000,50000",
        "CUST-002,Bob,b@x.com,555-5678,SMB,Retail,US,Active,2024-02-01,50000,25000",
        "CUST-003,Carol,c@x.com,555-9012,Enterprise,Finance,US,Active,2024-03-01,75000,40000",
    ]
    filepath.write_text("\n".join(rows))
    return str(filepath)


class TestLoadData:
    """Tests for data loading functions."""

    def test_load_orders_returns_list(self):
        rows = load_orders(ORDERS_PATH)
        assert isinstance(rows, list)
        assert len(rows) > 0

    def test_load_orders_has_expected_columns(self):
        rows = load_orders(ORDERS_PATH)
        expected = {"order_id", "customer_id", "order_date", "product_name",
                    "category", "quantity", "unit_price", "discount_pct",
                    "revenue", "status", "region"}
        assert expected == set(rows[0].keys())

    def test_load_orders_count(self):
        rows = load_orders(ORDERS_PATH)
        assert len(rows) == 157  # 157 data rows

    def test_load_valid_customer_ids(self):
        ids = load_valid_customer_ids(CUSTOMERS_PATH)
        assert isinstance(ids, set)
        assert len(ids) > 0
        assert "CUST-001" in ids

    def test_load_customer_ids_missing_file(self):
        ids = load_valid_customer_ids("/nonexistent/path.csv")
        assert ids == set()


class TestDeduplication:
    """Tests for dedup logic."""

    def test_duplicates_removed(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        stats = transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        assert stats["duplicates_removed"] > 0

    def test_fact_table_has_unique_order_ids(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        with open(os.path.join(gold_dir, "order_fact.csv")) as f:
            reader = csv.DictReader(f)
            ids = [r["order_id"] for r in reader]
        assert len(ids) == len(set(ids)), "Duplicate order_ids in fact table"


class TestFKValidation:
    """Tests for foreign key validation."""

    def test_orphan_customers_quarantined(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        stats = transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        assert stats["orphan_fk_quarantined"] > 0

    def test_no_orphans_in_fact(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        valid_custs = load_valid_customer_ids(CUSTOMERS_PATH)
        with open(os.path.join(gold_dir, "order_fact.csv")) as f:
            reader = csv.DictReader(f)
            for row in reader:
                assert row["customer_id"] in valid_custs, (
                    f"Orphan customer {row['customer_id']} in fact table"
                )

    def test_all_clean_with_valid_customers(self, sample_csv, sample_customers, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        stats = transform(
            orders_path=sample_csv,
            customers_path=sample_customers,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        assert stats["orphan_fk_quarantined"] == 0


class TestFutureDateQuarantine:
    """Tests for future date quarantine."""

    def test_future_dates_quarantined(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        stats = transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        assert stats["future_date_quarantined"] > 0

    def test_no_future_dates_in_fact(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        ref = date(2026, 12, 31)
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
            reference_date=ref,
        )
        with open(os.path.join(gold_dir, "order_fact.csv")) as f:
            reader = csv.DictReader(f)
            for row in reader:
                from datetime import datetime as dt
                od = dt.strptime(row["order_date"], "%Y-%m-%d").date()
                assert od <= ref, f"Future date {row['order_date']} in fact table"


class TestEnumValidation:
    """Tests for enum value validation."""

    def test_only_valid_categories_in_fact(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        with open(os.path.join(gold_dir, "dim_product.csv")) as f:
            cats = {r["category"] for r in csv.DictReader(f)}
        assert cats.issubset({"Electronics", "Furniture", "Supplies"})

    def test_only_valid_statuses(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        with open(os.path.join(gold_dir, "dim_status.csv")) as f:
            statuses = {r["status_name"] for r in csv.DictReader(f)}
        assert statuses.issubset({"Completed", "Pending", "Cancelled"})

    def test_only_valid_regions(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        with open(os.path.join(gold_dir, "dim_region.csv")) as f:
            regions = {r["region_name"] for r in csv.DictReader(f)}
        assert regions.issubset({"East", "West", "Central", "South"})


class TestStarSchema:
    """Tests for star schema construction."""

    def test_fact_table_created(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        assert os.path.exists(os.path.join(gold_dir, "order_fact.csv"))

    def test_all_dimension_tables_created(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        for name in ["dim_product.csv", "dim_region.csv", "dim_status.csv"]:
            assert os.path.exists(os.path.join(gold_dir, name)), f"Missing {name}"

    def test_summary_table_created(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        assert os.path.exists(os.path.join(gold_dir, "order_summary.csv"))

    def test_fact_fks_reference_dims(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        # Load dim PKs
        with open(os.path.join(gold_dir, "dim_product.csv")) as f:
            product_ids = {r["product_id"] for r in csv.DictReader(f)}
        with open(os.path.join(gold_dir, "dim_region.csv")) as f:
            region_ids = {r["region_id"] for r in csv.DictReader(f)}
        with open(os.path.join(gold_dir, "dim_status.csv")) as f:
            status_ids = {r["status_id"] for r in csv.DictReader(f)}

        with open(os.path.join(gold_dir, "order_fact.csv")) as f:
            for row in csv.DictReader(f):
                assert row["product_id"] in product_ids
                assert row["region_id"] in region_ids
                assert row["status_id"] in status_ids

    def test_dim_region_has_4_regions(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        with open(os.path.join(gold_dir, "dim_region.csv")) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 4

    def test_dim_status_has_3_statuses(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        with open(os.path.join(gold_dir, "dim_status.csv")) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 3

    def test_fact_columns(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        with open(os.path.join(gold_dir, "order_fact.csv")) as f:
            reader = csv.DictReader(f)
            row = next(reader)
        expected = {"order_id", "customer_id", "order_date", "product_id",
                    "region_id", "status_id", "status_name",
                    "quantity", "unit_price", "discount_pct", "revenue"}
        assert expected == set(row.keys())

    def test_summary_aggregation_correct(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        # Verify summary by reading fact and aggregating manually
        with open(os.path.join(gold_dir, "order_fact.csv")) as f:
            facts = list(csv.DictReader(f))
        with open(os.path.join(gold_dir, "dim_region.csv")) as f:
            region_map = {r["region_id"]: r["region_name"] for r in csv.DictReader(f)}
        with open(os.path.join(gold_dir, "dim_product.csv")) as f:
            cat_map = {r["product_id"]: r["category"] for r in csv.DictReader(f)}

        manual_agg = {}
        for row in facts:
            key = (region_map[row["region_id"]], cat_map[row["product_id"]])
            if key not in manual_agg:
                manual_agg[key] = {"revenue": 0.0, "count": 0}
            manual_agg[key]["revenue"] += float(row["revenue"])
            manual_agg[key]["count"] += 1

        with open(os.path.join(gold_dir, "order_summary.csv")) as f:
            summary = list(csv.DictReader(f))

        assert len(summary) == len(manual_agg)
        for s in summary:
            key = (s["region"], s["category"])
            assert key in manual_agg
            assert abs(float(s["total_revenue"]) - manual_agg[key]["revenue"]) < 0.1
            assert int(s["order_count"]) == manual_agg[key]["count"]


class TestQuarantine:
    """Tests for quarantine file creation."""

    def test_quarantine_file_created(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        stats = transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        if stats["quarantine_count"] > 0:
            assert os.path.exists(os.path.join(quar_dir, "quarantined_orders.csv"))

    def test_quarantine_has_reasons(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        stats = transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        if stats["quarantine_count"] > 0:
            with open(os.path.join(quar_dir, "quarantined_orders.csv")) as f:
                for row in csv.DictReader(f):
                    assert row.get("_quarantine_reasons"), "Missing quarantine reason"


class TestIdempotency:
    """Tests for transformation idempotency."""

    def test_double_run_same_output(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        stats1 = transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )

        with tempfile.TemporaryDirectory() as gold_dir2:
            with tempfile.TemporaryDirectory() as quar_dir2:
                stats2 = transform(
                    orders_path=ORDERS_PATH,
                    customers_path=CUSTOMERS_PATH,
                    output_dir=gold_dir2,
                    quarantine_dir=quar_dir2,
                )

        assert stats1["clean_records"] == stats2["clean_records"]
        assert stats1["duplicates_removed"] == stats2["duplicates_removed"]
        assert stats1["fact_count"] == stats2["fact_count"]


class TestTransformStats:
    """Tests for transformation statistics."""

    def test_stats_keys_present(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        stats = transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        required_keys = [
            "total_raw", "duplicates_removed", "null_pk_quarantined",
            "orphan_fk_quarantined", "future_date_quarantined",
            "clean_records", "quarantine_count", "fact_count",
            "dim_product_count", "dim_region_count", "dim_status_count",
        ]
        for key in required_keys:
            assert key in stats, f"Missing stat key: {key}"

    def test_record_counts_balance(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        stats = transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        deduped = stats["total_raw"] - stats["duplicates_removed"]
        assert stats["clean_records"] + stats["quarantine_count"] == deduped

    def test_fact_count_matches_clean(self, temp_dirs):
        gold_dir, quar_dir = temp_dirs
        stats = transform(
            orders_path=ORDERS_PATH,
            customers_path=CUSTOMERS_PATH,
            output_dir=gold_dir,
            quarantine_dir=quar_dir,
        )
        assert stats["fact_count"] == stats["clean_records"]
