"""
Transform order_transactions from Bronze (raw CSV) to Gold (star schema).

Transformations applied:
1. Dedup on order_id (keep first)
2. Quarantine null PKs
3. FK validation: customer_id must exist in customer_master
4. Future date quarantine: order_date > today
5. Revenue validation: |revenue - quantity*unit_price*(1-discount_pct)| <= 0.01
6. Enum validation: category, status, region
7. Type casting
8. Build star schema: order_fact, dim_product, dim_region, dim_status, order_summary

This script is idempotent - running it twice produces identical output.
"""

import csv
import os
import logging
from datetime import datetime, date, timezone

logger = logging.getLogger(__name__)

# Allowed enum values
VALID_CATEGORIES = {"Electronics", "Furniture", "Supplies"}
VALID_STATUSES = {"Completed", "Pending", "Cancelled"}
VALID_REGIONS = {"East", "West", "Central", "South"}

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKLOAD_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
FIXTURES_DIR = os.path.abspath(os.path.join(WORKLOAD_DIR, "..", "..", "shared", "fixtures"))
GOLD_OUTPUT_DIR = os.path.join(WORKLOAD_DIR, "output", "gold")
QUARANTINE_DIR = os.path.join(WORKLOAD_DIR, "output", "quarantine")


def load_valid_customer_ids(customers_path: str = None) -> set:
    """Load valid customer_ids from customer_master fixtures."""
    path = customers_path or os.path.join(FIXTURES_DIR, "customers.csv")
    if not os.path.exists(path):
        logger.warning("Customer file not found at %s, FK validation will be skipped", path)
        return set()

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["customer_id"] for row in reader}


def load_orders(orders_path: str = None) -> list[dict]:
    """Load raw orders from CSV."""
    path = orders_path or os.path.join(FIXTURES_DIR, "orders.csv")
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def transform(
    orders_path: str = None,
    customers_path: str = None,
    output_dir: str = None,
    quarantine_dir: str = None,
    reference_date: date = None,
) -> dict:
    """Run full Bronze-to-Gold transformation.

    Args:
        orders_path: Path to orders CSV (default: shared/fixtures/orders.csv)
        customers_path: Path to customers CSV for FK validation
        output_dir: Where to write Gold CSVs (default: workload output/gold/)
        quarantine_dir: Where to write quarantined records
        reference_date: Date to compare against for future-date check (default: today)

    Returns:
        dict with transformation metadata and statistics.
    """
    gold_dir = output_dir or GOLD_OUTPUT_DIR
    quar_dir = quarantine_dir or QUARANTINE_DIR
    ref_date = reference_date or date.today()

    os.makedirs(gold_dir, exist_ok=True)
    os.makedirs(quar_dir, exist_ok=True)

    # Load data
    raw_orders = load_orders(orders_path)
    valid_customers = load_valid_customer_ids(customers_path)
    total_raw = len(raw_orders)

    # Stats
    stats = {
        "total_raw": total_raw,
        "duplicates_removed": 0,
        "null_pk_quarantined": 0,
        "orphan_fk_quarantined": 0,
        "future_date_quarantined": 0,
        "invalid_enum_quarantined": 0,
        "revenue_mismatches": 0,
        "clean_records": 0,
    }

    quarantined = []
    clean = []

    # Step 1: Dedup on order_id (keep first)
    seen_ids = set()
    deduped = []
    for row in raw_orders:
        oid = row.get("order_id", "").strip()
        if oid in seen_ids:
            stats["duplicates_removed"] += 1
            continue
        seen_ids.add(oid)
        deduped.append(row)

    # Step 2-6: Validate each record
    for row in deduped:
        reasons = []

        # Null PK check
        if not row.get("order_id", "").strip():
            reasons.append("null_order_id")
            stats["null_pk_quarantined"] += 1

        if not row.get("customer_id", "").strip():
            reasons.append("null_customer_id")
            stats["null_pk_quarantined"] += 1

        # FK validation
        cid = row.get("customer_id", "").strip()
        if valid_customers and cid and cid not in valid_customers:
            reasons.append(f"orphan_customer_id:{cid}")
            stats["orphan_fk_quarantined"] += 1

        # Future date check
        try:
            order_date = datetime.strptime(row["order_date"], "%Y-%m-%d").date()
            if order_date > ref_date:
                reasons.append(f"future_date:{row['order_date']}")
                stats["future_date_quarantined"] += 1
        except (ValueError, KeyError):
            reasons.append(f"invalid_date:{row.get('order_date', 'MISSING')}")

        # Enum validation
        if row.get("category") not in VALID_CATEGORIES:
            reasons.append(f"invalid_category:{row.get('category')}")
            stats["invalid_enum_quarantined"] += 1
        if row.get("status") not in VALID_STATUSES:
            reasons.append(f"invalid_status:{row.get('status')}")
            stats["invalid_enum_quarantined"] += 1
        if row.get("region") not in VALID_REGIONS:
            reasons.append(f"invalid_region:{row.get('region')}")
            stats["invalid_enum_quarantined"] += 1

        # Revenue validation
        try:
            qty = float(row["quantity"])
            price = float(row["unit_price"])
            disc = float(row["discount_pct"])
            rev = float(row["revenue"])
            expected = qty * price * (1 - disc)
            if abs(rev - expected) > 0.01:
                stats["revenue_mismatches"] += 1
                # Flag but don't quarantine
                row["_revenue_flag"] = f"expected={expected:.2f},actual={rev}"
        except (ValueError, KeyError):
            pass

        if reasons:
            row["_quarantine_reasons"] = "|".join(reasons)
            quarantined.append(row)
        else:
            clean.append(row)

    stats["clean_records"] = len(clean)

    # Build star schema
    dim_product, dim_region, dim_status, fact_table, summary = _build_star_schema(clean)

    # Write outputs
    _write_csv(os.path.join(gold_dir, "order_fact.csv"), fact_table, _fact_columns())
    _write_csv(os.path.join(gold_dir, "dim_product.csv"), dim_product, ["product_id", "product_name", "category"])
    _write_csv(os.path.join(gold_dir, "dim_region.csv"), dim_region, ["region_id", "region_name"])
    _write_csv(os.path.join(gold_dir, "dim_status.csv"), dim_status, ["status_id", "status_name"])
    _write_csv(os.path.join(gold_dir, "order_summary.csv"), summary, _summary_columns())

    if quarantined:
        q_cols = list(raw_orders[0].keys()) + ["_quarantine_reasons"]
        _write_csv(os.path.join(quar_dir, "quarantined_orders.csv"), quarantined, q_cols)

    stats["quarantine_count"] = len(quarantined)
    stats["dim_product_count"] = len(dim_product)
    stats["dim_region_count"] = len(dim_region)
    stats["dim_status_count"] = len(dim_status)
    stats["fact_count"] = len(fact_table)
    stats["summary_count"] = len(summary)
    stats["transformed_at"] = datetime.now(timezone.utc).isoformat()

    return stats


def _build_star_schema(clean_records: list[dict]) -> tuple:
    """Build star schema tables from clean records.

    Returns: (dim_product, dim_region, dim_status, fact_table, summary)
    """
    # Build dimension tables
    products = {}
    regions = {}
    statuses = {}

    for row in clean_records:
        pkey = (row["product_name"], row["category"])
        if pkey not in products:
            products[pkey] = {
                "product_id": f"PROD-{len(products) + 1:03d}",
                "product_name": row["product_name"],
                "category": row["category"],
            }

        rkey = row["region"]
        if rkey not in regions:
            regions[rkey] = {
                "region_id": f"REG-{len(regions) + 1:03d}",
                "region_name": row["region"],
            }

        skey = row["status"]
        if skey not in statuses:
            statuses[skey] = {
                "status_id": f"STAT-{len(statuses) + 1:03d}",
                "status_name": row["status"],
            }

    dim_product = sorted(products.values(), key=lambda x: x["product_id"])
    dim_region = sorted(regions.values(), key=lambda x: x["region_id"])
    dim_status = sorted(statuses.values(), key=lambda x: x["status_id"])

    # Build fact table
    fact_table = []
    for row in clean_records:
        pkey = (row["product_name"], row["category"])
        fact_table.append({
            "order_id": row["order_id"],
            "customer_id": row["customer_id"],
            "order_date": row["order_date"],
            "product_id": products[pkey]["product_id"],
            "region_id": regions[row["region"]]["region_id"],
            "status_id": statuses[row["status"]]["status_id"],
            "status_name": row["status"],
            "quantity": int(float(row["quantity"])),
            "unit_price": round(float(row["unit_price"]), 2),
            "discount_pct": round(float(row["discount_pct"]), 4),
            "revenue": round(float(row["revenue"]), 2),
        })

    # Build summary aggregate
    agg = {}
    for row in fact_table:
        rname = None
        for r in dim_region:
            if r["region_id"] == row["region_id"]:
                rname = r["region_name"]
                break
        pcat = None
        for p in dim_product:
            if p["product_id"] == row["product_id"]:
                pcat = p["category"]
                break

        key = (rname, pcat)
        if key not in agg:
            agg[key] = {
                "region": rname,
                "category": pcat,
                "total_revenue": 0.0,
                "total_quantity": 0,
                "order_count": 0,
                "sum_unit_price": 0.0,
                "sum_discount_pct": 0.0,
            }
        agg[key]["total_revenue"] += row["revenue"]
        agg[key]["total_quantity"] += row["quantity"]
        agg[key]["order_count"] += 1
        agg[key]["sum_unit_price"] += row["unit_price"]
        agg[key]["sum_discount_pct"] += row["discount_pct"]

    summary = []
    for key, val in sorted(agg.items()):
        n = val["order_count"]
        summary.append({
            "region": val["region"],
            "category": val["category"],
            "total_revenue": round(val["total_revenue"], 2),
            "total_quantity": val["total_quantity"],
            "order_count": n,
            "avg_unit_price": round(val["sum_unit_price"] / n, 2) if n else 0,
            "avg_discount_pct": round(val["sum_discount_pct"] / n, 4) if n else 0,
        })

    return dim_product, dim_region, dim_status, fact_table, summary


def _fact_columns():
    return [
        "order_id", "customer_id", "order_date", "product_id",
        "region_id", "status_id", "status_name",
        "quantity", "unit_price", "discount_pct", "revenue",
    ]


def _summary_columns():
    return [
        "region", "category", "total_revenue", "total_quantity",
        "order_count", "avg_unit_price", "avg_discount_pct",
    ]


def _write_csv(filepath: str, rows: list[dict], columns: list[str]):
    """Write rows to CSV with specified column order."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %d rows to %s", len(rows), filepath)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stats = transform()
    print(f"Transformation complete: {stats['clean_records']} clean, "
          f"{stats['quarantine_count']} quarantined, "
          f"{stats['duplicates_removed']} duplicates removed")
    for k, v in stats.items():
        print(f"  {k}: {v}")
