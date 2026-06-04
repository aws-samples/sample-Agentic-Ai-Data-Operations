"""Unit tests for customer_master Silver-to-Gold transformation logic."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def gold_spec():
    """Load gold spec from config."""
    import yaml

    config_path = PROJECT_ROOT / "workloads" / "customer_master" / "config" / "gold.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


class TestGoldSpecValidation:
    """Validate the gold spec against the contract schema."""

    def test_spec_matches_schema(self, gold_spec):
        import jsonschema

        schema_path = PROJECT_ROOT / "contracts" / "v1" / "gold_spec.schema.json"
        with open(schema_path) as f:
            schema = json.load(f)

        jsonschema.validate(instance=gold_spec, schema=schema)

    def test_schema_type_is_star(self, gold_spec):
        assert gold_spec["schema_type"] == "star_schema"

    def test_grain_is_customer_level(self, gold_spec):
        assert gold_spec["grain"]["dimensions"] == ["customer_id"]
        assert gold_spec["grain"]["temporal"] == "none"

    def test_quality_threshold(self, gold_spec):
        assert gold_spec["quality_threshold"] == 0.95

    def test_output_table_is_dim_customer(self, gold_spec):
        tables = gold_spec.get("output_tables", [])
        assert len(tables) == 1
        assert tables[0]["name"] == "dim_customer"
        assert tables[0]["type"] == "dimension"

    def test_scd_type_2_dimensions(self, gold_spec):
        dims = gold_spec.get("dimensions", [])
        scd2_dims = [d["name"] for d in dims if d.get("scd_type") == 2]
        assert "risk_profile" in scd2_dims
        assert "employment_status" in scd2_dims
        assert "geographic_region" in scd2_dims

    def test_pii_suppressed_in_gold(self, gold_spec):
        """Gold columns must NOT include SSN, phone, address, DOB, first/last name."""
        output_cols = gold_spec["output_tables"][0]["columns"]
        assert "ssn" not in output_cols
        assert "phone" not in output_cols
        assert "address" not in output_cols
        assert "date_of_birth" not in output_cols
        assert "first_name" not in output_cols
        assert "last_name" not in output_cols

    def test_email_is_domain_only(self, gold_spec):
        """Gold should have email_masked (***@domain) not raw email."""
        output_cols = gold_spec["output_tables"][0]["columns"]
        assert "email" not in output_cols
        assert "email_masked" in output_cols
        assert "email_domain" in output_cols

    def test_derived_silver_columns(self, gold_spec):
        derived = gold_spec.get("derived_silver_columns", [])
        names = [c["name"] for c in derived]
        assert "email_masked" in names


class TestGoldTransformRendered:
    """Validate the rendered Gold transform script."""

    def test_script_exists(self):
        script_path = (
            PROJECT_ROOT
            / "workloads"
            / "customer_master"
            / "scripts"
            / "transform"
            / "silver_to_gold.py"
        )
        assert script_path.exists()

    def test_script_has_codegen_header(self):
        script_path = (
            PROJECT_ROOT
            / "workloads"
            / "customer_master"
            / "scripts"
            / "transform"
            / "silver_to_gold.py"
        )
        content = script_path.read_text()
        assert "# spec_hash:" in content
        assert "# template_id: gold_aggregate" in content
        assert "# schema_version: v1" in content

    def test_script_writes_to_dim_customer(self):
        script_path = (
            PROJECT_ROOT
            / "workloads"
            / "customer_master"
            / "scripts"
            / "transform"
            / "silver_to_gold.py"
        )
        content = script_path.read_text()
        assert "glue_catalog.customer_master_db.dim_customer" in content

    def test_script_reads_from_silver(self):
        script_path = (
            PROJECT_ROOT
            / "workloads"
            / "customer_master"
            / "scripts"
            / "transform"
            / "silver_to_gold.py"
        )
        content = script_path.read_text()
        assert "glue_catalog.customer_master_db.silver_customer_master" in content


class TestGoldDriftValidation:
    """Ensure rendered Gold script matches spec."""

    def test_no_drift(self):
        from shared.codegen.renderer import render_dry_run

        spec = {
            "dataset_name": "customer_master",
            "schema_version": "v1",
            "source_table": "glue_catalog.customer_master_db.silver_customer_master",
            "schema_type": "star_schema",
            "grain": {"dimensions": ["customer_id"], "temporal": "none"},
            "measures": [
                {"name": "customer_count", "source_column": "customer_id", "aggregation": "count"},
                {"name": "avg_credit_score", "source_column": "credit_score", "aggregation": "avg"},
                {"name": "avg_annual_income", "source_column": "annual_income", "aggregation": "avg"},
                {"name": "avg_tenure_months", "source_column": "customer_tenure_months", "aggregation": "avg"},
            ],
            "quality_threshold": 0.95,
            "iceberg_database": "customer_master_db",
            "iceberg_table": "dim_customer",
            "iceberg_partition_spec": [],
            "derived_silver_columns": [
                {"name": "email_masked", "expression": "concat('***@', email_domain)", "description": "Domain-only email for Gold"},
            ],
            "post_aggregation_columns": [],
        }

        spec_json = json.dumps(spec, sort_keys=True)
        spec_hash = hashlib.sha256(spec_json.encode()).hexdigest()

        rendered_bytes, artifact_hash = render_dry_run(
            spec=spec,
            spec_hash=spec_hash,
            template_id="gold_aggregate",
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
            / "silver_to_gold.py"
        )
        actual_content = script_path.read_bytes()
        assert actual_content == rendered_bytes, "Gold script has drifted from spec"
