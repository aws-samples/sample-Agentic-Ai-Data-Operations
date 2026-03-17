"""Unit tests for order_transactions ingestion."""

import os
import importlib.util

import pytest

# Load module
_ingest_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "scripts", "extract", "ingest_orders.py"
)
_spec = importlib.util.spec_from_file_location("ingest_orders", os.path.abspath(_ingest_path))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

validate_source_file = _mod.validate_source_file
read_source_csv = _mod.read_source_csv

FIXTURES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "shared", "fixtures")
)
ORDERS_PATH = os.path.join(FIXTURES_DIR, "orders.csv")


class TestValidateSourceFile:
    """Tests for source file validation."""

    def test_valid_file(self):
        result = validate_source_file(ORDERS_PATH)
        assert result["row_count"] == 157
        assert result["column_count"] == 11

    def test_expected_columns(self):
        result = validate_source_file(ORDERS_PATH)
        expected = {"order_id", "customer_id", "order_date", "product_name",
                    "category", "quantity", "unit_price", "discount_pct",
                    "revenue", "status", "region"}
        assert expected == set(result["columns"])

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            validate_source_file("/nonexistent/file.csv")

    def test_no_critical_issues(self):
        result = validate_source_file(ORDERS_PATH)
        # No null PKs in the source
        critical = [i for i in result["issues"] if "Missing columns" in i]
        assert len(critical) == 0

    def test_has_validated_at(self):
        result = validate_source_file(ORDERS_PATH)
        assert "validated_at" in result


class TestReadSourceCSV:
    """Tests for CSV reading."""

    def test_reads_all_rows(self):
        rows = read_source_csv(ORDERS_PATH)
        assert len(rows) == 157

    def test_row_is_dict(self):
        rows = read_source_csv(ORDERS_PATH)
        assert isinstance(rows[0], dict)

    def test_order_id_present(self):
        rows = read_source_csv(ORDERS_PATH)
        assert all(r.get("order_id") for r in rows)
