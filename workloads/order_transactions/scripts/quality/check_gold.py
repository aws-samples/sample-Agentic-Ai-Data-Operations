"""
Gold zone quality checks for order_transactions.

Validates transformed star schema data:
- Completeness: no nulls in PKs/FKs
- Uniqueness: PKs unique in all tables
- Referential integrity: fact FKs match dim PKs
- Accuracy: no future dates, no orphan customers
"""

import csv
import os
import logging
from datetime import datetime, date, timezone

logger = logging.getLogger(__name__)

GOLD_THRESHOLD = 0.95


def _load_csv(filepath: str) -> list[dict]:
    """Load a CSV into list of dicts."""
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_gold(
    gold_dir: str = None,
    customers_path: str = None,
    reference_date: date = None,
) -> dict:
    """Run all Gold zone quality checks.

    Args:
        gold_dir: Directory containing Gold CSVs
        customers_path: Path to customers CSV for FK validation
        reference_date: Reference date for future-date checks

    Returns:
        Quality report dict.
    """
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    gdir = gold_dir or os.path.join(base, "output", "gold")
    ref_date = reference_date or date.today()
    fixtures = os.path.abspath(os.path.join(base, "..", "..", "shared", "fixtures"))
    cust_path = customers_path or os.path.join(fixtures, "customers.csv")

    # Load tables
    fact = _load_csv(os.path.join(gdir, "order_fact.csv"))
    dim_product = _load_csv(os.path.join(gdir, "dim_product.csv"))
    dim_region = _load_csv(os.path.join(gdir, "dim_region.csv"))
    dim_status = _load_csv(os.path.join(gdir, "dim_status.csv"))

    checks = []

    # --- Completeness ---
    for col in ["order_id", "customer_id"]:
        nulls = sum(1 for r in fact if not r.get(col, "").strip())
        checks.append({
            "dimension": "completeness",
            "rule": f"order_fact.{col}_not_null",
            "passed": nulls == 0,
            "severity": "critical",
            "detail": f"{nulls}/{len(fact)} null values",
        })

    # --- Uniqueness ---
    # Fact PK
    fact_ids = [r["order_id"] for r in fact]
    fact_dupes = len(fact_ids) - len(set(fact_ids))
    checks.append({
        "dimension": "uniqueness",
        "rule": "order_fact.order_id_unique",
        "passed": fact_dupes == 0,
        "severity": "critical",
        "detail": f"{fact_dupes} duplicates",
    })

    # Dim PKs
    for table, rows, pk in [
        ("dim_product", dim_product, "product_id"),
        ("dim_region", dim_region, "region_id"),
        ("dim_status", dim_status, "status_id"),
    ]:
        ids = [r[pk] for r in rows]
        dupes = len(ids) - len(set(ids))
        checks.append({
            "dimension": "uniqueness",
            "rule": f"{table}.{pk}_unique",
            "passed": dupes == 0,
            "severity": "critical",
            "detail": f"{dupes} duplicates in {len(ids)} rows",
        })

    # --- Referential Integrity ---
    product_ids = {r["product_id"] for r in dim_product}
    region_ids = {r["region_id"] for r in dim_region}
    status_ids = {r["status_id"] for r in dim_status}

    for fk_col, dim_set, dim_name in [
        ("product_id", product_ids, "dim_product"),
        ("region_id", region_ids, "dim_region"),
        ("status_id", status_ids, "dim_status"),
    ]:
        orphans = sum(1 for r in fact if r.get(fk_col) not in dim_set)
        checks.append({
            "dimension": "referential_integrity",
            "rule": f"order_fact.{fk_col}_in_{dim_name}",
            "passed": orphans == 0,
            "severity": "critical",
            "detail": f"{orphans} orphan FKs",
        })

    # --- Accuracy: no future dates ---
    future = 0
    for r in fact:
        try:
            od = datetime.strptime(r["order_date"], "%Y-%m-%d").date()
            if od > ref_date:
                future += 1
        except (ValueError, KeyError):
            future += 1
    checks.append({
        "dimension": "accuracy",
        "rule": "order_fact.no_future_dates",
        "passed": future == 0,
        "severity": "critical",
        "detail": f"{future} future-dated orders",
    })

    # --- Accuracy: no orphan customers ---
    if os.path.exists(cust_path):
        valid_custs = set()
        with open(cust_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                valid_custs.add(row["customer_id"])
        orphan_custs = sum(1 for r in fact if r.get("customer_id") not in valid_custs)
        checks.append({
            "dimension": "accuracy",
            "rule": "order_fact.no_orphan_customers",
            "passed": orphan_custs == 0,
            "severity": "critical",
            "detail": f"{orphan_custs} orphan customer_ids",
        })

    # Score
    total_checks = len(checks)
    passed_checks = sum(1 for c in checks if c["passed"])
    critical_failures = [c for c in checks if not c["passed"] and c["severity"] == "critical"]
    score = passed_checks / total_checks if total_checks > 0 else 0
    meets_threshold = score >= GOLD_THRESHOLD and len(critical_failures) == 0

    return {
        "zone": "gold",
        "workload": "order_transactions",
        "gold_dir": gdir,
        "score": round(score, 4),
        "threshold": GOLD_THRESHOLD,
        "meets_threshold": meets_threshold,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "critical_failures": len(critical_failures),
        "checks": checks,
        "tables": {
            "order_fact": len(fact),
            "dim_product": len(dim_product),
            "dim_region": len(dim_region),
            "dim_status": len(dim_status),
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = check_gold()
    print(f"Gold Quality Score: {report['score']:.2%} (threshold: {report['threshold']:.0%})")
    print(f"Meets threshold: {report['meets_threshold']}")
    print(f"Checks: {report['passed_checks']}/{report['total_checks']} passed")
    print(f"Tables: {report['tables']}")
    for c in report["checks"]:
        status = "PASS" if c["passed"] else "FAIL"
        print(f"  [{status}] {c['dimension']}.{c['rule']}: {c['detail']}")
