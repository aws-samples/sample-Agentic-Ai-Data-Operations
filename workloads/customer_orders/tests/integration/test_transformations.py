import re
from pathlib import Path

import yaml

from shared.codegen.spec_loader import load_spec


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
SCRIPTS = ROOT / "scripts" / "transform"
SQL = ROOT / "sql"


def test_specs_scripts_quality_and_semantic_metadata_agree():
    silver, _ = load_spec(CONFIG / "silver.yaml", "silver")
    gold, _ = load_spec(CONFIG / "gold.yaml", "gold", "v2")
    source = yaml.safe_load((CONFIG / "source.yaml").read_text())
    semantic = yaml.safe_load((CONFIG / "semantic.yaml").read_text())
    quality = yaml.safe_load((CONFIG / "quality_rules.yaml").read_text())
    silver_script = (SCRIPTS / "bronze_to_silver.py").read_text()
    gold_script = (SCRIPTS / "silver_to_gold.py").read_text()

    assert source["dataset_name"] == silver["dataset_name"] == gold["dataset_name"]
    assert semantic["tables"][0]["physical_table"] == "gold_customer_orders"
    assert gold["iceberg_table"] == semantic["tables"][0]["physical_table"]
    assert gold["source_table"] == (
        f"glue_catalog.{silver['iceberg_database']}.{silver['iceberg_table']}"
    )
    assert quality["quality_gates"]["bronze_to_silver"]["overall_score"] == 0.8
    assert quality["quality_gates"]["silver_to_gold"]["overall_score"] == 0.95
    assert "order_id" in silver_script
    assert "credit_card_token" in silver_script
    assert "silver_customer_orders" in gold_script
    assert "gold_customer_orders" in gold_script
    for column in (
        "customer_id",
        "product_id",
        "order_date",
        "ship_date",
        "quantity",
        "unit_price",
        "discount_pct",
        "payment_method",
        "order_status",
        "data_subject_id",
        "consent_given",
        "consent_timestamp",
        "is_deleted",
        "deletion_requested_at",
    ):
        assert column in gold_script
    assert "credit_card_number" not in gold_script
    assert "credit_card_token" not in gold_script
    assert "customer_email" not in gold_script

    ddl = yaml.safe_load((CONFIG / "gold_ddl.yaml").read_text())
    gold_columns = {
        column["name"]
        for table in ddl["tables"]
        for column in table["columns"]
    }
    assert gold_columns == {
        "order_id",
        "order_count",
        "revenue",
        "customer_id",
        "product_id",
        "order_date",
        "ship_date",
        "quantity",
        "unit_price",
        "discount_pct",
        "payment_method",
        "order_status",
        "data_subject_id",
        "consent_given",
        "consent_timestamp",
        "is_deleted",
        "deletion_requested_at",
    }
    assert not gold_columns.intersection({
        "customer_email",
        "customer_phone",
        "customer_name",
        "shipping_address",
        "city",
        "state",
        "zip_code",
        "credit_card_number",
        "credit_card_token",
    })


def test_rendered_sql_is_zone_specific_and_has_only_deployment_placeholders():
    silver_sql = (SQL / "silver" / "customer_orders.sql").read_text()
    gold_sql = (SQL / "gold" / "customer_orders.sql").read_text()

    assert "customer_orders_db.silver_customer_orders" in silver_sql
    assert "customer_orders_db.gold_customer_orders" in gold_sql
    assert "s3://${DATA_LAKE_BUCKET}/" in silver_sql
    assert "s3://${DATA_LAKE_BUCKET}/" in gold_sql
    assert "s3://data-lake/" not in silver_sql + gold_sql
    assert not re.search(r"arn:aws:[^'\" ]+", silver_sql + gold_sql)


def test_generated_artifacts_have_five_line_provenance_headers():
    paths = [
        CONFIG / "silver.yaml",
        CONFIG / "gold.yaml",
        CONFIG / "transformations.yaml",
        SCRIPTS / "bronze_to_silver.py",
        SCRIPTS / "silver_to_gold.py",
        SQL / "silver" / "customer_orders.sql",
        SQL / "gold" / "customer_orders.sql",
    ]

    for path in paths:
        lines = path.read_text().splitlines()[:5]
        assert len(lines) == 5
        assert "spec_hash:" in lines[0]
        assert "template_id:" in lines[1]
        assert "template_hash:" in lines[2]
        assert "schema_version:" in lines[3]
        assert "rendered_at: 2026-10-22T18:18:44Z" in lines[4]

