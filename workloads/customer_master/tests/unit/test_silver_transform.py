"""Unit tests for customer_master Bronze-to-Silver transformation logic."""
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def silver_spec():
    """Load silver spec from config."""
    import yaml

    config_path = PROJECT_ROOT / "workloads" / "customer_master" / "config" / "silver.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


class TestSilverSpecValidation:
    """Validate the silver spec against the contract schema."""

    def test_spec_matches_schema(self, silver_spec):
        import jsonschema

        schema_path = PROJECT_ROOT / "contracts" / "v1" / "silver_spec.schema.json"
        with open(schema_path) as f:
            schema = json.load(f)

        jsonschema.validate(instance=silver_spec, schema=schema)

    def test_primary_key_is_customer_id(self, silver_spec):
        assert silver_spec["primary_key"] == ["customer_id"]

    def test_dedup_strategy_is_keep_latest(self, silver_spec):
        assert silver_spec["dedup_strategy"] == "keep_latest"
        assert silver_spec["dedup_order_by"] == "account_open_date"

    def test_quality_threshold(self, silver_spec):
        assert silver_spec["quality_threshold"] == 0.80

    def test_critical_columns_not_null(self, silver_spec):
        critical = silver_spec["null_handling"]["critical_columns"]
        assert "customer_id" in critical
        assert "email" in critical
        assert "last_name" in critical

    def test_pii_masking_enabled(self, silver_spec):
        assert silver_spec["pii_masking"]["enabled"] is True
        masked_cols = [c["name"] for c in silver_spec["pii_masking"]["columns"]]
        assert "ssn" in masked_cols
        assert "email" in masked_cols
        assert "phone" in masked_cols
        assert "date_of_birth" in masked_cols
        assert "address" in masked_cols

    def test_ssn_uses_hash_method(self, silver_spec):
        ssn_mask = next(
            c for c in silver_spec["pii_masking"]["columns"] if c["name"] == "ssn"
        )
        assert ssn_mask["method"] == "hash"

    def test_pre_pii_derived_columns(self, silver_spec):
        pre_pii = silver_spec.get("pre_pii_derived_columns", [])
        names = [c["name"] for c in pre_pii]
        assert "email_domain" in names

    def test_derived_columns_present(self, silver_spec):
        derived = silver_spec.get("derived_columns", [])
        names = [c["name"] for c in derived]
        assert "age_years" in names
        assert "customer_tenure_months" in names
        assert "income_bucket" in names
        assert "geographic_region" in names
        assert "employment_category" in names
        assert "wealth_tier" in names
        assert "lifecycle_stage" in names
        assert "lawful_basis" in names
        assert "consent_status" in names
        assert "retention_expiry_date" in names
        assert "ssn_duplicate_flag" in names

    def test_quarantine_enabled(self, silver_spec):
        assert silver_spec["quarantine"]["enabled"] is True
        assert silver_spec["quarantine"]["retention_days"] == 90


class TestSilverTransformRendered:
    """Validate the rendered Silver transform script."""

    def test_script_exists(self):
        script_path = (
            PROJECT_ROOT
            / "workloads"
            / "customer_master"
            / "scripts"
            / "transform"
            / "bronze_to_silver.py"
        )
        assert script_path.exists()

    def test_script_has_codegen_header(self):
        script_path = (
            PROJECT_ROOT
            / "workloads"
            / "customer_master"
            / "scripts"
            / "transform"
            / "bronze_to_silver.py"
        )
        content = script_path.read_text()
        assert "# spec_hash:" in content
        assert "# template_id: silver_transform" in content
        assert "# template_hash:" in content
        assert "# schema_version: v1" in content
        assert "# rendered_at:" in content

    def test_script_contains_dedup_logic(self):
        script_path = (
            PROJECT_ROOT
            / "workloads"
            / "customer_master"
            / "scripts"
            / "transform"
            / "bronze_to_silver.py"
        )
        content = script_path.read_text()
        assert "customer_id" in content
        assert "account_open_date" in content
        assert "row_number" in content

    def test_script_contains_pii_masking(self):
        script_path = (
            PROJECT_ROOT
            / "workloads"
            / "customer_master"
            / "scripts"
            / "transform"
            / "bronze_to_silver.py"
        )
        content = script_path.read_text()
        assert "sha2" in content
        assert "ssn" in content
        assert "REDACTED" in content

    def test_script_writes_to_iceberg(self):
        script_path = (
            PROJECT_ROOT
            / "workloads"
            / "customer_master"
            / "scripts"
            / "transform"
            / "bronze_to_silver.py"
        )
        content = script_path.read_text()
        assert "glue_catalog.customer_master_db.silver_customer_master" in content


class TestDriftValidation:
    """Ensure rendered script matches spec (no manual edits)."""

    def test_no_drift(self):
        from shared.codegen.renderer import render_dry_run

        spec = {
            "dataset_name": "customer_master",
            "schema_version": "v1",
            "source_table": "glue_catalog.customer_master_db.bronze_customer_master",
            "primary_key": ["customer_id"],
            "dedup_strategy": "keep_latest",
            "dedup_order_by": "account_open_date",
            "quality_threshold": 0.80,
            "iceberg_database": "customer_master_db",
            "iceberg_table": "silver_customer_master",
            "iceberg_partition_spec": [],
            "type_casts": [
                {"column": "date_of_birth", "from_type": "STRING", "to_type": "DATE", "format": "yyyy-MM-dd"},
                {"column": "account_open_date", "from_type": "STRING", "to_type": "DATE", "format": "yyyy-MM-dd"},
                {"column": "annual_income", "from_type": "STRING", "to_type": "INTEGER"},
                {"column": "credit_score", "from_type": "STRING", "to_type": "INTEGER"},
            ],
            "pre_pii_derived_columns": [
                {"name": "email_domain", "expression": "substring_index(email, '@', -1)", "description": "Domain extracted from raw email before pseudonymization"},
            ],
            "pii_masking": {
                "enabled": True,
                "columns": [
                    {"name": "ssn", "method": "hash"},
                    {"name": "email", "method": "hash"},
                    {"name": "phone", "method": "hash"},
                    {"name": "date_of_birth", "method": "redact"},
                    {"name": "address", "method": "redact"},
                ],
            },
            "derived_columns": [
                {"name": "age_years", "expression": "floor(datediff(current_date(), date_of_birth) / 365.25)", "description": "Customer age in years"},
                {"name": "customer_tenure_months", "expression": "floor(months_between(current_date(), account_open_date))", "description": "Months since account opened"},
                {"name": "income_bucket", "expression": "CASE WHEN annual_income < 75000 THEN 'Low' WHEN annual_income < 150000 THEN 'Mid' WHEN annual_income < 300000 THEN 'High' ELSE 'Ultra' END", "description": "Income tier"},
                {"name": "geographic_region", "expression": "CASE WHEN state IN ('CT','ME','MA','NH','RI','VT','NJ','NY','PA') THEN 'Northeast' WHEN state IN ('IL','IN','IA','KS','MI','MN','MO','NE','ND','OH','SD','WI') THEN 'Midwest' WHEN state IN ('AL','AR','DE','FL','GA','KY','LA','MD','MS','NC','OK','SC','TN','TX','VA','WV','DC') THEN 'Southeast' WHEN state IN ('AZ','CO','ID','MT','NV','NM','UT','WY') THEN 'Southwest' WHEN state IN ('AK','CA','HI','OR','WA') THEN 'West' ELSE 'Unknown' END", "description": "US Census region"},
                {"name": "employment_category", "expression": "CASE WHEN employment_status = 'Employed' THEN 'W2' WHEN employment_status = 'Self-Employed' THEN '1099' WHEN employment_status = 'Retired' THEN 'Retired' ELSE 'Other' END", "description": "Simplified employment category"},
                {"name": "wealth_tier", "expression": "CASE WHEN annual_income >= 300000 AND credit_score >= 750 THEN 'Ultra High Net Worth' WHEN annual_income >= 150000 AND credit_score >= 720 THEN 'High Net Worth' WHEN annual_income >= 75000 AND credit_score >= 680 THEN 'Mass Affluent' ELSE 'Mass Market' END", "description": "Composite wealth tier"},
                {"name": "lifecycle_stage", "expression": "CASE WHEN floor(months_between(current_date(), account_open_date)) < 6 THEN 'New' WHEN floor(months_between(current_date(), account_open_date)) < 24 THEN 'Growing' WHEN floor(months_between(current_date(), account_open_date)) < 60 THEN 'Mature' ELSE 'Loyal' END", "description": "Customer lifecycle stage"},
                {"name": "lawful_basis", "expression": "'contract'", "description": "GDPR lawful basis"},
                {"name": "consent_status", "expression": "'active'", "description": "Default consent status"},
                {"name": "retention_expiry_date", "expression": "date_add(current_date(), 365)", "description": "GDPR 365-day retention"},
                {"name": "ssn_duplicate_flag", "expression": "CASE WHEN count(1) OVER (PARTITION BY ssn) > 1 THEN true ELSE false END", "description": "Flags duplicate SSNs"},
            ],
            "drop_columns": [],
        }

        spec_json = json.dumps(spec, sort_keys=True)
        spec_hash = hashlib.sha256(spec_json.encode()).hexdigest()

        rendered_bytes, artifact_hash = render_dry_run(
            spec=spec,
            spec_hash=spec_hash,
            template_id="silver_transform",
            template_version="1.1.0",
            run_started_at="2026-06-03T00:00:00Z",
            schema_version="v1",
        )

        script_path = (
            PROJECT_ROOT
            / "workloads"
            / "customer_master"
            / "scripts"
            / "transform"
            / "bronze_to_silver.py"
        )
        actual_content = script_path.read_bytes()
        assert actual_content == rendered_bytes, "Silver script has drifted from spec"
