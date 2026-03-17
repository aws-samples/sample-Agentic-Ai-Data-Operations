#!/usr/bin/env python3
"""
Quality check runner for the sales_transactions workload.

Reads quality_rules.yaml, applies every rule against a CSV file,
calculates per-dimension and overall quality scores, and writes a
JSON report to workloads/sales_transactions/data/quality_reports/.

Usage:
    python3 scripts/quality/run_quality_checks.py <path/to/data.csv> [--threshold 0.80]

Exit codes:
    0  quality score >= threshold (default 0.80)
    1  quality score < threshold OR a critical rule failed
"""

import csv
import datetime
import json
import os
import re
import sys

import yaml


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKLOAD_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
CONFIG_DIR = os.path.join(WORKLOAD_DIR, "config")
QUALITY_RULES_PATH = os.path.join(CONFIG_DIR, "quality_rules.yaml")
REPORT_DIR = os.path.join(WORKLOAD_DIR, "data", "quality_reports")


# ---------------------------------------------------------------------------
# Rule evaluation helpers
# ---------------------------------------------------------------------------

def _is_null(value):
    """Return True when a CSV cell is effectively null/empty."""
    return value is None or value.strip() == ""


def evaluate_null_rate(rows, column, operator, threshold):
    """Check that the null rate for *column* satisfies operator/threshold."""
    total = len(rows)
    if total == 0:
        return True, 0.0, []
    null_count = sum(1 for r in rows if _is_null(r.get(column, "")))
    null_rate = null_count / total
    passed = _compare(null_rate, operator, threshold)
    failing_rows = [
        r["order_id"] for r in rows if _is_null(r.get(column, ""))
    ] if not passed else []
    return passed, null_rate, failing_rows


def evaluate_min_value(rows, column, operator, threshold):
    """Check that the minimum value in *column* satisfies operator/threshold."""
    values = []
    failing_rows = []
    for r in rows:
        raw = r.get(column, "")
        if _is_null(raw):
            continue
        try:
            val = float(raw)
        except ValueError:
            failing_rows.append(r["order_id"])
            continue
        values.append(val)
        if not _compare(val, operator, threshold):
            failing_rows.append(r["order_id"])
    if not values:
        return True, None, []
    passed = len(failing_rows) == 0
    return passed, min(values), failing_rows


def evaluate_max_value(rows, column, operator, threshold):
    """Check that the maximum value in *column* satisfies operator/threshold."""
    values = []
    failing_rows = []
    for r in rows:
        raw = r.get(column, "")
        if _is_null(raw):
            continue
        try:
            val = float(raw)
        except ValueError:
            failing_rows.append(r["order_id"])
            continue
        values.append(val)
        if not _compare(val, operator, threshold):
            failing_rows.append(r["order_id"])
    if not values:
        return True, None, []
    passed = len(failing_rows) == 0
    return passed, max(values), failing_rows


def evaluate_cross_column(rows, expression):
    """Evaluate a cross-column expression row-by-row.

    Supported expression: ``revenue <= quantity * unit_price``
    """
    failing_rows = []
    for r in rows:
        try:
            revenue = float(r["revenue"])
            quantity = float(r["quantity"])
            unit_price = float(r["unit_price"])
        except (ValueError, KeyError):
            failing_rows.append(r.get("order_id", "UNKNOWN"))
            continue
        # Tolerance of 0.01 for floating-point rounding
        if revenue > quantity * unit_price + 0.01:
            failing_rows.append(r["order_id"])
    passed = len(failing_rows) == 0
    return passed, len(failing_rows), failing_rows


def evaluate_conditional(rows, condition, expectation):
    """Evaluate a conditional rule: if *condition* then *expectation*.

    Supported patterns:
        condition:   ``status == 'pending'``
        expectation: ``ship_date == ''``
    """
    # Parse condition  "column == 'value'"
    cond_match = re.match(r"(\w+)\s*==\s*'([^']*)'", condition)
    # Parse expectation "column == 'value'" or "column == ''"
    exp_match = re.match(r"(\w+)\s*==\s*'([^']*)'", expectation)
    if not cond_match or not exp_match:
        return False, 0, ["PARSE_ERROR"]

    cond_col, cond_val = cond_match.group(1), cond_match.group(2)
    exp_col, exp_val = exp_match.group(1), exp_match.group(2)

    failing_rows = []
    for r in rows:
        if r.get(cond_col, "").strip() == cond_val:
            actual = r.get(exp_col, "").strip()
            if actual != exp_val:
                failing_rows.append(r.get("order_id", "UNKNOWN"))
    passed = len(failing_rows) == 0
    return passed, len(failing_rows), failing_rows


def evaluate_allowed_values(rows, column, allowed_values):
    """Check that every non-null value in *column* is in *allowed_values*."""
    failing_rows = []
    for r in rows:
        val = r.get(column, "").strip()
        if val == "":
            continue
        if val not in allowed_values:
            failing_rows.append(r.get("order_id", "UNKNOWN"))
    passed = len(failing_rows) == 0
    return passed, len(failing_rows), failing_rows


def evaluate_regex(rows, column, pattern, nullable=False):
    """Check that every value in *column* matches *pattern*.

    If nullable=True, empty values are skipped.
    """
    compiled = re.compile(pattern)
    failing_rows = []
    for r in rows:
        val = r.get(column, "").strip()
        if nullable and val == "":
            continue
        if val == "" or not compiled.match(val):
            failing_rows.append(r.get("order_id", "UNKNOWN"))
    passed = len(failing_rows) == 0
    return passed, len(failing_rows), failing_rows


def evaluate_unique(rows, column):
    """Check that all non-null values in *column* are unique."""
    seen = {}
    duplicates = []
    for r in rows:
        val = r.get(column, "").strip()
        if val == "":
            continue
        if val in seen:
            duplicates.append(r.get("order_id", "UNKNOWN"))
        else:
            seen[val] = True
    passed = len(duplicates) == 0
    return passed, len(duplicates), duplicates


# ---------------------------------------------------------------------------
# Comparison helper
# ---------------------------------------------------------------------------

def _compare(value, operator, threshold):
    """Apply a comparison operator."""
    if operator == "<=":
        return value <= threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == ">":
        return value > threshold
    if operator == "==":
        return value == threshold
    if operator == "!=":
        return value != threshold
    raise ValueError(f"Unknown operator: {operator}")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def load_rules(rules_path=None):
    """Load and return the quality rules dictionary."""
    path = rules_path or QUALITY_RULES_PATH
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_csv(csv_path):
    """Load a CSV file and return a list of row dicts."""
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def run_rule(rule, rows):
    """Run a single rule against *rows* and return a result dict."""
    check = rule.get("check")
    result = {
        "rule_id": rule["rule_id"],
        "name": rule["name"],
        "description": rule.get("description", ""),
        "severity": rule.get("severity", "warning"),
        "passed": False,
        "details": {},
        "failing_rows": [],
    }

    try:
        if check == "null_rate":
            passed, actual, failing = evaluate_null_rate(
                rows, rule["column"], rule["operator"], rule["threshold"]
            )
            result["passed"] = passed
            result["details"] = {
                "actual_null_rate": round(actual, 4),
                "threshold": rule["threshold"],
                "operator": rule["operator"],
            }
            result["failing_rows"] = failing

        elif check == "min_value":
            passed, actual, failing = evaluate_min_value(
                rows, rule["column"], rule["operator"], rule["threshold"]
            )
            result["passed"] = passed
            result["details"] = {
                "actual_min": actual,
                "threshold": rule["threshold"],
                "operator": rule["operator"],
            }
            result["failing_rows"] = failing

        elif check == "max_value":
            passed, actual, failing = evaluate_max_value(
                rows, rule["column"], rule["operator"], rule["threshold"]
            )
            result["passed"] = passed
            result["details"] = {
                "actual_max": actual,
                "threshold": rule["threshold"],
                "operator": rule["operator"],
            }
            result["failing_rows"] = failing

        elif check == "cross_column":
            passed, count, failing = evaluate_cross_column(
                rows, rule["expression"]
            )
            result["passed"] = passed
            result["details"] = {
                "expression": rule["expression"],
                "failing_count": count,
            }
            result["failing_rows"] = failing

        elif check == "conditional":
            passed, count, failing = evaluate_conditional(
                rows, rule["condition"], rule["expectation"]
            )
            result["passed"] = passed
            result["details"] = {
                "condition": rule["condition"],
                "expectation": rule["expectation"],
                "failing_count": count,
            }
            result["failing_rows"] = failing

        elif check == "allowed_values":
            passed, count, failing = evaluate_allowed_values(
                rows, rule["column"], rule["allowed_values"]
            )
            result["passed"] = passed
            result["details"] = {
                "allowed_values": rule["allowed_values"],
                "failing_count": count,
            }
            result["failing_rows"] = failing

        elif check == "regex":
            passed, count, failing = evaluate_regex(
                rows, rule["column"], rule["pattern"], nullable=False
            )
            result["passed"] = passed
            result["details"] = {
                "pattern": rule["pattern"],
                "failing_count": count,
            }
            result["failing_rows"] = failing

        elif check == "regex_nullable":
            passed, count, failing = evaluate_regex(
                rows, rule["column"], rule["pattern"], nullable=True
            )
            result["passed"] = passed
            result["details"] = {
                "pattern": rule["pattern"],
                "failing_count": count,
            }
            result["failing_rows"] = failing

        elif check == "unique":
            passed, count, failing = evaluate_unique(rows, rule["column"])
            result["passed"] = passed
            result["details"] = {"duplicate_count": count}
            result["failing_rows"] = failing

        else:
            result["details"] = {"error": f"Unknown check type: {check}"}

    except Exception as exc:
        result["details"] = {"error": str(exc)}

    return result


def run_all_checks(rules_config, rows):
    """Run every rule in *rules_config* and return the full report dict."""
    dimensions = rules_config["quality_rules"]["dimensions"]
    thresholds = rules_config["quality_rules"]["thresholds"]

    all_results = []
    dimension_results = {}
    critical_failures = []

    for dim_name, rules_list in dimensions.items():
        dim_passed = 0
        dim_total = 0
        dim_results = []

        for rule in rules_list:
            result = run_rule(rule, rows)
            dim_total += 1
            if result["passed"]:
                dim_passed += 1
            else:
                if result["severity"] == "critical":
                    critical_failures.append(result)
            dim_results.append(result)
            all_results.append(result)

        dim_score = dim_passed / dim_total if dim_total > 0 else 0.0
        dimension_results[dim_name] = {
            "passed": dim_passed,
            "total": dim_total,
            "score": round(dim_score, 4),
            "results": dim_results,
        }

    total_rules = len(all_results)
    total_passed = sum(1 for r in all_results if r["passed"])
    overall_score = total_passed / total_rules if total_rules > 0 else 0.0

    report = {
        "workload": rules_config["quality_rules"]["workload"],
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "row_count": len(rows),
        "overall": {
            "score": round(overall_score, 4),
            "passed": total_passed,
            "total": total_rules,
        },
        "thresholds": thresholds,
        "critical_failures": [
            {
                "rule_id": cf["rule_id"],
                "name": cf["name"],
                "description": cf["description"],
                "failing_rows": cf["failing_rows"][:10],  # cap for readability
            }
            for cf in critical_failures
        ],
        "has_critical_failures": len(critical_failures) > 0,
        "dimensions": {
            dim_name: {
                "score": dim_data["score"],
                "passed": dim_data["passed"],
                "total": dim_data["total"],
                "rules": [
                    {
                        "rule_id": r["rule_id"],
                        "name": r["name"],
                        "passed": r["passed"],
                        "severity": r["severity"],
                        "details": r["details"],
                    }
                    for r in dim_data["results"]
                ],
            }
            for dim_name, dim_data in dimension_results.items()
        },
    }

    return report


def write_report(report, report_dir=None):
    """Write the report JSON to disk and return the file path."""
    out_dir = report_dir or REPORT_DIR
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    filename = f"quality_report_{timestamp}.json"
    filepath = os.path.join(out_dir, filename)
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)
    return filepath


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main():
    """CLI entry-point."""
    if len(sys.argv) < 2:
        print("Usage: python3 run_quality_checks.py <csv_path> [--threshold N]")
        sys.exit(1)

    csv_path = sys.argv[1]
    threshold = 0.80  # default Bronze->Silver

    # Parse optional --threshold flag
    if "--threshold" in sys.argv:
        idx = sys.argv.index("--threshold")
        if idx + 1 < len(sys.argv):
            threshold = float(sys.argv[idx + 1])

    if not os.path.isfile(csv_path):
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    rules_config = load_rules()
    rows = load_csv(csv_path)

    print(f"Loaded {len(rows)} rows from {csv_path}")
    print(f"Running quality checks (threshold={threshold}) ...")

    report = run_all_checks(rules_config, rows)
    filepath = write_report(report)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"QUALITY REPORT SUMMARY")
    print(f"{'=' * 60}")
    print(f"Overall score:  {report['overall']['score']:.4f}  "
          f"({report['overall']['passed']}/{report['overall']['total']} rules passed)")
    print()

    for dim_name, dim_data in report["dimensions"].items():
        status = "PASS" if dim_data["score"] == 1.0 else "WARN"
        print(f"  {dim_name:<20s} {dim_data['score']:.4f}  "
              f"({dim_data['passed']}/{dim_data['total']})  [{status}]")

    print()
    if report["has_critical_failures"]:
        print(f"CRITICAL FAILURES: {len(report['critical_failures'])}")
        for cf in report["critical_failures"]:
            print(f"  - {cf['rule_id']}: {cf['name']}")
    else:
        print("No critical failures.")

    print(f"\nReport written to: {filepath}")
    print(f"{'=' * 60}")

    # Exit code
    if report["has_critical_failures"]:
        print("\nRESULT: FAIL (critical rule failures)")
        sys.exit(1)
    elif report["overall"]["score"] < threshold:
        print(f"\nRESULT: FAIL (score {report['overall']['score']:.4f} < threshold {threshold})")
        sys.exit(1)
    else:
        print(f"\nRESULT: PASS (score {report['overall']['score']:.4f} >= threshold {threshold})")
        sys.exit(0)


if __name__ == "__main__":
    main()
