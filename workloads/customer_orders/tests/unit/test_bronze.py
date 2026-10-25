from pathlib import Path

import yaml

from shared.codegen.spec_loader import load_spec


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
BRONZE_SCRIPT = ROOT / "scripts" / "extract" / "bronze_ingestion.py"


def test_bronze_spec_matches_authoritative_csv_and_iam_source():
    bronze, _ = load_spec(CONFIG / "bronze.yaml", "bronze")
    source = yaml.safe_load((CONFIG / "source.yaml").read_text())

    assert bronze["dataset_name"] == source["dataset_name"] == "customer_orders"
    assert bronze["source_path"] == source["source"]["location"]["production"]
    assert bronze["source_format"] == source["source"]["format"] == "csv"
    assert source["source"]["credentials"]["type"] == "iam_role"
    assert bronze["ingestion_mode"] == "full_load"
    assert bronze["schema_version"] == "v2"
    assert bronze["catalog_database"] == "customer_orders_db"
    assert bronze["catalog_table"] == "bronze_customer_orders"
    assert bronze["idempotency_key"] == "source_path"
    assert bronze["retention"]["days"] == 365
    assert bronze["landing_zone"] == "s3://${DATA_LAKE_BUCKET}/bronze/customer_orders/"


def test_rendered_bronze_job_uses_catalog_idempotency_and_preserves_raw_duplicates():
    text = BRONZE_SCRIPT.read_text()

    compile(text, str(BRONZE_SCRIPT), "exec")
    assert "StructuredLogger" in text
    assert 'run_id="local"' in text
    assert 'logger.context["run_id"]' in text
    assert '"ADOP_RUN_ID"' in text
    assert '"CUSTOMER_ORDERS_SOURCE_URI"' in text
    assert '"DATA_LAKE_BUCKET"' in text
    assert 'table_name = "glue_catalog.customer_orders_db.bronze_customer_orders"' in text
    assert '.writeTo(table_name).using("iceberg").overwritePartitions()' in text
    assert '.partitionedBy(F.col("_adop_source_run_id"))' in text
    assert "dropDuplicates" not in text
    assert '.mode("append")' not in text
    assert '.save(landing_zone)' not in text
    assert "arn:aws:" not in text
