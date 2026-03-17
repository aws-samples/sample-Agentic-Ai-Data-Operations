"""Integration tests — end-to-end pipeline from Bronze CSV to Gold star schema."""

import csv
import importlib.util
import os

import pytest

# Load modules
_base = os.path.join(os.path.dirname(__file__), "..", "..")

_spec_t = importlib.util.spec_from_file_location(
    "bronze_to_gold",
    os.path.join(_base, "scripts", "transform", "bronze_to_gold.py"),
)
_transform = importlib.util.module_from_spec(_spec_t)
_spec_t.loader.exec_module(_transform)

_spec_cb = importlib.util.spec_from_file_location(
    "check_bronze",
    os.path.join(_base, "scripts", "quality", "check_bronze.py"),
)
_check_bronze = importlib.util.module_from_spec(_spec_cb)
_spec_cb.loader.exec_module(_check_bronze)

_spec_cg = importlib.util.spec_from_file_location(
    "check_gold",
    os.path.join(_base, "scripts", "quality", "check_gold.py"),
)
_check_gold = importlib.util.module_from_spec(_spec_cg)
_spec_cg.loader.exec_module(_check_gold)

FIXTURES_DIR = os.path.join(_base, "..", "..", "shared", "fixtures")
CSV_PATH = os.path.join(FIXTURES_DIR, "customers.csv")


class TestEndToEndPipeline:
    """Simulates the full pipeline: read -> quality check -> transform -> quality check."""

    @pytest.fixture(scope="class")
    def pipeline_output(self, tmp_path_factory):
        """Run full pipeline once for all tests."""
        out_dir = str(tmp_path_factory.mktemp("gold"))
        result = _transform.transform(
            file_path=CSV_PATH,
            output_dir=out_dir,
            upload=False,
        )
        return {**result, "gold_dir": out_dir}

    def test_bronze_quality_gate(self):
        """Bronze quality check runs and produces a score."""
        report = _check_bronze.run_bronze_checks(CSV_PATH)
        assert report["total_rows"] == 52
        assert report["score"] > 0.80

    def test_transform_produces_50_customers(self, pipeline_output):
        assert pipeline_output["gold_fact_row_count"] == 50

    def test_transform_removes_2_duplicates(self, pipeline_output):
        assert pipeline_output["duplicates_removed"] == 2

    def test_quarantine_captures_dupes(self, pipeline_output):
        assert pipeline_output["quarantined_count"] == 2

    def test_gold_quality_gate_passes(self, pipeline_output):
        report = _check_gold.run_gold_checks(pipeline_output["gold_dir"])
        assert report["gate_passed"] is True
        assert report["score"] >= 0.95
        assert report["critical_failures"] == 0

    def test_fact_table_file_valid(self, pipeline_output):
        path = os.path.join(pipeline_output["gold_dir"], "customer_fact.csv")
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 50
        # Check PII masking
        for row in rows:
            if row["email_hash"]:
                assert "@" not in row["email_hash"]
            if row["phone_masked"]:
                assert "*" in row["phone_masked"]

    def test_dim_segment_complete(self, pipeline_output):
        path = os.path.join(pipeline_output["gold_dir"], "dim_segment.csv")
        with open(path) as f:
            rows = list(csv.DictReader(f))
        names = {r["segment_name"] for r in rows}
        assert names == {"Enterprise", "SMB", "Individual"}

    def test_dim_country_has_full_names(self, pipeline_output):
        path = os.path.join(pipeline_output["gold_dir"], "dim_country.csv")
        with open(path) as f:
            rows = list(csv.DictReader(f))
        name_map = {r["country_code"]: r["country_name"] for r in rows}
        assert name_map["US"] == "United States"
        assert name_map["UK"] == "United Kingdom"
        assert name_map["CA"] == "Canada"
        assert name_map["DE"] == "Germany"

    def test_dim_status_complete(self, pipeline_output):
        path = os.path.join(pipeline_output["gold_dir"], "dim_status.csv")
        with open(path) as f:
            rows = list(csv.DictReader(f))
        names = {r["status_name"] for r in rows}
        assert names == {"Active", "Inactive", "Churned"}

    def test_summary_totals_match_fact(self, pipeline_output):
        fact_path = os.path.join(pipeline_output["gold_dir"], "customer_fact.csv")
        summ_path = os.path.join(pipeline_output["gold_dir"], "customer_summary_by_segment.csv")

        with open(fact_path) as f:
            fact = list(csv.DictReader(f))
        with open(summ_path) as f:
            summ = list(csv.DictReader(f))

        fact_total = sum(float(r["annual_value"]) for r in fact)
        summ_total = sum(float(r["total_annual_value"]) for r in summ)
        assert abs(fact_total - summ_total) < 0.01

        fact_count = len(fact)
        summ_count = sum(int(r["customer_count"]) for r in summ)
        assert fact_count == summ_count

    def test_no_pii_in_gold_email(self, pipeline_output):
        """Verify no raw emails exist in Gold zone."""
        path = os.path.join(pipeline_output["gold_dir"], "customer_fact.csv")
        with open(path) as f:
            content = f.read()
        assert "@example.com" not in content

    def test_bronze_immutability(self):
        """Verify source CSV is unchanged after pipeline run."""
        with open(CSV_PATH) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 52  # Original count preserved

    def test_idempotent_pipeline(self, tmp_path):
        """Running pipeline twice produces identical results."""
        r1 = _transform.transform(
            file_path=CSV_PATH, output_dir=str(tmp_path / "r1"), upload=False
        )
        r2 = _transform.transform(
            file_path=CSV_PATH, output_dir=str(tmp_path / "r2"), upload=False
        )
        assert r1["gold_fact_row_count"] == r2["gold_fact_row_count"]
        assert r1["duplicates_removed"] == r2["duplicates_removed"]

        # Compare fact CSVs
        with open(os.path.join(str(tmp_path / "r1"), "customer_fact.csv")) as f1:
            c1 = f1.read()
        with open(os.path.join(str(tmp_path / "r2"), "customer_fact.csv")) as f2:
            c2 = f2.read()
        assert c1 == c2


class TestConfigFilesExist:
    """Verify all config files are present and non-empty."""

    CONFIG_DIR = os.path.join(_base, "config")

    @pytest.mark.parametrize("filename", [
        "source.yaml",
        "semantic.yaml",
        "transformations.yaml",
        "quality_rules.yaml",
        "schedule.yaml",
    ])
    def test_config_exists(self, filename):
        path = os.path.join(self.CONFIG_DIR, filename)
        assert os.path.isfile(path), f"Missing config: {filename}"
        assert os.path.getsize(path) > 0, f"Empty config: {filename}"


class TestSQLFilesExist:
    """Verify SQL DDL files exist."""

    SQL_DIR = os.path.join(_base, "sql")

    def test_bronze_sql_exists(self):
        path = os.path.join(self.SQL_DIR, "bronze", "create_bronze_table.sql")
        assert os.path.isfile(path)

    def test_gold_sql_exists(self):
        path = os.path.join(self.SQL_DIR, "gold", "create_gold_tables.sql")
        assert os.path.isfile(path)
