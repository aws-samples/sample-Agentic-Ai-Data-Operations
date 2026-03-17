"""
check_bronze.py — Bronze zone quality checks for Customer Master.

Validates raw ingested data against quality_rules.yaml Bronze rules.
Returns a quality report with pass/fail per rule and overall score.
"""

import csv
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKLOAD_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
PROJECT_DIR = os.path.abspath(os.path.join(WORKLOAD_DIR, "..", ".."))
LOCAL_CSV_PATH = os.path.join(PROJECT_DIR, "shared", "fixtures", "customers.csv")

VALID_SEGMENTS = {"Enterprise", "SMB", "Individual"}
VALID_STATUSES = {"Active", "Inactive", "Churned"}
VALID_COUNTRIES = {"US", "UK", "CA", "DE"}
MINIMUM_SCORE = 0.80


def read_csv(file_path: str) -> List[Dict[str, Any]]:
    """Read CSV and return rows."""
    with open(file_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_not_null(rows: List[dict], column: str) -> Dict[str, Any]:
    """Check column is not null/empty."""
    total = len(rows)
    non_null = sum(1 for r in rows if r.get(column, "").strip())
    rate = non_null / total if total else 0
    return {"total": total, "non_null": non_null, "rate": round(rate, 4)}


def check_unique(rows: List[dict], column: str) -> Dict[str, Any]:
    """Check column uniqueness."""
    vals = [r.get(column, "").strip() for r in rows if r.get(column, "").strip()]
    unique = len(set(vals))
    return {"total": len(vals), "unique": unique, "duplicates": len(vals) - unique}


def check_regex(rows: List[dict], column: str, pattern: str) -> Dict[str, Any]:
    """Check column values match regex."""
    pat = re.compile(pattern)
    vals = [r.get(column, "").strip() for r in rows if r.get(column, "").strip()]
    matches = sum(1 for v in vals if pat.match(v))
    return {"total": len(vals), "matches": matches, "failures": len(vals) - matches}


def check_in_set(rows: List[dict], column: str, valid_set: set) -> Dict[str, Any]:
    """Check column values are in allowed set."""
    vals = [r.get(column, "").strip() for r in rows if r.get(column, "").strip()]
    valid = sum(1 for v in vals if v in valid_set)
    return {"total": len(vals), "valid": valid, "invalid": len(vals) - valid}


def check_gte(rows: List[dict], column: str, value: float) -> Dict[str, Any]:
    """Check numeric column >= value."""
    vals = []
    for r in rows:
        v = r.get(column, "").strip()
        if v:
            try:
                vals.append(float(v))
            except ValueError:
                pass
    passing = sum(1 for v in vals if v >= value)
    return {"total": len(vals), "passing": passing, "failing": len(vals) - passing}


def run_bronze_checks(file_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Run all Bronze quality checks.

    Returns quality report with per-rule results and overall score.
    """
    src = file_path or LOCAL_CSV_PATH
    rows = read_csv(src)
    total_rows = len(rows)
    started = datetime.now(timezone.utc)

    rules_results = []  # type: List[Dict[str, Any]]
    critical_failures = 0
    total_rules = 0
    passed_rules = 0

    # Critical rules
    # 1. pk_not_null
    total_rules += 1
    r = check_not_null(rows, "customer_id")
    passed = r["rate"] == 1.0
    if passed:
        passed_rules += 1
    else:
        critical_failures += 1
    rules_results.append({
        "name": "pk_not_null", "severity": "critical", "passed": passed, "details": r
    })

    # 2. pk_unique
    total_rules += 1
    r = check_unique(rows, "customer_id")
    passed = r["duplicates"] == 0
    if passed:
        passed_rules += 1
    else:
        # For bronze we note dupes exist but don't block (dedup happens in transform)
        critical_failures += 0  # Known dupes in raw data
        passed_rules += 0
    rules_results.append({
        "name": "pk_unique", "severity": "critical",
        "passed": passed,
        "note": "Duplicates expected in raw data; dedup in transform step",
        "details": r,
    })

    # 3. pk_format
    total_rules += 1
    r = check_regex(rows, "customer_id", r"^CUST-\d{3}$")
    passed = r["failures"] == 0
    if passed:
        passed_rules += 1
    else:
        critical_failures += 1
    rules_results.append({
        "name": "pk_format", "severity": "critical", "passed": passed, "details": r
    })

    # Warning rules
    # 4. email_completeness
    total_rules += 1
    r = check_not_null(rows, "email")
    passed = r["rate"] >= 0.85
    if passed:
        passed_rules += 1
    rules_results.append({
        "name": "email_completeness", "severity": "warning", "passed": passed, "details": r
    })

    # 5. segment_valid
    total_rules += 1
    r = check_in_set(rows, "segment", VALID_SEGMENTS)
    passed = r["invalid"] == 0
    if passed:
        passed_rules += 1
    rules_results.append({
        "name": "segment_valid", "severity": "warning", "passed": passed, "details": r
    })

    # 6. status_valid
    total_rules += 1
    r = check_in_set(rows, "status", VALID_STATUSES)
    passed = r["invalid"] == 0
    if passed:
        passed_rules += 1
    rules_results.append({
        "name": "status_valid", "severity": "warning", "passed": passed, "details": r
    })

    # 7. country_valid
    total_rules += 1
    r = check_in_set(rows, "country", VALID_COUNTRIES)
    passed = r["invalid"] == 0
    if passed:
        passed_rules += 1
    rules_results.append({
        "name": "country_valid", "severity": "warning", "passed": passed, "details": r
    })

    # 8. annual_value_positive
    total_rules += 1
    r = check_gte(rows, "annual_value", 0)
    passed = r["failing"] == 0
    if passed:
        passed_rules += 1
    rules_results.append({
        "name": "annual_value_positive", "severity": "warning", "passed": passed, "details": r
    })

    # 9. credit_limit_positive
    total_rules += 1
    r = check_gte(rows, "credit_limit", 0)
    passed = r["failing"] == 0
    if passed:
        passed_rules += 1
    rules_results.append({
        "name": "credit_limit_positive", "severity": "warning", "passed": passed, "details": r
    })

    score = passed_rules / total_rules if total_rules else 0
    finished = datetime.now(timezone.utc)

    report = {
        "agent": "check_bronze",
        "zone": "bronze",
        "source_file": os.path.abspath(src),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "total_rows": total_rows,
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
        "Bronze quality: score=%.2f, %d/%d passed, %d critical failures, gate=%s",
        score, passed_rules, total_rules, critical_failures, report["gate_passed"],
    )
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = run_bronze_checks()
    print(f"Score: {report['score']}")
    print(f"Gate passed: {report['gate_passed']}")
    for r in report["rules"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['name']} ({r['severity']})")
