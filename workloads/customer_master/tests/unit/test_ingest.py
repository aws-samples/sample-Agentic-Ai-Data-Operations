"""Unit tests for ingest_customers.py"""

import importlib.util
import os
import tempfile

import pytest

# Load module by path
_spec = importlib.util.spec_from_file_location(
    "ingest_customers",
    os.path.join(
        os.path.dirname(__file__), "..", "..", "scripts", "extract", "ingest_customers.py"
    ),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

read_csv = _mod.read_csv
compute_checksum = _mod.compute_checksum
rows_to_csv_bytes = _mod.rows_to_csv_bytes
EXPECTED_COLUMNS = _mod.EXPECTED_COLUMNS

FIXTURES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "shared", "fixtures"
)
CSV_PATH = os.path.join(FIXTURES_DIR, "customers.csv")


class TestReadCsv:
    def test_reads_all_rows(self):
        rows = read_csv(CSV_PATH)
        assert len(rows) == 52

    def test_has_expected_columns(self):
        rows = read_csv(CSV_PATH)
        for col in EXPECTED_COLUMNS:
            assert col in rows[0], f"Missing column: {col}"

    def test_first_row_has_customer_id(self):
        rows = read_csv(CSV_PATH)
        assert rows[0]["customer_id"].startswith("CUST-")

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            read_csv("/nonexistent/path.csv")

    def test_missing_columns_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("col_a,col_b\n1,2\n")
            f.flush()
            with pytest.raises(ValueError, match="missing expected columns"):
                read_csv(f.name)
        os.unlink(f.name)


class TestChecksum:
    def test_deterministic(self):
        rows = read_csv(CSV_PATH)
        c1 = compute_checksum(rows)
        c2 = compute_checksum(rows)
        assert c1 == c2

    def test_changes_with_data(self):
        rows = read_csv(CSV_PATH)
        c1 = compute_checksum(rows)
        rows[0]["name"] = "MODIFIED"
        c2 = compute_checksum(rows)
        assert c1 != c2

    def test_empty_rows(self):
        c = compute_checksum([])
        assert isinstance(c, str) and len(c) == 64


class TestRowsToCsvBytes:
    def test_round_trip(self):
        rows = read_csv(CSV_PATH)
        csv_bytes = rows_to_csv_bytes(rows)
        assert b"customer_id" in csv_bytes
        lines = csv_bytes.decode("utf-8").strip().split("\n")
        assert len(lines) == 53  # header + 52 rows

    def test_empty_rows(self):
        assert rows_to_csv_bytes([]) == b""
