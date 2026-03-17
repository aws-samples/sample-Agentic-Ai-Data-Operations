"""
Quality Check Functions - Lightweight Implementation
Can be used in unit tests without Spark/AWS dependencies.
"""

from typing import Dict, List, Any


def check_completeness(data: List[Dict[str, Any]], column: str, threshold: float, severity: str) -> Dict[str, Any]:
    """
    Check NOT NULL completeness.

    Args:
        data: List of dictionaries representing rows
        column: Column name to check
        threshold: Minimum acceptable ratio of non-null values
        severity: "critical" or "warning"

    Returns:
        Dictionary with check results
    """
    if not data:
        return {
            "column": column,
            "dimension": "completeness",
            "score": 1.0,
            "passed": True,
            "severity": severity,
            "detail": "Empty dataset"
        }

    total = len(data)
    non_null = sum(1 for row in data if row.get(column) is not None and row.get(column) != "")
    score = non_null / total
    passed = score >= threshold

    return {
        "column": column,
        "dimension": "completeness",
        "score": score,
        "passed": passed,
        "severity": severity,
        "detail": f"{non_null}/{total} non-null"
    }


def check_validity(data: List[Dict[str, Any]], column: str, valid_values: List, threshold: float, severity: str) -> Dict[str, Any]:
    """
    Check if values are in a valid set.

    Args:
        data: List of dictionaries representing rows
        column: Column name to check
        valid_values: List of valid values
        threshold: Minimum acceptable ratio
        severity: "critical" or "warning"

    Returns:
        Dictionary with check results
    """
    if not data:
        return {
            "column": column,
            "dimension": "validity",
            "score": 1.0,
            "passed": True,
            "severity": severity,
            "detail": "Empty dataset"
        }

    total = len(data)
    valid = sum(1 for row in data if row.get(column) in valid_values)
    score = valid / total
    passed = score >= threshold

    return {
        "column": column,
        "dimension": "validity",
        "score": score,
        "passed": passed,
        "severity": severity,
        "detail": f"{valid}/{total} valid"
    }


def check_uniqueness(data: List[Dict[str, Any]], column: str, threshold: float, severity: str) -> Dict[str, Any]:
    """
    Check if values are unique (no duplicates).

    Args:
        data: List of dictionaries representing rows
        column: Column name to check
        threshold: Minimum acceptable uniqueness ratio
        severity: "critical" or "warning"

    Returns:
        Dictionary with check results
    """
    if not data:
        return {
            "column": column,
            "dimension": "uniqueness",
            "score": 1.0,
            "passed": True,
            "severity": severity,
            "detail": "Empty dataset"
        }

    total = len(data)
    values = [row.get(column) for row in data]
    unique = len(set(values))
    score = unique / total
    passed = score >= threshold

    return {
        "column": column,
        "dimension": "uniqueness",
        "score": score,
        "passed": passed,
        "severity": severity,
        "detail": f"{unique}/{total} unique"
    }


def check_accuracy_range(data: List[Dict[str, Any]], column: str, min_val: float, max_val: float, threshold: float, severity: str) -> Dict[str, Any]:
    """
    Check if numeric values are within a valid range.

    Args:
        data: List of dictionaries representing rows
        column: Column name to check
        min_val: Minimum acceptable value
        max_val: Maximum acceptable value
        threshold: Minimum acceptable ratio
        severity: "critical" or "warning"

    Returns:
        Dictionary with check results
    """
    if not data:
        return {
            "column": column,
            "dimension": "accuracy",
            "score": 1.0,
            "passed": True,
            "severity": severity,
            "detail": "Empty dataset"
        }

    # Filter out nulls
    non_null_values = [row.get(column) for row in data if row.get(column) is not None]

    if not non_null_values:
        return {
            "column": column,
            "dimension": "accuracy",
            "score": 1.0,
            "passed": True,
            "severity": severity,
            "detail": "All values are null"
        }

    total = len(non_null_values)
    in_range = sum(1 for val in non_null_values if min_val <= val <= max_val)
    score = in_range / total
    passed = score >= threshold

    return {
        "column": column,
        "dimension": "accuracy",
        "score": score,
        "passed": passed,
        "severity": severity,
        "detail": f"{in_range}/{total} in range [{min_val}, {max_val}]"
    }


def check_accuracy_greater_than(data: List[Dict[str, Any]], column: str, min_val: float, threshold: float, severity: str) -> Dict[str, Any]:
    """
    Check if numeric values are greater than a minimum.

    Args:
        data: List of dictionaries representing rows
        column: Column name to check
        min_val: Minimum acceptable value (exclusive)
        threshold: Minimum acceptable ratio
        severity: "critical" or "warning"

    Returns:
        Dictionary with check results
    """
    if not data:
        return {
            "column": column,
            "dimension": "accuracy",
            "score": 1.0,
            "passed": True,
            "severity": severity,
            "detail": "Empty dataset"
        }

    # Filter out nulls
    non_null_values = [row.get(column) for row in data if row.get(column) is not None]

    if not non_null_values:
        return {
            "column": column,
            "dimension": "accuracy",
            "score": 1.0,
            "passed": True,
            "severity": severity,
            "detail": "All values are null"
        }

    total = len(non_null_values)
    valid = sum(1 for val in non_null_values if val > min_val)
    score = valid / total
    passed = score >= threshold

    return {
        "column": column,
        "dimension": "accuracy",
        "score": score,
        "passed": passed,
        "severity": severity,
        "detail": f"{valid}/{total} > {min_val}"
    }


def check_referential_integrity(child_data: List[Dict[str, Any]], child_col: str, parent_data: List[Dict[str, Any]], parent_col: str, threshold: float, severity: str) -> Dict[str, Any]:
    """
    Check if foreign key values exist in parent table.

    Args:
        child_data: Child table rows
        child_col: Foreign key column in child
        parent_data: Parent table rows
        parent_col: Primary key column in parent
        threshold: Minimum acceptable ratio
        severity: "critical" or "warning"

    Returns:
        Dictionary with check results
    """
    if not child_data:
        return {
            "dimension": "referential_integrity",
            "score": 1.0,
            "passed": True,
            "severity": severity,
            "detail": "Empty child dataset"
        }

    # Build set of parent keys
    parent_keys = {row.get(parent_col) for row in parent_data}

    # Check child keys
    total = len(child_data)
    valid = sum(1 for row in child_data if row.get(child_col) in parent_keys)
    score = valid / total
    passed = score >= threshold

    return {
        "dimension": "referential_integrity",
        "score": score,
        "passed": passed,
        "severity": severity,
        "detail": f"{valid}/{total} FK references exist"
    }


def calculate_overall_score(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate overall quality score and identify critical failures.

    Args:
        results: List of check results

    Returns:
        Dictionary with overall metrics
    """
    if not results:
        return {
            "total_checks": 0,
            "passed_checks": 0,
            "failed_checks": 0,
            "overall_score": 1.0,
            "critical_failures": 0
        }

    total_checks = len(results)
    passed_checks = sum(1 for r in results if r["passed"])
    failed_checks = total_checks - passed_checks
    overall_score = passed_checks / total_checks
    critical_failures = sum(1 for r in results if not r["passed"] and r["severity"] == "critical")

    return {
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "overall_score": overall_score,
        "critical_failures": critical_failures
    }
