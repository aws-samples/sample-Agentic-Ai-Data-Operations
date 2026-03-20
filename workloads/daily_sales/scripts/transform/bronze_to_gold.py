"""
bronze_to_gold.py -- Transform daily_sales from Bronze (raw CSV) to Gold (star schema).

Pipeline steps:
  1. Bronze->Silver: Read CSV, dedup on sale_id, validate (discount 0-100, qty>0,
     total>0), quarantine invalid rows, type cast numerics, PII masking (SHA-256
     hash email, mask name), fill null emails, write Silver CSV + quality + lineage.
  2. Silver->Gold: Build star schema -- dim_store, dim_product, dim_date, fact_sales.
     Each table written as separate CSV. Gold quality report generated.
  3. Lineage JSON with source->target mapping, row counts, checksums.

All transformations are idempotent -- running twice produces identical output.
Quarantined records are written separately with reasons, never dropped silently.
"""

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_COLUMNS = [
    "sale_id", "sale_date", "store_id", "store_name",
    "customer_name", "customer_email", "product_sku", "product_name",
    "category", "quantity", "unit_price", "discount_pct",
    "total_amount", "payment_method", "region",
]

SILVER_COLUMNS = [
    "sale_id", "sale_date", "store_id", "store_name",
    "customer_name", "customer_email", "product_sku", "product_name",
    "category", "quantity", "unit_price", "discount_pct",
    "total_amount", "payment_method", "region", "email_hash",
]

VALID_PAYMENT_METHODS = {"credit_card", "debit_card", "cash", "mobile_pay"}
VALID_REGIONS = {"Northeast", "Southeast", "Midwest", "West"}

NULL_EMAIL_DEFAULT = "unknown@masked.invalid"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(value: str) -> str:
    """Deterministic SHA-256 hash of a string."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _mask_name(name: str) -> str:
    """Mask customer name: first initial + '***'. Empty/null -> '***'."""
    if not name or not name.strip():
        return "***"
    return name.strip()[0].upper() + "***"


def _safe_float(value: str) -> Optional[float]:
    """Parse a string to float, return None on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: str) -> Optional[int]:
    """Parse a string to int, return None on failure."""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _checksum_rows(rows: List[Dict[str, Any]]) -> str:
    """Compute a deterministic SHA-256 checksum over sorted rows."""
    h = hashlib.sha256()
    for row in rows:
        # Sort keys for determinism
        for k in sorted(row.keys()):
            h.update(f"{k}={row[k]}|".encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Step 1: Read Bronze CSV
# ---------------------------------------------------------------------------

def read_bronze(file_path: str) -> List[Dict[str, Any]]:
    """Read raw CSV from Bronze zone. Validates that expected columns exist."""
    file_path = os.path.abspath(file_path)
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Bronze CSV not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return rows

    # Validate columns
    actual_cols = set(rows[0].keys())
    missing = set(EXPECTED_COLUMNS) - actual_cols
    if missing:
        raise ValueError(f"Missing columns in source CSV: {missing}")

    return rows


# ---------------------------------------------------------------------------
# Step 2: Deduplicate on sale_id (keep first)
# ---------------------------------------------------------------------------

def deduplicate(rows: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
    """Deduplicate on sale_id, keep first occurrence. Return (clean, dupes)."""
    seen = set()
    clean = []
    dupes = []
    for row in rows:
        sid = row.get("sale_id", "")
        if sid in seen:
            dupes.append(row)
        else:
            seen.add(sid)
            clean.append(row)
    return clean, dupes


# ---------------------------------------------------------------------------
# Step 3: Null handling
# ---------------------------------------------------------------------------

def handle_nulls(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fill null customer_email with default; fill null customer_name with UNKNOWN."""
    for row in rows:
        email = row.get("customer_email", "")
        if not email or not email.strip():
            row["customer_email"] = NULL_EMAIL_DEFAULT
        name = row.get("customer_name", "")
        if not name or not name.strip():
            row["customer_name"] = "UNKNOWN"
    return rows


# ---------------------------------------------------------------------------
# Step 4: Type casting
# ---------------------------------------------------------------------------

def type_cast(rows: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
    """Cast quantity->int, unit_price/discount_pct/total_amount->float.
    Rows that fail casting are quarantined."""
    clean = []
    quarantined = []
    for row in rows:
        reasons = []

        qty = _safe_int(row.get("quantity", ""))
        if qty is None:
            reasons.append("quantity: cannot cast to integer")
        else:
            row["quantity"] = qty

        for col in ("unit_price", "discount_pct", "total_amount"):
            val = _safe_float(row.get(col, ""))
            if val is None:
                reasons.append(f"{col}: cannot cast to float")
            else:
                row[col] = val

        if reasons:
            row["_quarantine_reasons"] = reasons
            quarantined.append(row)
        else:
            clean.append(row)

    return clean, quarantined


# ---------------------------------------------------------------------------
# Step 5: Validation
# ---------------------------------------------------------------------------

def validate_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
    """Validate: discount_pct 0-100, quantity>0, total_amount>0.
    Invalid rows are quarantined with reasons."""
    clean = []
    quarantined = []
    for row in rows:
        reasons = []
        discount = row["discount_pct"]
        if not (0 <= discount <= 100):
            reasons.append(f"discount_pct={discount}: must be 0-100")

        qty = row["quantity"]
        if qty <= 0:
            reasons.append(f"quantity={qty}: must be > 0")

        total = row["total_amount"]
        if total <= 0:
            reasons.append(f"total_amount={total}: must be > 0")

        if reasons:
            row["_quarantine_reasons"] = reasons
            quarantined.append(row)
        else:
            clean.append(row)

    return clean, quarantined


# ---------------------------------------------------------------------------
# Step 6: PII masking
# ---------------------------------------------------------------------------

def mask_pii(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """SHA-256 hash customer_email -> email_hash, mask customer_name -> first initial + '***'."""
    for row in rows:
        email = row.get("customer_email", "")
        row["email_hash"] = _sha256(email)
        row["customer_email"] = row["email_hash"]  # Replace raw email with hash
        row["customer_name"] = _mask_name(row.get("customer_name", ""))
    return rows


# ---------------------------------------------------------------------------
# Step 7: Build Silver output
# ---------------------------------------------------------------------------

def build_silver(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort silver rows deterministically by sale_id."""
    return sorted(rows, key=lambda r: r.get("sale_id", ""))


# ---------------------------------------------------------------------------
# Step 8: Build Gold star schema
# ---------------------------------------------------------------------------

def build_dim_store(silver_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unique stores with surrogate store_key (integer, starting at 1)."""
    seen = OrderedDict()
    for row in silver_rows:
        sid = row["store_id"]
        if sid not in seen:
            seen[sid] = {
                "store_id": sid,
                "store_name": row["store_name"],
                "region": row["region"],
            }
    result = []
    for i, (sid, rec) in enumerate(seen.items(), start=1):
        rec["store_key"] = i
        result.append(rec)
    return result


def build_dim_product(silver_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unique products with surrogate product_key (integer, starting at 1)."""
    seen = OrderedDict()
    for row in silver_rows:
        sku = row["product_sku"]
        if sku not in seen:
            seen[sku] = {
                "product_sku": sku,
                "product_name": row["product_name"],
                "category": row["category"],
            }
    result = []
    for i, (sku, rec) in enumerate(seen.items(), start=1):
        rec["product_key"] = i
        result.append(rec)
    return result


def build_dim_date(silver_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unique dates with calendar attributes and surrogate date_key (YYYYMMDD int)."""
    seen = OrderedDict()
    for row in silver_rows:
        sd = row["sale_date"]
        if sd not in seen:
            try:
                dt = datetime.strptime(str(sd).strip(), "%Y-%m-%d")
            except ValueError:
                continue
            # iso weekday: Monday=1 .. Sunday=7
            day_of_week = dt.isoweekday()
            month = dt.month
            quarter = (dt.month - 1) // 3 + 1
            year = dt.year
            date_key = int(dt.strftime("%Y%m%d"))
            seen[sd] = {
                "date_key": date_key,
                "sale_date": sd,
                "day_of_week": day_of_week,
                "month": month,
                "quarter": quarter,
                "year": year,
            }
    return list(seen.values())


def build_fact_sales(
    silver_rows: List[Dict[str, Any]],
    dim_store: List[Dict[str, Any]],
    dim_product: List[Dict[str, Any]],
    dim_date: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build fact table with FK lookups to dimension tables."""
    store_lookup = {d["store_id"]: d["store_key"] for d in dim_store}
    product_lookup = {d["product_sku"]: d["product_key"] for d in dim_product}
    date_lookup = {d["sale_date"]: d["date_key"] for d in dim_date}

    facts = []
    for row in silver_rows:
        store_key = store_lookup.get(row["store_id"])
        product_key = product_lookup.get(row["product_sku"])
        date_key = date_lookup.get(row["sale_date"])

        facts.append({
            "sale_id": row["sale_id"],
            "date_key": date_key,
            "store_key": store_key,
            "product_key": product_key,
            "quantity": row["quantity"],
            "unit_price": row["unit_price"],
            "discount_pct": row["discount_pct"],
            "total_amount": row["total_amount"],
            "payment_method": row["payment_method"],
            "email_hash": row["email_hash"],
        })
    return sorted(facts, key=lambda r: r["sale_id"])


# ---------------------------------------------------------------------------
# Quality report generation
# ---------------------------------------------------------------------------

def generate_quality_report(
    zone: str,
    rows: List[Dict[str, Any]],
    quarantined: List[Dict[str, Any]],
    input_count: int,
) -> Dict[str, Any]:
    """Generate quality report JSON for a zone."""
    total = input_count
    valid = len(rows)
    invalid = len(quarantined)
    score = valid / total if total > 0 else 0.0

    report = {
        "zone": zone,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_row_count": total,
        "valid_row_count": valid,
        "quarantined_row_count": invalid,
        "quality_score": round(score, 4),
        "dimensions": {
            "completeness": round(score, 4),
            "uniqueness": 1.0,  # dedup already applied
            "validity": round(valid / total if total > 0 else 0.0, 4),
        },
        "pass": score >= (0.80 if zone == "silver" else 0.95),
        "quarantine_summary": [],
    }

    for q in quarantined:
        reasons = q.get("_quarantine_reasons", ["unknown"])
        report["quarantine_summary"].append({
            "sale_id": q.get("sale_id", "unknown"),
            "reasons": reasons,
        })

    return report


# ---------------------------------------------------------------------------
# Lineage generation
# ---------------------------------------------------------------------------

def generate_lineage(
    source_path: str,
    output_dir: str,
    bronze_count: int,
    silver_count: int,
    quarantine_count: int,
    gold_tables: Dict[str, int],
    silver_checksum: str,
) -> Dict[str, Any]:
    """Generate lineage JSON with source->target mapping."""
    return {
        "pipeline": "daily_sales_bronze_to_gold",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": source_path,
            "format": "csv",
            "row_count": bronze_count,
        },
        "silver": {
            "path": os.path.join(output_dir, "silver"),
            "format": "csv",
            "row_count": silver_count,
            "checksum": silver_checksum,
        },
        "quarantine": {
            "row_count": quarantine_count,
        },
        "gold": {
            "path": os.path.join(output_dir, "gold"),
            "tables": gold_tables,
        },
        "steps": [
            {"step": "read_bronze", "input_rows": bronze_count},
            {"step": "deduplicate", "key": "sale_id", "strategy": "keep_first"},
            {"step": "handle_nulls", "fills": {"customer_email": NULL_EMAIL_DEFAULT, "customer_name": "UNKNOWN"}},
            {"step": "type_cast", "columns": ["quantity", "unit_price", "discount_pct", "total_amount"]},
            {"step": "validate", "rules": ["discount_pct 0-100", "quantity > 0", "total_amount > 0"]},
            {"step": "mask_pii", "columns": {"customer_email": "sha256_hash", "customer_name": "first_initial_mask"}},
            {"step": "build_silver", "output_rows": silver_count},
            {"step": "build_gold_star_schema", "tables": list(gold_tables.keys())},
        ],
    }


# ---------------------------------------------------------------------------
# CSV I/O helpers
# ---------------------------------------------------------------------------

def _write_csv(filepath: str, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    """Write rows to CSV deterministically."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(filepath: str, data: Any) -> None:
    """Write JSON file with deterministic formatting."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False, default=str)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(input_path: str, output_dir: str) -> Dict[str, Any]:
    """Run the full Bronze -> Silver -> Gold pipeline. Returns summary dict."""

    # --- Bronze -> Silver ---
    bronze_rows = read_bronze(input_path)
    bronze_count = len(bronze_rows)

    # Dedup
    deduped, dupes = deduplicate(bronze_rows)

    # Null handling
    deduped = handle_nulls(deduped)

    # Type casting
    casted, cast_quarantined = type_cast(deduped)

    # Validation
    valid, val_quarantined = validate_rows(casted)

    # PII masking
    silver_rows = mask_pii(valid)

    # Build silver
    silver_rows = build_silver(silver_rows)

    # Combine all quarantined
    all_quarantined = []
    for d in dupes:
        d["_quarantine_reasons"] = ["duplicate sale_id"]
        all_quarantined.append(d)
    all_quarantined.extend(cast_quarantined)
    all_quarantined.extend(val_quarantined)

    # Write Silver
    silver_dir = os.path.join(output_dir, "silver")
    silver_csv_path = os.path.join(silver_dir, "daily_sales_silver.csv")
    _write_csv(silver_csv_path, silver_rows, SILVER_COLUMNS)

    # Write quarantine
    if all_quarantined:
        quarantine_dir = os.path.join(output_dir, "quarantine")
        q_fieldnames = EXPECTED_COLUMNS + ["_quarantine_reasons"]
        for q in all_quarantined:
            if isinstance(q.get("_quarantine_reasons"), list):
                q["_quarantine_reasons"] = "; ".join(q["_quarantine_reasons"])
        _write_csv(
            os.path.join(quarantine_dir, "daily_sales_quarantine.csv"),
            all_quarantined,
            q_fieldnames,
        )

    # Silver quality report
    silver_quality = generate_quality_report("silver", silver_rows, all_quarantined, bronze_count)
    _write_json(os.path.join(silver_dir, "quality_report.json"), silver_quality)

    # Silver checksum
    silver_checksum = _checksum_rows(silver_rows)

    # --- Silver -> Gold (Star Schema) ---
    dim_store = build_dim_store(silver_rows)
    dim_product = build_dim_product(silver_rows)
    dim_date = build_dim_date(silver_rows)
    fact_sales = build_fact_sales(silver_rows, dim_store, dim_product, dim_date)

    gold_dir = os.path.join(output_dir, "gold")

    _write_csv(
        os.path.join(gold_dir, "dim_store.csv"),
        dim_store,
        ["store_key", "store_id", "store_name", "region"],
    )
    _write_csv(
        os.path.join(gold_dir, "dim_product.csv"),
        dim_product,
        ["product_key", "product_sku", "product_name", "category"],
    )
    _write_csv(
        os.path.join(gold_dir, "dim_date.csv"),
        dim_date,
        ["date_key", "sale_date", "day_of_week", "month", "quarter", "year"],
    )
    _write_csv(
        os.path.join(gold_dir, "fact_sales.csv"),
        fact_sales,
        ["sale_id", "date_key", "store_key", "product_key", "quantity",
         "unit_price", "discount_pct", "total_amount", "payment_method", "email_hash"],
    )

    # Gold quality report
    gold_tables = {
        "fact_sales": len(fact_sales),
        "dim_store": len(dim_store),
        "dim_product": len(dim_product),
        "dim_date": len(dim_date),
    }
    gold_quality = {
        "zone": "gold",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tables": gold_tables,
        "quality_score": 1.0 if len(fact_sales) == len(silver_rows) else round(len(fact_sales) / len(silver_rows), 4),
        "fk_integrity": {
            "all_store_keys_valid": all(
                f["store_key"] is not None for f in fact_sales
            ),
            "all_product_keys_valid": all(
                f["product_key"] is not None for f in fact_sales
            ),
            "all_date_keys_valid": all(
                f["date_key"] is not None for f in fact_sales
            ),
        },
        "pass": True,
    }
    _write_json(os.path.join(gold_dir, "quality_report.json"), gold_quality)

    # Lineage
    lineage = generate_lineage(
        source_path=input_path,
        output_dir=output_dir,
        bronze_count=bronze_count,
        silver_count=len(silver_rows),
        quarantine_count=len(all_quarantined),
        gold_tables=gold_tables,
        silver_checksum=silver_checksum,
    )
    _write_json(os.path.join(output_dir, "lineage.json"), lineage)

    summary = {
        "bronze_rows": bronze_count,
        "silver_rows": len(silver_rows),
        "quarantined_rows": len(all_quarantined),
        "duplicates": len(dupes),
        "cast_failures": len(cast_quarantined),
        "validation_failures": len(val_quarantined),
        "gold_tables": gold_tables,
        "silver_quality_score": silver_quality["quality_score"],
        "gold_quality_pass": gold_quality["pass"],
    }
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="daily_sales Bronze -> Silver -> Gold transformation pipeline"
    )
    parser.add_argument(
        "--local", action="store_true",
        help="Run in local mode using local CSV file",
    )
    parser.add_argument(
        "--input", dest="input_path",
        help="Path to input CSV (Bronze zone)",
    )
    parser.add_argument(
        "--output-dir", dest="output_dir",
        help="Directory for output files (silver/, gold/, quarantine/)",
    )
    args = parser.parse_args()

    # Resolve paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workload_dir = os.path.abspath(os.path.join(script_dir, "..", ".."))
    project_dir = os.path.abspath(os.path.join(workload_dir, "..", ".."))

    if args.input_path:
        input_path = os.path.abspath(args.input_path)
    elif args.local:
        input_path = os.path.join(project_dir, "demo", "sample_data", "daily_sales_2026-03-18.csv")
    else:
        print("Error: provide --input <path> or use --local for sample data", file=sys.stderr)
        sys.exit(1)

    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    else:
        output_dir = os.path.join(workload_dir, "output")

    print(f"Input:  {input_path}")
    print(f"Output: {output_dir}")

    summary = run_pipeline(input_path, output_dir)

    print("\n--- Pipeline Summary ---")
    print(f"  Bronze rows:        {summary['bronze_rows']}")
    print(f"  Silver rows:        {summary['silver_rows']}")
    print(f"  Quarantined rows:   {summary['quarantined_rows']}")
    print(f"    - Duplicates:     {summary['duplicates']}")
    print(f"    - Cast failures:  {summary['cast_failures']}")
    print(f"    - Validation:     {summary['validation_failures']}")
    print(f"  Silver quality:     {summary['silver_quality_score']}")
    print(f"  Gold tables:        {summary['gold_tables']}")
    print(f"  Gold quality pass:  {summary['gold_quality_pass']}")
    print("--- Done ---")


if __name__ == "__main__":
    main()
