import hashlib
from pathlib import Path

import yaml

from shared.codegen.drift_validator import parse_artifact_header
from shared.codegen.renderer import render_dry_run
from shared.codegen.spec_loader import load_spec


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
BRONZE_SCRIPT = ROOT / "scripts" / "extract" / "bronze_ingestion.py"


def test_bronze_spec_script_and_downstream_source_agree():
    bronze, spec_hash = load_spec(CONFIG / "bronze.yaml", "bronze", "v2")
    silver, _ = load_spec(CONFIG / "silver.yaml", "silver")
    source = yaml.safe_load((CONFIG / "source.yaml").read_text())
    script = BRONZE_SCRIPT.read_text()

    rendered, artifact_hash = render_dry_run(
        bronze,
        spec_hash,
        "bronze_ingestion",
            "1.7.0",
        "2026-10-22T18:18:44Z",
        schema_version="v2",
    )

    assert source["source"]["location"]["production"] == bronze["source_path"]
    assert silver["source_table"] == "glue_catalog.customer_orders_db.bronze_customer_orders"
    assert parse_artifact_header(script)["spec_hash"] == spec_hash
    assert hashlib.sha256(script.encode()).hexdigest() == artifact_hash
    assert rendered.decode() == script
    assert "glue_catalog.customer_orders_db.bronze_customer_orders" in script
    assert "overwritePartitions()" in script
    assert "scripts/extract/bronze_ingestion.py" in (
        (ROOT / "config" / "schedule.yaml").read_text()
    )
