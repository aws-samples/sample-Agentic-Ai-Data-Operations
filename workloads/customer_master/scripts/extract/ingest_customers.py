"""
ingest_customers.py — Extract customer CSV and upload to S3 Bronze zone.

Bronze zone is immutable: each ingestion creates a new partition by date.
No transformations applied — raw data preserved as-is.
"""

import csv
import hashlib
import io
import logging
import os
from datetime import datetime, timezone
from typing import Any, List, Dict, Optional

logger = logging.getLogger(__name__)

# Configuration — no hardcoded secrets
S3_BUCKET = os.environ.get(
    "S3_BUCKET", "aws-glue-assets-123456789012-us-east-1"
)
BRONZE_PREFIX = os.environ.get(
    "BRONZE_PREFIX", "demo-ai-agents/bronze/customers"
)
LOCAL_CSV_PATH = os.environ.get(
    "LOCAL_CSV_PATH",
    os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "shared", "fixtures", "customers.csv"
    ),
)

EXPECTED_COLUMNS = [
    "customer_id", "name", "email", "phone", "segment",
    "industry", "country", "status", "join_date",
    "annual_value", "credit_limit",
]


def read_csv(file_path: str) -> List[Dict[str, Any]]:
    """Read CSV file and return list of row dicts."""
    abs_path = os.path.abspath(file_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Source CSV not found: {abs_path}")

    with open(abs_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Validate header
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        missing = set(EXPECTED_COLUMNS) - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV missing expected columns: {missing}")
        rows = list(reader)

    logger.info("Read %d rows from %s", len(rows), abs_path)
    return rows


def compute_checksum(rows: List[Dict[str, Any]]) -> str:
    """Compute SHA-256 checksum of the data for audit."""
    h = hashlib.sha256()
    for row in rows:
        h.update(str(sorted(row.items())).encode("utf-8"))
    return h.hexdigest()


def rows_to_csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    """Convert row dicts back to CSV bytes for upload."""
    if not rows:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EXPECTED_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def upload_to_s3(
    csv_bytes: bytes,
    bucket: str,
    prefix: str,
    filename: str = "customers.csv",
) -> str:
    """Upload CSV bytes to S3. Returns the S3 key."""
    import boto3

    s3 = boto3.client("s3")
    key = f"{prefix}/{filename}"
    s3.put_object(Bucket=bucket, Key=key, Body=csv_bytes)
    s3_uri = f"s3://{bucket}/{key}"
    logger.info("Uploaded to %s", s3_uri)
    return s3_uri


def ingest(
    file_path: Optional[str] = None,
    upload: bool = True,
) -> Dict[str, Any]:
    """
    Main ingestion entry point.

    Returns audit record with row count, checksum, and S3 URI.
    """
    src = file_path or LOCAL_CSV_PATH
    rows = read_csv(src)
    checksum = compute_checksum(rows)
    csv_bytes = rows_to_csv_bytes(rows)

    result: Dict[str, Any] = {
        "source_file": os.path.abspath(src),
        "row_count": len(rows),
        "column_count": len(EXPECTED_COLUMNS),
        "checksum_sha256": checksum,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "agent": "ingest_customers",
    }

    if upload:
        s3_uri = upload_to_s3(csv_bytes, S3_BUCKET, BRONZE_PREFIX)
        result["s3_uri"] = s3_uri
    else:
        result["s3_uri"] = None
        logger.info("Upload skipped (upload=False)")

    logger.info("Ingestion complete: %d rows, checksum=%s", len(rows), checksum[:12])
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = ingest(upload=True)
    print(result)
