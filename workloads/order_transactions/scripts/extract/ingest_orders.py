"""
Ingest orders CSV to S3 Bronze zone.

Reads orders.csv from local fixtures or specified path,
uploads to S3 Bronze location. No transformations applied - Bronze is immutable raw data.
"""

import csv
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Configuration - override via environment variables
S3_BUCKET = os.environ.get(
    "S3_BUCKET", "aws-glue-assets-123456789012-us-east-1"
)
BRONZE_PREFIX = os.environ.get(
    "BRONZE_PREFIX", "demo-ai-agents/bronze/orders/"
)
LOCAL_SOURCE = os.environ.get(
    "LOCAL_SOURCE",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "shared", "fixtures", "orders.csv"),
)


def validate_source_file(filepath: str) -> dict:
    """Validate the source CSV file before ingestion.

    Returns a dict with row_count, column_count, columns, and any issues found.
    """
    issues = []
    filepath = os.path.abspath(filepath)

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Source file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        expected_columns = [
            "order_id", "customer_id", "order_date", "product_name",
            "category", "quantity", "unit_price", "discount_pct",
            "revenue", "status", "region",
        ]

        missing = set(expected_columns) - set(columns)
        if missing:
            issues.append(f"Missing columns: {missing}")

        rows = list(reader)
        row_count = len(rows)

        # Check for null PKs
        null_pks = sum(1 for r in rows if not r.get("order_id", "").strip())
        if null_pks > 0:
            issues.append(f"Null order_id found in {null_pks} rows")

    return {
        "filepath": filepath,
        "row_count": row_count,
        "column_count": len(columns),
        "columns": columns,
        "issues": issues,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }


def read_source_csv(filepath: str) -> list[dict]:
    """Read the source CSV and return list of row dicts."""
    filepath = os.path.abspath(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def upload_to_s3(filepath: str, bucket: str, key: str) -> dict:
    """Upload a file to S3 using boto3.

    Returns metadata about the upload.
    """
    import boto3

    s3 = boto3.client("s3")
    s3.upload_file(filepath, bucket, key)
    logger.info("Uploaded %s to s3://%s/%s", filepath, bucket, key)

    return {
        "bucket": bucket,
        "key": key,
        "source": filepath,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


def ingest(source_path: str = None) -> dict:
    """Main ingestion entry point.

    1. Validate source file
    2. Upload to S3 Bronze zone
    3. Return ingestion metadata
    """
    source = os.path.abspath(source_path or LOCAL_SOURCE)
    validation = validate_source_file(source)

    if validation["issues"]:
        logger.warning("Source validation issues: %s", validation["issues"])

    filename = os.path.basename(source)
    s3_key = f"{BRONZE_PREFIX}{filename}"

    result = upload_to_s3(source, S3_BUCKET, s3_key)
    result["validation"] = validation
    result["zone"] = "bronze"
    result["workload"] = "order_transactions"

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = ingest()
    print(f"Ingested {result['validation']['row_count']} rows to s3://{result['bucket']}/{result['key']}")
