"""
bronze_to_gold.py — Transform customer data from Bronze (raw CSV) to Gold (star schema).

Pipeline steps:
  1. Read Bronze CSV
  2. Deduplicate on customer_id (keep first)
  3. Quarantine null PKs and invalid enums
  4. PII masking: email -> SHA-256, phone -> mask all but last 4
  5. Type casting: annual_value/credit_limit -> float, join_date validated
  6. Build star schema: customer_fact, dim_segment, dim_country, dim_status, summary

All transformations are idempotent — running twice produces identical output.
Quarantined records are written separately, never dropped silently.
"""

import csv
import hashlib
import io
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKLOAD_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
PROJECT_DIR = os.path.abspath(os.path.join(WORKLOAD_DIR, "..", ".."))
LOCAL_CSV_PATH = os.path.join(PROJECT_DIR, "shared", "fixtures", "customers.csv")
GOLD_OUTPUT_DIR = os.path.join(WORKLOAD_DIR, "output", "gold")

# S3 config
S3_BUCKET = os.environ.get("S3_BUCKET", "aws-glue-assets-123456789012-us-east-1")
GOLD_PREFIX = os.environ.get("GOLD_PREFIX", "demo-ai-agents/gold/customers")

# Enum sets
VALID_SEGMENTS = {"Enterprise", "SMB", "Individual"}
VALID_STATUSES = {"Active", "Inactive", "Churned"}
VALID_COUNTRIES = {"US", "UK", "CA", "DE"}

COUNTRY_NAMES = {
    "US": "United States",
    "UK": "United Kingdom",
    "CA": "Canada",
    "DE": "Germany",
}

EXPECTED_COLUMNS = [
    "customer_id", "name", "email", "phone", "segment",
    "industry", "country", "status", "join_date",
    "annual_value", "credit_limit",
]


# ---------------------------------------------------------------------------
# Step 1: Read Bronze
# ---------------------------------------------------------------------------

def read_bronze(file_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read raw CSV from Bronze zone."""
    src = file_path or LOCAL_CSV_PATH
    src = os.path.abspath(src)
    if not os.path.isfile(src):
        raise FileNotFoundError(f"Bronze CSV not found: {src}")
    with open(src, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    logger.info("Read %d Bronze rows from %s", len(rows), src)
    return rows


# ---------------------------------------------------------------------------
# Step 2: Deduplicate
# ---------------------------------------------------------------------------

def deduplicate(rows: List[Dict[str, Any]]) -> Tuple[List[dict], List[dict]]:
    """Deduplicate on customer_id, keep first occurrence. Return (clean, dupes)."""
    seen = set()  # type: set
    clean = []  # type: List[dict]
    dupes = []  # type: List[dict]
    for row in rows:
        cid = row.get("customer_id", "").strip()
        if cid in seen:
            dupes.append({**row, "_quarantine_reason": f"duplicate customer_id={cid}"})
        else:
            seen.add(cid)
            clean.append(row)
    logger.info("Dedup: %d clean, %d duplicates", len(clean), len(dupes))
    return clean, dupes


# ---------------------------------------------------------------------------
# Step 3: Quarantine invalid rows
# ---------------------------------------------------------------------------

def validate_rows(rows: List[Dict[str, Any]]) -> Tuple[List[dict], List[dict]]:
    """Validate PKs, enums, types. Quarantine invalid rows."""
    clean = []  # type: List[dict]
    quarantined = []  # type: List[dict]

    pk_pattern = re.compile(r"^CUST-\d{3}$")

    for row in rows:
        reasons = []  # type: List[str]
        cid = row.get("customer_id", "").strip()

        # PK checks
        if not cid:
            reasons.append("null customer_id")
        elif not pk_pattern.match(cid):
            reasons.append(f"invalid customer_id format: {cid}")

        # Required fields
        if not row.get("name", "").strip():
            reasons.append("null name")

        # Enum checks
        seg = row.get("segment", "").strip()
        if seg and seg not in VALID_SEGMENTS:
            reasons.append(f"invalid segment: {seg}")
        elif not seg:
            reasons.append("null segment")

        status = row.get("status", "").strip()
        if status and status not in VALID_STATUSES:
            reasons.append(f"invalid status: {status}")
        elif not status:
            reasons.append("null status")

        country = row.get("country", "").strip()
        if country and country not in VALID_COUNTRIES:
            reasons.append(f"invalid country: {country}")
        elif not country:
            reasons.append("null country")

        # Type casting validation
        for col in ("annual_value", "credit_limit"):
            val = row.get(col, "").strip()
            if val:
                try:
                    float(val)
                except ValueError:
                    reasons.append(f"non-numeric {col}: {val}")

        join_date = row.get("join_date", "").strip()
        if join_date:
            try:
                datetime.strptime(join_date, "%Y-%m-%d")
            except ValueError:
                reasons.append(f"invalid join_date: {join_date}")
        elif not join_date:
            reasons.append("null join_date")

        if reasons:
            quarantined.append({**row, "_quarantine_reason": "; ".join(reasons)})
        else:
            clean.append(row)

    logger.info("Validation: %d clean, %d quarantined", len(clean), len(quarantined))
    return clean, quarantined


# ---------------------------------------------------------------------------
# Step 4: PII masking
# ---------------------------------------------------------------------------

def hash_email(email: Optional[str]) -> Optional[str]:
    """SHA-256 hash of email. Returns None if input is null/empty."""
    if not email or not email.strip():
        return None
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def mask_phone(phone: Optional[str]) -> Optional[str]:
    """Mask all but last 4 digits. Returns None if null/empty."""
    if not phone or not phone.strip():
        return None
    digits = re.sub(r"\D", "", phone.strip())
    if len(digits) <= 4:
        return digits
    masked = "*" * (len(digits) - 4) + digits[-4:]
    return masked


def apply_pii_masking(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply PII masking. email -> hash, phone -> masked."""
    result = []
    for row in rows:
        r = dict(row)
        r["email_hash"] = hash_email(r.get("email"))
        r["phone_masked"] = mask_phone(r.get("phone"))
        result.append(r)
    logger.info("PII masking applied to %d rows", len(result))
    return result


# ---------------------------------------------------------------------------
# Step 5: Type casting
# ---------------------------------------------------------------------------

def cast_types(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cast annual_value/credit_limit to float. Already validated."""
    result = []
    for row in rows:
        r = dict(row)
        av = r.get("annual_value", "").strip() if r.get("annual_value") else ""
        cl = r.get("credit_limit", "").strip() if r.get("credit_limit") else ""
        r["annual_value"] = round(float(av), 2) if av else 0.0
        r["credit_limit"] = round(float(cl), 2) if cl else 0.0
        result.append(r)
    return result


# ---------------------------------------------------------------------------
# Step 6: Build star schema
# ---------------------------------------------------------------------------

def build_customer_fact(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build customer_fact table from transformed rows."""
    fact_rows = []
    for row in rows:
        fact_rows.append({
            "customer_id": row["customer_id"].strip(),
            "name": row["name"].strip(),
            "email_hash": row.get("email_hash"),
            "phone_masked": row.get("phone_masked"),
            "segment": row["segment"].strip(),
            "industry": row.get("industry", "").strip(),
            "country_code": row["country"].strip(),
            "status": row["status"].strip(),
            "join_date": row["join_date"].strip(),
            "annual_value": row["annual_value"],
            "credit_limit": row["credit_limit"],
        })
    return fact_rows


def build_dim_segment(fact_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build dim_segment from distinct segments."""
    segments = sorted({r["segment"] for r in fact_rows})
    return [
        {"segment_id": i + 1, "segment_name": s}
        for i, s in enumerate(segments)
    ]


def build_dim_country(fact_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build dim_country from distinct countries."""
    countries = sorted({r["country_code"] for r in fact_rows})
    return [
        {"country_code": c, "country_name": COUNTRY_NAMES.get(c, c)}
        for c in countries
    ]


def build_dim_status(fact_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build dim_status from distinct statuses."""
    statuses = sorted({r["status"] for r in fact_rows})
    return [
        {"status_id": i + 1, "status_name": s}
        for i, s in enumerate(statuses)
    ]


def build_summary_by_segment(fact_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build pre-aggregated summary by segment."""
    seg_data = {}  # type: Dict[str, List[dict]]
    for r in fact_rows:
        seg_data.setdefault(r["segment"], []).append(r)

    summary = []
    for seg in sorted(seg_data.keys()):
        rows_in_seg = seg_data[seg]
        vals = [r["annual_value"] for r in rows_in_seg]
        summary.append({
            "segment": seg,
            "customer_count": len(rows_in_seg),
            "total_annual_value": round(sum(vals), 2),
            "avg_annual_value": round(sum(vals) / len(vals), 2) if vals else 0.0,
            "total_credit_limit": round(
                sum(r["credit_limit"] for r in rows_in_seg), 2
            ),
        })
    return summary


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def write_csv_file(rows: List[Dict[str, Any]], filepath: str) -> str:
    """Write list of dicts to CSV file."""
    if not rows:
        logger.warning("No rows to write for %s", filepath)
        return filepath
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %d rows to %s", len(rows), filepath)
    return filepath


def rows_to_csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    """Convert rows to CSV bytes for S3 upload."""
    if not rows:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def upload_to_s3(csv_bytes: bytes, bucket: str, key: str) -> str:
    """Upload bytes to S3."""
    import boto3
    s3 = boto3.client("s3")
    s3.put_object(Bucket=bucket, Key=key, Body=csv_bytes)
    uri = f"s3://{bucket}/{key}"
    logger.info("Uploaded to %s", uri)
    return uri


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def transform(
    file_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    upload: bool = False,
) -> Dict[str, Any]:
    """
    Run full Bronze-to-Gold transformation pipeline.

    Args:
        file_path: Path to Bronze CSV (default: shared/fixtures/customers.csv)
        output_dir: Local directory for Gold CSVs (default: workload output/gold/)
        upload: If True, upload Gold CSVs to S3

    Returns:
        Audit record with counts, file paths, and metadata
    """
    out_dir = output_dir or GOLD_OUTPUT_DIR
    started = datetime.now(timezone.utc)

    # Step 1: Read
    bronze_rows = read_bronze(file_path)

    # Step 2: Dedup
    deduped, dupes = deduplicate(bronze_rows)

    # Step 3: Validate
    valid, quarantined = validate_rows(deduped)

    # Combine quarantine
    all_quarantined = dupes + quarantined

    # Step 4: PII masking
    masked = apply_pii_masking(valid)

    # Step 5: Type casting
    casted = cast_types(masked)

    # Step 6: Build star schema
    fact_rows = build_customer_fact(casted)
    dim_segment = build_dim_segment(fact_rows)
    dim_country = build_dim_country(fact_rows)
    dim_status = build_dim_status(fact_rows)
    summary = build_summary_by_segment(fact_rows)

    # Write local files
    tables = {
        "customer_fact": fact_rows,
        "dim_segment": dim_segment,
        "dim_country": dim_country,
        "dim_status": dim_status,
        "customer_summary_by_segment": summary,
    }

    local_files = {}
    for name, data in tables.items():
        path = write_csv_file(data, os.path.join(out_dir, f"{name}.csv"))
        local_files[name] = path

    # Write quarantine
    if all_quarantined:
        q_path = write_csv_file(
            all_quarantined,
            os.path.join(out_dir, "quarantine", "quarantined_records.csv"),
        )
        local_files["quarantine"] = q_path

    # Upload to S3 if requested
    s3_uris = {}
    if upload:
        for name, data in tables.items():
            csv_bytes = rows_to_csv_bytes(data)
            key = f"{GOLD_PREFIX}/{name}/{name}.csv"
            s3_uris[name] = upload_to_s3(csv_bytes, S3_BUCKET, key)

    finished = datetime.now(timezone.utc)

    result = {
        "agent": "bronze_to_gold",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "bronze_row_count": len(bronze_rows),
        "duplicates_removed": len(dupes),
        "quarantined_count": len(all_quarantined),
        "gold_fact_row_count": len(fact_rows),
        "dim_segment_count": len(dim_segment),
        "dim_country_count": len(dim_country),
        "dim_status_count": len(dim_status),
        "summary_row_count": len(summary),
        "local_files": local_files,
        "s3_uris": s3_uris,
        "idempotent": True,
        "tables": tables,
    }
    logger.info(
        "Transform complete: %d bronze -> %d gold fact rows, %d quarantined",
        len(bronze_rows), len(fact_rows), len(all_quarantined),
    )
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = transform(upload=False)
    for k, v in result.items():
        if k not in ("local_files", "s3_uris", "tables"):
            print(f"  {k}: {v}")
    print("\nLocal files:")
    for name, path in result["local_files"].items():
        print(f"  {name}: {path}")
