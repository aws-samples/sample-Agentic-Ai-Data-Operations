"""
Unit Tests for Quality Check Functions
Tests quality check logic in isolation with synthetic data.
"""

import os
import importlib.util
import pytest

# Load quality functions module
_quality_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "scripts", "quality", "quality_functions.py"
)
_spec = importlib.util.spec_from_file_location("quality_functions", os.path.abspath(_quality_path))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

check_completeness = _mod.check_completeness
check_validity = _mod.check_validity
check_uniqueness = _mod.check_uniqueness
check_accuracy_range = _mod.check_accuracy_range
check_accuracy_greater_than = _mod.check_accuracy_greater_than
check_referential_integrity = _mod.check_referential_integrity
calculate_overall_score = _mod.calculate_overall_score


# ============================================================================
# Test Completeness
# ============================================================================

def test_completeness_all_present():
    """Test completeness when all values are present"""
    data = [{"col": "A"}, {"col": "B"}, {"col": "C"}]
    result = check_completeness(data, "col", 1.0, "critical")
    assert result["score"] == 1.0
    assert result["passed"] is True


def test_completeness_some_nulls():
    """Test completeness when some nulls exist"""
    data = [{"col": "A"}, {"col": None}, {"col": "C"}, {"col": None}]
    result = check_completeness(data, "col", 0.5, "warning")
    assert result["score"] == 0.5
    assert result["passed"] is True


def test_completeness_below_threshold():
    """Test completeness below threshold"""
    data = [{"col": "A"}, {"col": None}, {"col": None}, {"col": None}]
    result = check_completeness(data, "col", 0.5, "critical")
    assert result["score"] == 0.25
    assert result["passed"] is False


def test_completeness_empty_df():
    """Test completeness with empty dataframe"""
    data = []
    result = check_completeness(data, "col", 1.0, "critical")
    assert result["score"] == 1.0
    assert result["passed"] is True


# ============================================================================
# Test Validity
# ============================================================================

def test_validity_all_valid():
    """Test validity when all values are valid"""
    data = [{"fund_type": "ETF"}, {"fund_type": "Mutual Fund"}, {"fund_type": "ETF"}]
    result = check_validity(data, "fund_type", ["ETF", "Mutual Fund"], 1.0, "critical")
    assert result["score"] == 1.0
    assert result["passed"] is True


def test_validity_some_invalid():
    """Test validity when some values are invalid"""
    data = [
        {"fund_type": "ETF"},
        {"fund_type": "Invalid"},
        {"fund_type": "Mutual Fund"},
        {"fund_type": "Unknown"}
    ]
    result = check_validity(data, "fund_type", ["ETF", "Mutual Fund"], 0.5, "warning")
    assert result["score"] == 0.5
    assert result["passed"] is True


def test_validity_below_threshold():
    """Test validity below threshold"""
    data = [
        {"fund_type": "ETF"},
        {"fund_type": "Bad1"},
        {"fund_type": "Bad2"},
        {"fund_type": "Bad3"}
    ]
    result = check_validity(data, "fund_type", ["ETF", "Mutual Fund"], 0.5, "critical")
    assert result["score"] == 0.25
    assert result["passed"] is False


# ============================================================================
# Test Uniqueness
# ============================================================================

def test_uniqueness_all_unique():
    """Test uniqueness when all values are unique"""
    data = [{"ticker": "A"}, {"ticker": "B"}, {"ticker": "C"}, {"ticker": "D"}]
    result = check_uniqueness(data, "ticker", 1.0, "critical")
    assert result["score"] == 1.0
    assert result["passed"] is True


def test_uniqueness_some_duplicates():
    """Test uniqueness when some duplicates exist"""
    data = [{"ticker": "A"}, {"ticker": "B"}, {"ticker": "B"}, {"ticker": "C"}]
    result = check_uniqueness(data, "ticker", 0.75, "warning")
    assert result["score"] == 0.75
    assert result["passed"] is True


def test_uniqueness_below_threshold():
    """Test uniqueness below threshold"""
    data = [{"ticker": "A"}, {"ticker": "A"}, {"ticker": "A"}, {"ticker": "A"}]
    result = check_uniqueness(data, "ticker", 0.5, "critical")
    assert result["score"] == 0.25
    assert result["passed"] is False


# ============================================================================
# Test Accuracy Range
# ============================================================================

def test_accuracy_range_all_in_range():
    """Test accuracy when all values are in range"""
    data = [
        {"expense_ratio": 0.5},
        {"expense_ratio": 1.0},
        {"expense_ratio": 1.5},
        {"expense_ratio": 2.0}
    ]
    result = check_accuracy_range(data, "expense_ratio", 0.0, 3.0, 1.0, "critical")
    assert result["score"] == 1.0
    assert result["passed"] is True


def test_accuracy_range_some_out_of_range():
    """Test accuracy when some values are out of range"""
    data = [
        {"expense_ratio": 0.5},
        {"expense_ratio": 1.0},
        {"expense_ratio": 4.0},
        {"expense_ratio": 5.0}
    ]
    result = check_accuracy_range(data, "expense_ratio", 0.0, 3.0, 0.5, "warning")
    assert result["score"] == 0.5
    assert result["passed"] is True


def test_accuracy_range_with_nulls():
    """Test accuracy range with null values (should be ignored)"""
    data = [
        {"expense_ratio": 0.5},
        {"expense_ratio": 1.0},
        {"expense_ratio": None},
        {"expense_ratio": None}
    ]
    result = check_accuracy_range(data, "expense_ratio", 0.0, 3.0, 1.0, "critical")
    assert result["score"] == 1.0
    assert result["passed"] is True


def test_accuracy_range_below_threshold():
    """Test accuracy range below threshold"""
    data = [
        {"expense_ratio": 0.5},
        {"expense_ratio": 4.0},
        {"expense_ratio": 5.0},
        {"expense_ratio": 6.0}
    ]
    result = check_accuracy_range(data, "expense_ratio", 0.0, 3.0, 0.5, "critical")
    assert result["score"] == 0.25
    assert result["passed"] is False


# ============================================================================
# Test Accuracy Greater Than
# ============================================================================

def test_accuracy_greater_than_all_valid():
    """Test accuracy when all values > threshold"""
    data = [{"nav": 10.0}, {"nav": 20.0}, {"nav": 30.0}]
    result = check_accuracy_greater_than(data, "nav", 0, 1.0, "critical")
    assert result["score"] == 1.0
    assert result["passed"] is True


def test_accuracy_greater_than_some_invalid():
    """Test accuracy when some values <= threshold"""
    data = [{"nav": 10.0}, {"nav": -5.0}, {"nav": 0.0}, {"nav": 20.0}]
    result = check_accuracy_greater_than(data, "nav", 0, 0.5, "warning")
    assert result["score"] == 0.5
    assert result["passed"] is True


def test_accuracy_greater_than_below_threshold():
    """Test accuracy greater than below threshold"""
    data = [{"nav": 10.0}, {"nav": -5.0}, {"nav": -10.0}, {"nav": 0.0}]
    result = check_accuracy_greater_than(data, "nav", 0, 0.5, "critical")
    assert result["score"] == 0.25
    assert result["passed"] is False


# ============================================================================
# Test Referential Integrity
# ============================================================================

def test_referential_integrity_all_valid():
    """Test referential integrity when all FKs resolve"""
    parent = [{"ticker": "A"}, {"ticker": "B"}, {"ticker": "C"}]
    child = [{"fund_ticker": "A"}, {"fund_ticker": "B"}, {"fund_ticker": "C"}]
    result = check_referential_integrity(child, "fund_ticker", parent, "ticker", 1.0, "critical")
    assert result["score"] == 1.0
    assert result["passed"] is True


def test_referential_integrity_some_orphans():
    """Test referential integrity when some orphans exist"""
    parent = [{"ticker": "A"}, {"ticker": "B"}]
    child = [{"fund_ticker": "A"}, {"fund_ticker": "B"}, {"fund_ticker": "C"}, {"fund_ticker": "D"}]
    result = check_referential_integrity(child, "fund_ticker", parent, "ticker", 0.5, "warning")
    assert result["score"] == 0.5
    assert result["passed"] is True


def test_referential_integrity_below_threshold():
    """Test referential integrity below threshold"""
    parent = [{"ticker": "A"}]
    child = [{"fund_ticker": "A"}, {"fund_ticker": "B"}, {"fund_ticker": "C"}, {"fund_ticker": "D"}]
    result = check_referential_integrity(child, "fund_ticker", parent, "ticker", 0.5, "critical")
    assert result["score"] == 0.25
    assert result["passed"] is False


def test_referential_integrity_empty_child():
    """Test referential integrity with empty child"""
    parent = [{"ticker": "A"}, {"ticker": "B"}]
    child = []
    result = check_referential_integrity(child, "fund_ticker", parent, "ticker", 1.0, "critical")
    assert result["score"] == 1.0
    assert result["passed"] is True


# ============================================================================
# Test Overall Score Calculation
# ============================================================================

def test_overall_score_all_pass():
    """Test overall score when all checks pass"""
    results = [
        {"passed": True, "severity": "critical"},
        {"passed": True, "severity": "critical"}
    ]
    summary = calculate_overall_score(results)
    assert summary["overall_score"] == 1.0
    assert summary["critical_failures"] == 0


def test_overall_score_some_fail():
    """Test overall score when some checks fail"""
    results = [
        {"passed": False, "severity": "critical"},
        {"passed": True, "severity": "critical"}
    ]
    summary = calculate_overall_score(results)
    assert summary["overall_score"] == 0.5
    assert summary["critical_failures"] == 1


def test_critical_failure_detection():
    """Test detection of critical failures"""
    results = [
        {"passed": False, "severity": "critical"},
        {"passed": False, "severity": "warning"}
    ]
    summary = calculate_overall_score(results)
    assert summary["critical_failures"] == 1


def test_empty_results():
    """Test overall score with no checks"""
    results = []
    summary = calculate_overall_score(results)
    assert summary["overall_score"] == 1.0
    assert summary["total_checks"] == 0
