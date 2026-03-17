"""Unit tests for bronze_to_gold.py transformation pipeline."""

import importlib.util
import os

import pytest

# Load module by path
_spec = importlib.util.spec_from_file_location(
    "bronze_to_gold",
    os.path.join(
        os.path.dirname(__file__), "..", "..", "scripts", "transform", "bronze_to_gold.py"
    ),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

read_bronze = _mod.read_bronze
deduplicate = _mod.deduplicate
validate_rows = _mod.validate_rows
hash_email = _mod.hash_email
mask_phone = _mod.mask_phone
apply_pii_masking = _mod.apply_pii_masking
cast_types = _mod.cast_types
build_customer_fact = _mod.build_customer_fact
build_dim_segment = _mod.build_dim_segment
build_dim_country = _mod.build_dim_country
build_dim_status = _mod.build_dim_status
build_summary_by_segment = _mod.build_summary_by_segment
transform = _mod.transform

FIXTURES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "shared", "fixtures"
)
CSV_PATH = os.path.join(FIXTURES_DIR, "customers.csv")


# ---- Read Bronze ----

class TestReadBronze:
    def test_reads_52_rows(self):
        rows = read_bronze(CSV_PATH)
        assert len(rows) == 52

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            read_bronze("/nonexistent.csv")


# ---- Deduplication ----

class TestDeduplicate:
    def test_removes_known_duplicates(self):
        rows = read_bronze(CSV_PATH)
        clean, dupes = deduplicate(rows)
        assert len(dupes) == 2  # CUST-044, CUST-039
        assert len(clean) == 50

    def test_keeps_first_occurrence(self):
        rows = [
            {"customer_id": "CUST-001", "name": "First"},
            {"customer_id": "CUST-001", "name": "Second"},
        ]
        clean, dupes = deduplicate(rows)
        assert len(clean) == 1
        assert clean[0]["name"] == "First"
        assert len(dupes) == 1
        assert "duplicate" in dupes[0]["_quarantine_reason"]

    def test_no_duplicates(self):
        rows = [
            {"customer_id": "CUST-001"},
            {"customer_id": "CUST-002"},
        ]
        clean, dupes = deduplicate(rows)
        assert len(clean) == 2
        assert len(dupes) == 0

    def test_idempotent(self):
        rows = read_bronze(CSV_PATH)
        clean1, _ = deduplicate(rows)
        clean2, dupes2 = deduplicate(clean1)
        assert len(clean1) == len(clean2)
        assert len(dupes2) == 0


# ---- Validation ----

class TestValidation:
    def test_all_valid_after_dedup(self):
        rows = read_bronze(CSV_PATH)
        clean, _ = deduplicate(rows)
        valid, quarantined = validate_rows(clean)
        assert len(valid) == 50
        assert len(quarantined) == 0

    def test_quarantine_null_pk(self):
        rows = [{"customer_id": "", "name": "X", "segment": "SMB",
                 "status": "Active", "country": "US", "join_date": "2024-01-01",
                 "annual_value": "100", "credit_limit": "50"}]
        _, q = validate_rows(rows)
        assert len(q) == 1
        assert "null customer_id" in q[0]["_quarantine_reason"]

    def test_quarantine_bad_format(self):
        rows = [{"customer_id": "BAD-ID", "name": "X", "segment": "SMB",
                 "status": "Active", "country": "US", "join_date": "2024-01-01",
                 "annual_value": "100", "credit_limit": "50"}]
        _, q = validate_rows(rows)
        assert len(q) == 1
        assert "invalid customer_id format" in q[0]["_quarantine_reason"]

    def test_quarantine_invalid_enum(self):
        rows = [{"customer_id": "CUST-001", "name": "X", "segment": "Unknown",
                 "status": "Active", "country": "US", "join_date": "2024-01-01",
                 "annual_value": "100", "credit_limit": "50"}]
        _, q = validate_rows(rows)
        assert len(q) == 1
        assert "invalid segment" in q[0]["_quarantine_reason"]

    def test_quarantine_bad_date(self):
        rows = [{"customer_id": "CUST-001", "name": "X", "segment": "SMB",
                 "status": "Active", "country": "US", "join_date": "not-a-date",
                 "annual_value": "100", "credit_limit": "50"}]
        _, q = validate_rows(rows)
        assert len(q) == 1
        assert "invalid join_date" in q[0]["_quarantine_reason"]

    def test_quarantine_bad_numeric(self):
        rows = [{"customer_id": "CUST-001", "name": "X", "segment": "SMB",
                 "status": "Active", "country": "US", "join_date": "2024-01-01",
                 "annual_value": "abc", "credit_limit": "50"}]
        _, q = validate_rows(rows)
        assert len(q) == 1
        assert "non-numeric annual_value" in q[0]["_quarantine_reason"]


# ---- PII Masking ----

class TestPIIMasking:
    def test_hash_email_deterministic(self):
        h1 = hash_email("test@example.com")
        h2 = hash_email("test@example.com")
        assert h1 == h2

    def test_hash_email_no_at_symbol(self):
        h = hash_email("test@example.com")
        assert "@" not in h
        assert len(h) == 64  # SHA-256 hex

    def test_hash_email_case_insensitive(self):
        assert hash_email("Test@Example.COM") == hash_email("test@example.com")

    def test_hash_email_null(self):
        assert hash_email(None) is None
        assert hash_email("") is None
        assert hash_email("   ") is None

    def test_mask_phone(self):
        masked = mask_phone("(555) 324-5471")
        assert masked.endswith("5471")
        assert "*" in masked

    def test_mask_phone_preserves_last_4(self):
        masked = mask_phone("(555) 999-1234")
        assert masked[-4:] == "1234"

    def test_mask_phone_null(self):
        assert mask_phone(None) is None
        assert mask_phone("") is None

    def test_mask_phone_short(self):
        assert mask_phone("1234") == "1234"

    def test_apply_masking_adds_columns(self):
        rows = [{"email": "a@b.com", "phone": "(555) 123-4567", "name": "Test"}]
        result = apply_pii_masking(rows)
        assert "email_hash" in result[0]
        assert "phone_masked" in result[0]
        assert "@" not in result[0]["email_hash"]


# ---- Type Casting ----

class TestTypeCasting:
    def test_casts_floats(self):
        rows = [{"annual_value": "123.45", "credit_limit": "678.90"}]
        result = cast_types(rows)
        assert result[0]["annual_value"] == 123.45
        assert result[0]["credit_limit"] == 678.90

    def test_empty_defaults_to_zero(self):
        rows = [{"annual_value": "", "credit_limit": ""}]
        result = cast_types(rows)
        assert result[0]["annual_value"] == 0.0
        assert result[0]["credit_limit"] == 0.0


# ---- Star Schema ----

class TestStarSchema:
    @pytest.fixture
    def fact_rows(self):
        rows = read_bronze(CSV_PATH)
        clean, _ = deduplicate(rows)
        valid, _ = validate_rows(clean)
        masked = apply_pii_masking(valid)
        casted = cast_types(masked)
        return build_customer_fact(casted)

    def test_fact_50_rows(self, fact_rows):
        assert len(fact_rows) == 50

    def test_fact_unique_ids(self, fact_rows):
        ids = [r["customer_id"] for r in fact_rows]
        assert len(set(ids)) == len(ids)

    def test_fact_has_all_columns(self, fact_rows):
        expected = {
            "customer_id", "name", "email_hash", "phone_masked",
            "segment", "industry", "country_code", "status",
            "join_date", "annual_value", "credit_limit",
        }
        assert set(fact_rows[0].keys()) == expected

    def test_dim_segment(self, fact_rows):
        dim = build_dim_segment(fact_rows)
        assert len(dim) == 3
        names = {d["segment_name"] for d in dim}
        assert names == {"Enterprise", "SMB", "Individual"}

    def test_dim_country(self, fact_rows):
        dim = build_dim_country(fact_rows)
        assert len(dim) == 4
        codes = {d["country_code"] for d in dim}
        assert codes == {"US", "UK", "CA", "DE"}
        # Check name mapping
        for d in dim:
            if d["country_code"] == "US":
                assert d["country_name"] == "United States"
            elif d["country_code"] == "UK":
                assert d["country_name"] == "United Kingdom"

    def test_dim_status(self, fact_rows):
        dim = build_dim_status(fact_rows)
        assert len(dim) == 3
        names = {d["status_name"] for d in dim}
        assert names == {"Active", "Inactive", "Churned"}

    def test_summary_by_segment(self, fact_rows):
        summary = build_summary_by_segment(fact_rows)
        assert len(summary) == 3
        total_count = sum(s["customer_count"] for s in summary)
        assert total_count == 50
        # Check totals match fact
        fact_total = sum(r["annual_value"] for r in fact_rows)
        summary_total = sum(s["total_annual_value"] for s in summary)
        assert abs(fact_total - summary_total) < 0.01

    def test_summary_avg_correctness(self, fact_rows):
        summary = build_summary_by_segment(fact_rows)
        for s in summary:
            expected_avg = s["total_annual_value"] / s["customer_count"]
            assert abs(s["avg_annual_value"] - expected_avg) < 0.01


# ---- Full Pipeline ----

class TestFullTransform:
    def test_transform_end_to_end(self, tmp_path):
        result = transform(
            file_path=CSV_PATH,
            output_dir=str(tmp_path),
            upload=False,
        )
        assert result["bronze_row_count"] == 52
        assert result["duplicates_removed"] == 2
        assert result["quarantined_count"] == 2  # 2 dupes, 0 invalid
        assert result["gold_fact_row_count"] == 50
        assert result["dim_segment_count"] == 3
        assert result["dim_country_count"] == 4
        assert result["dim_status_count"] == 3
        assert result["summary_row_count"] == 3

    def test_idempotent(self, tmp_path):
        r1 = transform(file_path=CSV_PATH, output_dir=str(tmp_path / "run1"), upload=False)
        r2 = transform(file_path=CSV_PATH, output_dir=str(tmp_path / "run2"), upload=False)
        assert r1["gold_fact_row_count"] == r2["gold_fact_row_count"]
        assert r1["duplicates_removed"] == r2["duplicates_removed"]
        # Compare fact table content
        for i in range(len(r1["tables"]["customer_fact"])):
            assert r1["tables"]["customer_fact"][i] == r2["tables"]["customer_fact"][i]

    def test_output_files_created(self, tmp_path):
        transform(file_path=CSV_PATH, output_dir=str(tmp_path), upload=False)
        assert (tmp_path / "customer_fact.csv").exists()
        assert (tmp_path / "dim_segment.csv").exists()
        assert (tmp_path / "dim_country.csv").exists()
        assert (tmp_path / "dim_status.csv").exists()
        assert (tmp_path / "customer_summary_by_segment.csv").exists()
        assert (tmp_path / "quarantine" / "quarantined_records.csv").exists()

    def test_quarantine_has_reasons(self, tmp_path):
        import csv as csvmod
        transform(file_path=CSV_PATH, output_dir=str(tmp_path), upload=False)
        with open(tmp_path / "quarantine" / "quarantined_records.csv") as f:
            reader = csvmod.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        for row in rows:
            assert "_quarantine_reason" in row
            assert "duplicate" in row["_quarantine_reason"]
