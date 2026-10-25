import re
from pathlib import Path

import yaml

from shared.codegen.spec_loader import load_spec
from shared.metadata.semantic_reader import validate_semantic_yaml


WORKLOAD = Path(__file__).resolve().parents[2]
SOURCE_PATH = WORKLOAD / "config" / "source.yaml"
SEMANTIC_PATH = WORKLOAD / "config" / "semantic.yaml"


def test_source_and_semantic_specs_agree_on_workload_and_pk():
    source, _ = load_spec(SOURCE_PATH, "source")
    semantic = yaml.safe_load(SEMANTIC_PATH.read_text())

    assert source["dataset_name"] == semantic["workload"] == "customer_orders"
    assert source["schema"]["columns"][0]["name"] == "order_id"
    assert semantic["tables"][0]["primary_key"] == "order_id"
    assert validate_semantic_yaml(semantic) is True


def test_specs_contain_no_recorded_account_or_bucket_identifier():
    source_text = SOURCE_PATH.read_text()
    semantic_text = SEMANTIC_PATH.read_text()
    semantic = yaml.safe_load(semantic_text)
    semantic_columns = {
        column["name"]
        for table in semantic["tables"]
        for column in table["columns"]
    }

    assert not re.search(r"\b\d{12}\b", source_text + semantic_text)  # no AWS account IDs
    assert "arn:aws:" not in source_text + semantic_text
    assert "credit_card_number" in source_text
    assert "credit_card_number" not in semantic_columns
    assert semantic["controls"]["credit_card_number"]["target"] == "credit_card_token"


def test_semantic_gold_contract_and_token_suppression_are_aligned():
    semantic = yaml.safe_load(SEMANTIC_PATH.read_text())
    table = semantic["tables"][0]
    expected_columns = [
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

    assert table["physical_table"] == "gold_customer_orders"
    assert [column["name"] for column in table["columns"]] == expected_columns
    assert semantic["compliance"] == "GDPR"
    assert semantic["controls"]["credit_card_token"] == {
        "gold_exposure": "suppressed",
        "suppression_reason": (
            "Tokenized payment references are not exposed in the final Gold physical table."
        ),
    }
