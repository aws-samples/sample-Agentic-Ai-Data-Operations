"""
Bronze zone quality checks for order_transactions.

Validates raw data BEFORE transformation:
- Completeness: null checks on critical columns
- Uniqueness: duplicate order_id detection
- Validity: enum values, positive numerics, date format
- Consistency: revenue formula check
"""

import csv
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

FIXTURES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "shared", "fixtures")
)

VALID_CATEGORIES = {"Electronics", "Furniture", "Supplies"}
VALID_STATUSES = {"Completed", "Pending", "Cancelled"}
VALID_REGIONS = {"East", "West", "Central", "South"}


def check_bronze(orders_path: str = None) -> dict:
    """Run all Bronze quality checks.

    Returns a quality report with scores and details.
    """
    path = orders_path or os.path.join(FIXTURES_DIR, "orders.csv")

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    checks = []

    # Completeness checks
    for col in ["order_id", "customer_id", "order_date", "revenue"]:
        nulls = sum(1 for r in rows if not r.get(col, "").strip())
        severity = "critical" if col in ("order_id", "customer_id", "order_date") else "warning"
        passed = nulls == 0
        checks.append({
            "dimension": "completeness",
            "rule": f"{col}_not_null",
            "passed": passed,
            "severity": severity,
            "detail": f"{nulls}/{total} null values",
        })

    # Uniqueness check
    order_ids = [r.get("order_id", "").strip() for r in rows]
    dupes = total - len(set(order_ids))
    checks.append({
        "dimension": "uniqueness",
        "rule": "order_id_unique",
        "passed": dupes == 0,
        "severity": "warning",
        "detail": f"{dupes} duplicate order_ids",
    })

    # Validity: enums
    for col, valid_set, name in [
        ("category", VALID_CATEGORIES, "category"),
        ("status", VALID_STATUSES, "status"),
        ("region", VALID_REGIONS, "region"),
    ]:
        invalid = sum(1 for r in rows if r.get(col, "").strip() not in valid_set)
        checks.append({
            "dimension": "validity",
            "rule": f"{name}_in_set",
            "passed": invalid == 0,
            "severity": "critical",
            "detail": f"{invalid}/{total} invalid values",
        })

    # Validity: positive numerics
    for col in ["quantity", "unit_price"]:
        bad = 0
        for r in rows:
            try:
                if float(r.get(col, 0)) <= 0:
                    bad += 1
            except ValueError:
                bad += 1
        checks.append({
            "dimension": "validity",
            "rule": f"{col}_positive",
            "passed": bad == 0,
            "severity": "critical",
            "detail": f"{bad}/{total} non-positive values",
        })

    # Validity: discount_pct range [0, 1]
    bad_disc = 0
    for r in rows:
        try:
            d = float(r.get("discount_pct", 0))
            if d < 0 or d > 1:
                bad_disc += 1
        except ValueError:
            bad_disc += 1
    checks.append({
        "dimension": "validity",
        "rule": "discount_pct_range",
        "passed": bad_disc == 0,
        "severity": "critical",
        "detail": f"{bad_disc}/{total} out of range",
    })

    # Consistency: revenue formula
    mismatches = 0
    for r in rows:
        try:
            qty = float(r["quantity"])
            price = float(r["unit_price"])
            disc = float(r["discount_pct"])
            rev = float(r["revenue"])
            expected = qty * price * (1 - disc)
            if abs(rev - expected) > 0.01:
                mismatches += 1
        except (ValueError, KeyError):
            mismatches += 1
    checks.append({
        "dimension": "consistency",
        "rule": "revenue_formula",
        "passed": mismatches == 0,
        "severity": "warning",
        "detail": f"{mismatches}/{total} revenue mismatches",
    })

    # Compute overall score
    total_checks = len(checks)
    passed_checks = sum(1 for c in checks if c["passed"])
    critical_failures = [c for c in checks if not c["passed"] and c["severity"] == "critical"]
    score = passed_checks / total_checks if total_checks > 0 else 0

    return {
        "zone": "bronze",
        "workload": "order_transactions",
        "source_file": path,
        "row_count": total,
        "score": round(score, 4),
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "critical_failures": len(critical_failures),
        "checks": checks,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = check_bronze()
    print(f"Bronze Quality Score: {report['score']:.2%}")
    print(f"Checks: {report['passed_checks']}/{report['total_checks']} passed")
    if report["critical_failures"]:
        print(f"CRITICAL FAILURES: {report['critical_failures']}")
    for c in report["checks"]:
        status = "PASS" if c["passed"] else "FAIL"
        print(f"  [{status}] {c['dimension']}.{c['rule']}: {c['detail']}")
