"""
check_gold.py — Gold zone quality checks for Customer Master star schema.

Validates the transformed Gold zone tables against quality_rules.yaml Gold rules.
"""

import csv
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKLOAD_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
GOLD_OUTPUT_DIR = os.path.join(WORKLOAD_DIR, "output", "gold")
MINIMUM_SCORE = 0.95


def read_csv(file_path: str) -> List[Dict[str, Any]]:
    """Read CSV and return rows."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Gold CSV not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_unique(rows: List[dict], column: str) -> Dict[str, Any]:
    """Check column uniqueness."""
    vals = [r.get(column, "").strip() for r in rows if r.get(column, "").strip()]
    unique = len(set(vals))
    return {"total": len(vals), "unique": unique, "duplicates": len(vals) - unique}


def check_not_null(rows: List[dict], column: str) -> Dict[str, Any]:
    """Check column is not null."""
    total = len(rows)
    non_null = sum(1 for r in rows if r.get(column, "").strip())
    return {"total": total, "non_null": non_null, "rate": round(non_null / total, 4) if total else 0}


def check_referential_integrity(
    parent_rows: List[dict], parent_col: str,
    child_rows: List[dict], child_col: str,
) -> Dict[str, Any]:
    """Check all child values exist in parent."""
    parent_vals = {r.get(parent_col, "").strip() for r in parent_rows}
    child_vals = {r.get(child_col, "").strip() for r in child_rows}
    orphans = child_vals - parent_vals
    return {
        "parent_count": len(parent_vals),
        "child_distinct": len(child_vals),
        "orphans": list(orphans),
        "orphan_count": len(orphans),
    }


def check_no_at_in_hash(rows: List[dict], column: str) -> Dict[str, Any]:
    """Check hashed email does not contain @ symbol."""
    vals = [r.get(column, "").strip() for r in rows if r.get(column, "").strip()]
    has_at = sum(1 for v in vals if "@" in v)
    return {"total": len(vals), "has_at_symbol": has_at, "properly_hashed": len(vals) - has_at}


def check_mask_chars(rows: List[dict], column: str) -> Dict[str, Any]:
    """Check masked phone contains * characters."""
    vals = [r.get(column, "").strip() for r in rows if r.get(column, "").strip()]
    has_mask = sum(1 for v in vals if "*" in v)
    return {"total": len(vals), "masked": has_mask, "not_masked": len(vals) - has_mask}


def run_gold_checks(gold_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Run all Gold zone quality checks.

    Returns quality report with per-rule results and overall score.
    """
    gdir = gold_dir or GOLD_OUTPUT_DIR
    started = datetime.now(timezone.utc)

    # Load tables
    fact = read_csv(os.path.join(gdir, "customer_fact.csv"))
    dim_seg = read_csv(os.path.join(gdir, "dim_segment.csv"))
    dim_country = read_csv(os.path.join(gdir, "dim_country.csv"))
    dim_status = read_csv(os.path.join(gdir, "dim_status.csv"))
    summary = read_csv(os.path.join(gdir, "customer_summary_by_segment.csv"))

    rules_results: List[Dict[str, Any]] = []
    critical_failures = 0
    total_rules = 0
    passed_rules = 0

    # 1. fact_pk_unique
    total_rules += 1
    r = check_unique(fact, "customer_id")
    passed = r["duplicates"] == 0
    if passed:
        passed_rules += 1
    else:
        critical_failures += 1
    rules_results.append({
        "name": "fact_pk_unique", "severity": "critical", "passed": passed, "details": r
    })

    # 2. fact_no_null_pk
    total_rules += 1
    r = check_not_null(fact, "customer_id")
    passed = r["rate"] == 1.0
    if passed:
        passed_rules += 1
    else:
        critical_failures += 1
    rules_results.append({
        "name": "fact_no_null_pk", "severity": "critical", "passed": passed, "details": r
    })

    # 3. dim_segment_complete
    total_rules += 1
    r = check_referential_integrity(dim_seg, "segment_name", fact, "segment")
    passed = r["orphan_count"] == 0
    if passed:
        passed_rules += 1
    else:
        critical_failures += 1
    rules_results.append({
        "name": "dim_segment_complete", "severity": "critical", "passed": passed, "details": r
    })

    # 4. dim_country_complete
    total_rules += 1
    r = check_referential_integrity(dim_country, "country_code", fact, "country_code")
    passed = r["orphan_count"] == 0
    if passed:
        passed_rules += 1
    else:
        critical_failures += 1
    rules_results.append({
        "name": "dim_country_complete", "severity": "critical", "passed": passed, "details": r
    })

    # 5. dim_status_complete
    total_rules += 1
    r = check_referential_integrity(dim_status, "status_name", fact, "status")
    passed = r["orphan_count"] == 0
    if passed:
        passed_rules += 1
    else:
        critical_failures += 1
    rules_results.append({
        "name": "dim_status_complete", "severity": "critical", "passed": passed, "details": r
    })

    # 6. no_duplicate_facts (row-level)
    total_rules += 1
    r = check_unique(fact, "customer_id")
    passed = r["duplicates"] == 0
    if passed:
        passed_rules += 1
    else:
        critical_failures += 1
    rules_results.append({
        "name": "no_duplicate_facts", "severity": "critical", "passed": passed, "details": r
    })

    # 7. pii_masked (email hash)
    total_rules += 1
    r = check_no_at_in_hash(fact, "email_hash")
    passed = r["has_at_symbol"] == 0
    if passed:
        passed_rules += 1
    else:
        critical_failures += 1
    rules_results.append({
        "name": "pii_masked_email", "severity": "critical", "passed": passed, "details": r
    })

    # 8. phone_masked
    total_rules += 1
    r = check_mask_chars(fact, "phone_masked")
    passed = r["not_masked"] == 0
    if passed:
        passed_rules += 1
    rules_results.append({
        "name": "phone_masked", "severity": "warning", "passed": passed, "details": r
    })

    # 9. summary_matches_fact
    total_rules += 1
    fact_seg_counts: Dict[str, int] = {}
    for row in fact:
        seg = row.get("segment", "").strip()
        fact_seg_counts[seg] = fact_seg_counts.get(seg, 0) + 1
    summary_counts: Dict[str, int] = {}
    for row in summary:
        seg = row.get("segment", "").strip()
        summary_counts[seg] = int(row.get("customer_count", 0))
    passed = fact_seg_counts == summary_counts
    if passed:
        passed_rules += 1
    rules_results.append({
        "name": "summary_matches_fact", "severity": "warning", "passed": passed,
        "details": {"fact_counts": fact_seg_counts, "summary_counts": summary_counts},
    })

    score = passed_rules / total_rules if total_rules else 0
    finished = datetime.now(timezone.utc)

    report = {
        "agent": "check_gold",
        "zone": "gold",
        "gold_dir": os.path.abspath(gdir),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "fact_row_count": len(fact),
        "total_rules": total_rules,
        "passed_rules": passed_rules,
        "failed_rules": total_rules - passed_rules,
        "critical_failures": critical_failures,
        "score": round(score, 4),
        "minimum_score": MINIMUM_SCORE,
        "gate_passed": score >= MINIMUM_SCORE and critical_failures == 0,
        "rules": rules_results,
    }
    logger.info(
        "Gold quality: score=%.2f, %d/%d passed, %d critical failures, gate=%s",
        score, passed_rules, total_rules, critical_failures, report["gate_passed"],
    )
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = run_gold_checks()
    print(f"Score: {report['score']}")
    print(f"Gate passed: {report['gate_passed']}")
    for r in report["rules"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['name']} ({r['severity']})")
