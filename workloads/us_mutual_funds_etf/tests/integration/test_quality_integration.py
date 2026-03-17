"""
Integration Tests for Quality Checks
Tests quality checks against realistic Silver and Gold data scenarios.
"""

import os
import importlib.util
import pytest
from datetime import date

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
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_silver_funds():
    """Create sample funds_clean data"""
    return [
        {
            "fund_ticker": "VTI",
            "fund_name": "Vanguard Total Stock Market ETF",
            "fund_type": "ETF",
            "management_company": "Vanguard",
            "inception_date": date(2010, 5, 24),
            "fund_category": "Total Market Equity",
            "geographic_focus": "US",
            "sector_focus": "Diversified"
        },
        {
            "fund_ticker": "SPY",
            "fund_name": "SPDR S&P 500 ETF Trust",
            "fund_type": "ETF",
            "management_company": "State Street",
            "inception_date": date(1993, 1, 22),
            "fund_category": "Large Cap Equity",
            "geographic_focus": "US",
            "sector_focus": "Diversified"
        },
        {
            "fund_ticker": "BND",
            "fund_name": "Vanguard Total Bond Market ETF",
            "fund_type": "ETF",
            "management_company": "Vanguard",
            "inception_date": date(2007, 4, 3),
            "fund_category": "Bond",
            "geographic_focus": "US",
            "sector_focus": "Diversified"
        }
    ]


@pytest.fixture
def sample_silver_market():
    """Create sample market_data_clean data"""
    return [
        {
            "fund_ticker": "VTI",
            "asset_class": "Equity",
            "benchmark_index": "CRSP US Total Market Index",
            "morningstar_category": "Large Blend",
            "expense_ratio_pct": 0.03,
            "dividend_yield_pct": 1.5,
            "beta": 1.05,
            "sharpe_ratio": 1.2,
            "morningstar_rating": 4
        },
        {
            "fund_ticker": "SPY",
            "asset_class": "Equity",
            "benchmark_index": "S&P 500",
            "morningstar_category": "Large Blend",
            "expense_ratio_pct": 0.09,
            "dividend_yield_pct": 1.4,
            "beta": 1.00,
            "sharpe_ratio": 1.1,
            "morningstar_rating": 5
        },
        {
            "fund_ticker": "BND",
            "asset_class": "Fixed Income",
            "benchmark_index": "Bloomberg Barclays Aggregate",
            "morningstar_category": "Intermediate Bond",
            "expense_ratio_pct": 0.04,
            "dividend_yield_pct": 2.2,
            "beta": 0.15,
            "sharpe_ratio": 0.8,
            "morningstar_rating": 3
        }
    ]


@pytest.fixture
def sample_silver_nav():
    """Create sample nav_clean data"""
    return [
        {
            "fund_ticker": "VTI",
            "price_date": date(2025, 1, 15),
            "nav": 250.5,
            "total_assets_millions": 1500000.0,
            "return_1mo_pct": 2.5,
            "return_3mo_pct": 5.0,
            "return_ytd_pct": 8.0,
            "return_1yr_pct": 12.5,
            "return_3yr_pct": 18.0,
            "return_5yr_pct": 22.0
        },
        {
            "fund_ticker": "SPY",
            "price_date": date(2025, 1, 15),
            "nav": 480.0,
            "total_assets_millions": 450000.0,
            "return_1mo_pct": 2.0,
            "return_3mo_pct": 4.5,
            "return_ytd_pct": 7.5,
            "return_1yr_pct": 11.0,
            "return_3yr_pct": 16.5,
            "return_5yr_pct": 20.0
        },
        {
            "fund_ticker": "BND",
            "price_date": date(2025, 1, 15),
            "nav": 78.5,
            "total_assets_millions": 300000.0,
            "return_1mo_pct": 0.5,
            "return_3mo_pct": 1.0,
            "return_ytd_pct": 2.0,
            "return_1yr_pct": 3.5,
            "return_3yr_pct": 5.0,
            "return_5yr_pct": 6.5
        }
    ]


@pytest.fixture
def sample_gold_dim_fund():
    """Create sample dim_fund data"""
    return [
        {
            "fund_ticker": "VTI",
            "fund_name": "Vanguard Total Stock Market ETF",
            "fund_type": "ETF",
            "asset_class": "Equity"
        },
        {
            "fund_ticker": "SPY",
            "fund_name": "SPDR S&P 500 ETF Trust",
            "fund_type": "ETF",
            "asset_class": "Equity"
        }
    ]


@pytest.fixture
def sample_gold_dim_category():
    """Create sample dim_category data"""
    return [
        {
            "category_key": 1,
            "fund_category": "Total Market Equity",
            "asset_class": "Equity",
            "typical_expense_min": 0.03,
            "typical_expense_max": 0.10
        },
        {
            "category_key": 2,
            "fund_category": "Large Cap Equity",
            "asset_class": "Equity",
            "typical_expense_min": 0.04,
            "typical_expense_max": 0.15
        }
    ]


@pytest.fixture
def sample_gold_dim_date():
    """Create sample dim_date data"""
    return [
        {
            "date_key": 20250115,
            "as_of_date": date(2025, 1, 15),
            "month": 1,
            "month_name": "January",
            "quarter": 1,
            "year": 2025
        },
        {
            "date_key": 20250215,
            "as_of_date": date(2025, 2, 15),
            "month": 2,
            "month_name": "February",
            "quarter": 1,
            "year": 2025
        }
    ]


@pytest.fixture
def sample_gold_fact():
    """Create sample fact_fund_performance data"""
    return [
        {
            "fact_id": 1,
            "fund_ticker": "VTI",
            "category_key": 1,
            "date_key": 20250115,
            "nav": 250.5,
            "total_assets_millions": 1500000.0,
            "expense_ratio_pct": 0.03
        },
        {
            "fact_id": 2,
            "fund_ticker": "SPY",
            "category_key": 2,
            "date_key": 20250115,
            "nav": 480.0,
            "total_assets_millions": 450000.0,
            "expense_ratio_pct": 0.09
        }
    ]


# ============================================================================
# Test Silver Quality Gate (Full Pipeline)
# ============================================================================

def test_silver_funds_quality_pass(sample_silver_funds):
    """Test Silver funds quality checks pass"""
    results = []

    # Completeness checks
    results.append(check_completeness(sample_silver_funds, "fund_ticker", 1.0, "critical"))
    results.append(check_completeness(sample_silver_funds, "fund_name", 0.95, "warning"))
    results.append(check_completeness(sample_silver_funds, "fund_type", 1.0, "critical"))

    # Validity checks
    results.append(check_validity(sample_silver_funds, "fund_type", ["ETF", "Mutual Fund"], 1.0, "critical"))

    # Uniqueness checks
    results.append(check_uniqueness(sample_silver_funds, "fund_ticker", 1.0, "critical"))

    # All checks should pass
    assert all(r["passed"] for r in results)


def test_silver_market_quality_pass(sample_silver_market):
    """Test Silver market_data quality checks pass"""
    results = []

    # Completeness
    results.append(check_completeness(sample_silver_market, "fund_ticker", 1.0, "critical"))
    results.append(check_completeness(sample_silver_market, "expense_ratio_pct", 0.90, "warning"))

    # Accuracy
    results.append(check_accuracy_range(sample_silver_market, "expense_ratio_pct", 0.0, 3.0, 1.0, "critical"))
    results.append(check_accuracy_range(sample_silver_market, "beta", 0.0, 3.0, 0.95, "warning"))
    results.append(check_accuracy_range(sample_silver_market, "morningstar_rating", 1, 5, 1.0, "critical"))

    # All checks should pass
    assert all(r["passed"] for r in results)


def test_silver_nav_quality_pass(sample_silver_nav, sample_silver_funds):
    """Test Silver NAV quality checks pass"""
    results = []

    # Completeness
    results.append(check_completeness(sample_silver_nav, "fund_ticker", 1.0, "critical"))
    results.append(check_completeness(sample_silver_nav, "price_date", 1.0, "critical"))
    results.append(check_completeness(sample_silver_nav, "nav", 1.0, "critical"))

    # Accuracy
    results.append(check_accuracy_greater_than(sample_silver_nav, "nav", 0, 1.0, "critical"))
    results.append(check_accuracy_range(sample_silver_nav, "return_1yr_pct", -50, 100, 1.0, "warning"))

    # Referential Integrity
    results.append(check_referential_integrity(sample_silver_nav, "fund_ticker", sample_silver_funds, "fund_ticker", 1.0, "critical"))

    # All checks should pass
    assert all(r["passed"] for r in results)


def test_silver_overall_score_calculation(sample_silver_funds, sample_silver_market, sample_silver_nav):
    """Test overall Silver quality score calculation"""
    results = []

    # Run all Silver checks
    results.append(check_completeness(sample_silver_funds, "fund_ticker", 1.0, "critical"))
    results.append(check_validity(sample_silver_funds, "fund_type", ["ETF", "Mutual Fund"], 1.0, "critical"))
    results.append(check_uniqueness(sample_silver_funds, "fund_ticker", 1.0, "critical"))
    results.append(check_accuracy_range(sample_silver_market, "expense_ratio_pct", 0.0, 3.0, 1.0, "critical"))
    results.append(check_accuracy_greater_than(sample_silver_nav, "nav", 0, 1.0, "critical"))

    summary = calculate_overall_score(results)
    assert summary["overall_score"] >= 0.80, f"Silver quality score {summary['overall_score']:.3f} < 0.80"
    assert summary["critical_failures"] == 0


# ============================================================================
# Test Gold Quality Gate (Full Pipeline)
# ============================================================================

def test_gold_dim_fund_quality_pass(sample_gold_dim_fund):
    """Test Gold dim_fund quality checks pass"""
    results = []

    results.append(check_completeness(sample_gold_dim_fund, "fund_ticker", 1.0, "critical"))
    results.append(check_completeness(sample_gold_dim_fund, "fund_name", 1.0, "critical"))
    results.append(check_completeness(sample_gold_dim_fund, "asset_class", 1.0, "critical"))
    results.append(check_uniqueness(sample_gold_dim_fund, "fund_ticker", 1.0, "critical"))

    assert all(r["passed"] for r in results)


def test_gold_dim_category_quality_pass(sample_gold_dim_category):
    """Test Gold dim_category quality checks pass"""
    results = []

    results.append(check_completeness(sample_gold_dim_category, "category_key", 1.0, "critical"))
    results.append(check_completeness(sample_gold_dim_category, "fund_category", 1.0, "critical"))
    results.append(check_uniqueness(sample_gold_dim_category, "category_key", 1.0, "critical"))

    # Check min <= max
    valid_expense = all(
        row["typical_expense_min"] <= row["typical_expense_max"]
        for row in sample_gold_dim_category
    )
    assert valid_expense

    assert all(r["passed"] for r in results)


def test_gold_dim_date_quality_pass(sample_gold_dim_date):
    """Test Gold dim_date quality checks pass"""
    results = []

    results.append(check_completeness(sample_gold_dim_date, "date_key", 1.0, "critical"))
    results.append(check_completeness(sample_gold_dim_date, "as_of_date", 1.0, "critical"))
    results.append(check_uniqueness(sample_gold_dim_date, "date_key", 1.0, "critical"))
    results.append(check_accuracy_range(sample_gold_dim_date, "month", 1, 12, 1.0, "critical"))
    results.append(check_accuracy_range(sample_gold_dim_date, "quarter", 1, 4, 1.0, "critical"))

    assert all(r["passed"] for r in results)


def test_gold_fact_referential_integrity(sample_gold_fact, sample_gold_dim_fund, sample_gold_dim_date):
    """Test Gold fact table referential integrity"""
    results = []

    results.append(check_referential_integrity(sample_gold_fact, "fund_ticker", sample_gold_dim_fund, "fund_ticker", 1.0, "critical"))
    results.append(check_referential_integrity(sample_gold_fact, "date_key", sample_gold_dim_date, "date_key", 1.0, "critical"))

    assert all(r["passed"] for r in results)


def test_gold_fact_data_accuracy(sample_gold_fact):
    """Test Gold fact table data accuracy"""
    results = []

    results.append(check_uniqueness(sample_gold_fact, "fact_id", 1.0, "critical"))
    results.append(check_accuracy_greater_than(sample_gold_fact, "nav", 0, 1.0, "critical"))
    results.append(check_accuracy_range(sample_gold_fact, "expense_ratio_pct", 0.0, 3.0, 0.95, "warning"))

    assert all(r["passed"] for r in results)


def test_gold_overall_score_calculation(sample_gold_dim_fund, sample_gold_dim_category, sample_gold_dim_date, sample_gold_fact):
    """Test overall Gold quality score calculation"""
    results = []

    # Dim checks
    results.append(check_completeness(sample_gold_dim_fund, "fund_ticker", 1.0, "critical"))
    results.append(check_uniqueness(sample_gold_dim_fund, "fund_ticker", 1.0, "critical"))
    results.append(check_uniqueness(sample_gold_dim_category, "category_key", 1.0, "critical"))
    results.append(check_uniqueness(sample_gold_dim_date, "date_key", 1.0, "critical"))

    # Fact checks
    results.append(check_uniqueness(sample_gold_fact, "fact_id", 1.0, "critical"))
    results.append(check_accuracy_greater_than(sample_gold_fact, "nav", 0, 1.0, "critical"))

    summary = calculate_overall_score(results)
    assert summary["overall_score"] >= 0.95, f"Gold quality score {summary['overall_score']:.3f} < 0.95"
    assert summary["critical_failures"] == 0


# ============================================================================
# Test Quality Gate Blocking
# ============================================================================

def test_silver_quality_gate_blocks_bad_data():
    """Test Silver quality gate blocks data with critical failures"""
    # Create data with critical issues
    bad_data = [
        {"fund_ticker": None, "fund_name": "Fund A", "fund_type": "ETF"},  # NULL ticker
        {"fund_ticker": "B", "fund_name": "Fund B", "fund_type": "Invalid Type"},  # Invalid type
        {"fund_ticker": "C", "fund_name": "Fund C", "fund_type": "ETF"}
    ]

    results = []
    results.append(check_completeness(bad_data, "fund_ticker", 1.0, "critical"))
    results.append(check_validity(bad_data, "fund_type", ["ETF", "Mutual Fund"], 1.0, "critical"))

    summary = calculate_overall_score(results)
    assert summary["critical_failures"] > 0


def test_gold_quality_gate_blocks_bad_data():
    """Test Gold quality gate blocks data with critical failures"""
    # Create fact data with invalid NAV
    bad_fact = [
        {"fact_id": 1, "fund_ticker": "A", "nav": -10.0},  # Negative NAV
        {"fact_id": 2, "fund_ticker": "B", "nav": 0.0}  # Zero NAV
    ]

    result = check_accuracy_greater_than(bad_fact, "nav", 0, 1.0, "critical")
    assert not result["passed"]
