import importlib
from unittest.mock import patch


def test_import_is_pure_and_column_detector_is_value_free():
    with patch("boto3.client") as client:
        module = importlib.import_module("shared.utils.pii_detection_and_tagging")
        client.assert_not_called()

    assert module.detect_pii_by_column_name("customer_email") == [("EMAIL", "HIGH")]
    assert module.detect_pii_by_column_name("order_id") == []
