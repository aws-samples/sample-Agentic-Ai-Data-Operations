from pathlib import Path

from shared.codegen.spec_loader import load_spec
from shared.metadata.semantic_reader import validate_semantic_yaml
import yaml


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "config" / "source.yaml"
SEMANTIC = ROOT / "config" / "semantic.yaml"


def test_source_yaml_matches_v1_contract():
    spec, spec_hash = load_spec(SOURCE, "source")

    assert spec_hash
    assert spec["dataset_name"] == "customer_orders"
    assert spec["compliance"] == "GDPR"


def test_semantic_yaml_matches_reader_contract():
    semantic = yaml.safe_load(SEMANTIC.read_text())

    assert validate_semantic_yaml(semantic) is True
    assert semantic["ontology_opt_in"] is False


def test_confirmed_pii_and_raw_pan_boundary_are_explicit():
    source = yaml.safe_load(SOURCE.read_text())
    columns = {column["name"]: column for column in source["schema"]["columns"]}

    confirmed_pii = {
        "customer_email",
        "customer_phone",
        "credit_card_number",
        "customer_name",
        "shipping_address",
        "city",
        "state",
        "zip_code",
    }
    assert {name for name, column in columns.items() if column.get("phi")} == confirmed_pii

    semantic = yaml.safe_load(SEMANTIC.read_text())
    semantic_columns = {
        column["name"]
        for table in semantic["tables"]
        for column in table["columns"]
    }
    assert "credit_card_number" not in semantic_columns
    assert "credit_card_token" not in semantic_columns


def test_gold_semantic_columns_match_final_physical_contract():
    semantic = yaml.safe_load(SEMANTIC.read_text())

    assert [
        column["name"] for column in semantic["tables"][0]["columns"]
    ] == [
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
    ]


def test_gold_semantic_columns_exclude_non_exposed_pii_and_token():
    semantic = yaml.safe_load(SEMANTIC.read_text())
    gold_columns = {
        column["name"]
        for table in semantic["tables"]
        for column in table["columns"]
    }

    assert gold_columns.isdisjoint(
        {
            "customer_email",
            "customer_phone",
            "customer_name",
            "shipping_address",
            "city",
            "state",
            "zip_code",
            "credit_card_token",
        }
    )
    assert semantic["controls"]["credit_card_token"]["gold_exposure"] == "suppressed"
