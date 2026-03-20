"""
ingest_daily_sales.py -- Bronze zone ingestion script for daily_sales workload.

Reads a CSV from the source path, validates that all expected columns exist,
and writes a copy to the Bronze output path (immutable, write-once).

Usage:
    python3 ingest_daily_sales.py --input <source_csv> --output <bronze_dir>
"""

import argparse
import csv
import os
import shutil
import sys
from datetime import datetime, timezone
from typing import Dict, List

EXPECTED_COLUMNS = [
    "sale_id", "sale_date", "store_id", "store_name",
    "customer_name", "customer_email", "product_sku", "product_name",
    "category", "quantity", "unit_price", "discount_pct",
    "total_amount", "payment_method", "region",
]


def validate_columns(file_path: str) -> Dict:
    """Read CSV header and validate all expected columns are present.
    Returns dict with status, columns found, and any missing columns."""
    file_path = os.path.abspath(file_path)
    if not os.path.isfile(file_path):
        return {
            "status": "error",
            "message": f"File not found: {file_path}",
            "columns_found": [],
            "columns_missing": EXPECTED_COLUMNS,
        }

    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return {
                "status": "error",
                "message": "CSV file has no header row",
                "columns_found": [],
                "columns_missing": EXPECTED_COLUMNS,
            }
        actual = list(reader.fieldnames)

    actual_set = set(actual)
    missing = [c for c in EXPECTED_COLUMNS if c not in actual_set]
    extra = [c for c in actual if c not in set(EXPECTED_COLUMNS)]

    if missing:
        return {
            "status": "error",
            "message": f"Missing columns: {missing}",
            "columns_found": actual,
            "columns_missing": missing,
            "columns_extra": extra,
        }

    return {
        "status": "ok",
        "message": f"All {len(EXPECTED_COLUMNS)} expected columns present",
        "columns_found": actual,
        "columns_missing": [],
        "columns_extra": extra,
    }


def count_rows(file_path: str) -> int:
    """Count data rows in CSV (excluding header)."""
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        return sum(1 for _ in reader)


def ingest(input_path: str, output_dir: str) -> Dict:
    """Validate and copy CSV to Bronze zone. Returns ingestion summary."""
    input_path = os.path.abspath(input_path)
    output_dir = os.path.abspath(output_dir)

    # Validate
    validation = validate_columns(input_path)
    if validation["status"] != "ok":
        return {
            "status": "failed",
            "validation": validation,
        }

    row_count = count_rows(input_path)

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Copy file to Bronze (immutable write-once)
    filename = os.path.basename(input_path)
    output_path = os.path.join(output_dir, filename)
    shutil.copy2(input_path, output_path)

    return {
        "status": "success",
        "source": input_path,
        "destination": output_path,
        "row_count": row_count,
        "column_count": len(EXPECTED_COLUMNS),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "validation": validation,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Ingest daily_sales CSV into Bronze zone"
    )
    parser.add_argument(
        "--input", dest="input_path", required=True,
        help="Path to source CSV file",
    )
    parser.add_argument(
        "--output", dest="output_dir", required=True,
        help="Bronze zone output directory",
    )
    args = parser.parse_args()

    result = ingest(args.input_path, args.output_dir)

    if result["status"] != "success":
        print(f"Ingestion FAILED: {result['validation']['message']}", file=sys.stderr)
        sys.exit(1)

    print(f"Ingestion SUCCESS: {result['row_count']} rows -> {result['destination']}")


if __name__ == "__main__":
    main()
