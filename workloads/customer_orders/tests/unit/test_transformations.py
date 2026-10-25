import hashlib
import json
from pathlib import Path

import yaml

from shared.codegen.spec_loader import compute_spec_hash, load_spec


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
TRANSFORM = ROOT / "scripts" / "transform"


def _header(path: Path) -> dict[str, str]:
    lines = path.read_text().splitlines()[:5]
    return {
        line.split(": ", 1)[0].removeprefix("# "): line.split(": ", 1)[1]
        for line in lines
    }


def test_silver_spec_is_valid_and_has_fail_closed_tokenization():
    spec, spec_hash = load_spec(CONFIG / "silver.yaml", "silver")
    token = next(
        item for item in spec["pii_masking"]["columns"]
        if item["name"] == "credit_card_number"
    )

    assert spec_hash == _header(CONFIG / "silver.yaml")["spec_hash"]
    assert spec["dedup_strategy"] == "none"
    assert spec["null_handling"]["strategy"] == "quarantine"
    assert spec["quality_threshold"] == 0.8
    assert token["method"] == "tokenize"
    assert token["target_column"] == "credit_card_token"
    assert token["token_secret_id"] == "${CUSTOMER_ORDERS_TOKEN_SECRET_ID}"
    assert "credit_card_number" in spec["drop_columns"]
    assert "last_four" not in json.dumps(spec)


def test_gold_spec_is_valid_and_matches_the_silver_target():
    silver, _ = load_spec(CONFIG / "silver.yaml", "silver")
    gold, gold_hash = load_spec(CONFIG / "gold.yaml", "gold", "v2")

    assert gold_hash == _header(CONFIG / "gold.yaml")["spec_hash"]
    assert gold["source_table"] == (
        f"glue_catalog.{silver['iceberg_database']}.{silver['iceberg_table']}"
    )
    assert gold["schema_type"] == "flat_iceberg"
    assert gold["grain"] == {"dimensions": ["order_id"], "temporal": "none"}
    assert [(m["name"], m["aggregation"]) for m in gold["measures"]] == [
        ("order_count", "count"),
        ("revenue", "sum"),
        ("customer_id", "first_value"),
        ("product_id", "first_value"),
        ("order_date", "first_value"),
        ("ship_date", "first_value"),
        ("quantity", "first_value"),
        ("unit_price", "first_value"),
        ("discount_pct", "first_value"),
        ("payment_method", "first_value"),
        ("order_status", "first_value"),
        ("data_subject_id", "first_value"),
        ("consent_given", "first_value"),
        ("consent_timestamp", "first_value"),
        ("is_deleted", "first_value"),
        ("deletion_requested_at", "first_value"),
    ]
    assert gold["quality_threshold"] == 0.95


def test_transform_config_is_renderer_output_and_preserves_human_rules():
    config = yaml.safe_load((CONFIG / "transformations.yaml").read_text())
    header = _header(CONFIG / "transformations.yaml")
    body = json.dumps(config, sort_keys=True, separators=(",", ":"))
    expected_hash = hashlib.sha256(
        json.dumps(
            {
                "dataset_name": "customer_orders",
                "schema_version": "v1",
                "compliance": "GDPR",
                "silver": config["silver"],
                "gold": config["gold"],
                "security": config["security"],
                "gdpr_demo_controls": config["gdpr_demo_controls"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    assert header["template_id"] == "transformations"
    assert header["spec_hash"] == expected_hash
    assert config["silver"]["zone_behavior"] == "type_1"
    assert config["silver"]["deduplication"]["strategy"] == "none"
    assert config["silver"]["deduplication"]["duplicate_action"] == "block_promotion"
    assert config["silver"]["quality_gate"] == 0.8
    assert config["gold"]["quality_gate"] == 0.95
    assert config["security"]["pan_retained"] is False
    assert config["security"]["last_four_retained"] is False


def test_rendered_transform_scripts_compile_and_drop_pan():
    silver_text = (TRANSFORM / "bronze_to_silver.py").read_text()
    gold_text = (TRANSFORM / "silver_to_gold.py").read_text()

    compile(silver_text, "bronze_to_silver.py", "exec")
    compile(gold_text, "silver_to_gold.py", "exec")
    assert 'target_column' not in silver_text
    assert "from shared.utils.pii_detection_and_tagging import detect_pii_by_column_name" in silver_text
    assert "def _log_pii_inventory(df):" in silver_text
    assert "_log_pii_inventory(final_df)" in silver_text
    assert silver_text.index("_log_pii_inventory(final_df)") < silver_text.index("final_df.writeTo(table_name)")
    assert '"ADOP_RUN_ID"' in silver_text
    assert 'run_id="standalone"' not in silver_text
    assert 'F.lit(_token_secret(_resolve("${CUSTOMER_ORDERS_TOKEN_SECRET_ID}"' in silver_text
    assert 'final_df = derived_df.drop("credit_card_number")' in silver_text
    assert "last_four" not in silver_text
    assert 'F.count("order_id").alias("order_count")' in gold_text
    assert 'F.sum("revenue").alias("revenue")' in gold_text
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
    ):
        assert f'F.first("{column}", ignorenulls=True).alias("{column}")' in gold_text
    assert 'F.first("data_subject_id", ignorenulls=True).alias("data_subject_id")' in gold_text
    assert 'F.first("consent_given", ignorenulls=True).alias("consent_given")' in gold_text
    assert 'F.first("consent_timestamp", ignorenulls=True).alias("consent_timestamp")' in gold_text
    assert 'F.first("is_deleted", ignorenulls=True).alias("is_deleted")' in gold_text
    assert 'F.first("deletion_requested_at", ignorenulls=True).alias("deletion_requested_at")' in gold_text
    assert "from shared.utils.pii_detection_and_tagging import detect_pii_by_column_name" in gold_text
    assert "def _log_pii_inventory(df):" in gold_text
    assert "_log_pii_inventory(gold_df)" in gold_text
    assert gold_text.index("_log_pii_inventory(gold_df)") < gold_text.index("gold_df.writeTo(table_name)")
    assert '"ADOP_RUN_ID"' in gold_text
    assert 'run_id="standalone"' not in gold_text
    assert "credit_card_number" not in gold_text
    assert "customer_email" not in gold_text

