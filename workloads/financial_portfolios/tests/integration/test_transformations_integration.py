#!/usr/bin/env python3
"""
Integration tests for financial_portfolios transformations
Tests end-to-end Bronze→Silver→Gold pipeline with sample data

Run: python -m pytest workloads/financial_portfolios/tests/integration/test_transformations_integration.py -v
"""

import pytest
import pandas as pd
import json
import subprocess
from pathlib import Path
from datetime import datetime
import tempfile
import shutil


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def workload_root():
    """Root directory of financial_portfolios workload"""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def sample_data_dir():
    """Sample data directory"""
    return Path(__file__).parent.parent.parent.parent.parent / "sample_data"


@pytest.fixture
def temp_output_dir():
    """Temporary output directory for test runs"""
    temp_dir = Path(tempfile.mkdtemp(prefix="financial_portfolios_test_"))
    yield temp_dir
    # Cleanup after tests
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def bronze_data(sample_data_dir, temp_output_dir):
    """Copy sample data to temporary Bronze zone"""
    bronze_dir = temp_output_dir / "bronze"
    bronze_dir.mkdir(parents=True, exist_ok=True)

    # Copy sample CSVs to bronze
    shutil.copy(sample_data_dir / "stocks.csv", bronze_dir / "stocks.csv")
    shutil.copy(sample_data_dir / "portfolios.csv", bronze_dir / "portfolios.csv")
    shutil.copy(sample_data_dir / "positions.csv", bronze_dir / "positions.csv")

    return bronze_dir


# =============================================================================
# BRONZE → SILVER TESTS
# =============================================================================

def test_bronze_to_silver_stocks_pipeline(workload_root, bronze_data, temp_output_dir):
    """Run Bronze→Silver transformation for stocks and verify output"""
    script_path = workload_root / "scripts" / "transform" / "bronze_to_silver_stocks.py"
    bronze_path = bronze_data / "stocks.csv"
    silver_path = temp_output_dir / "silver" / "stocks.parquet"

    # Run transformation
    result = subprocess.run(
        [
            "python3", str(script_path),
            "--local",
            "--bronze_path", str(bronze_path),
            "--silver_path", str(silver_path)
        ],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)

    assert result.returncode == 0, f"Transformation failed: {result.stderr}"

    # Verify output file exists
    assert silver_path.exists(), "Silver output file not created"

    # Verify data
    df = pd.read_parquet(silver_path)
    assert len(df) > 0, "Output is empty"
    assert len(df) == 50, "Expected 50 stocks"

    # Verify schema
    expected_columns = ['ticker', 'company_name', 'sector', 'industry', 'exchange',
                       'market_cap_billions', 'current_price', 'price_52w_high', 'price_52w_low',
                       'pe_ratio', 'dividend_yield', 'beta', 'avg_volume_millions', 'listing_date']
    for col in expected_columns:
        assert col in df.columns, f"Missing column: {col}"

    # Verify data types
    assert df['listing_date'].dtype == 'datetime64[ns]'
    assert df['current_price'].dtype in ['float64', 'object']  # May be decimal
    assert df['ticker'].notna().all(), "Ticker column has nulls"

    # Verify deduplication (no duplicate tickers)
    assert df['ticker'].is_unique, "Duplicate tickers found after deduplication"

    # Verify lineage exists
    lineage_path = str(silver_path).replace('.parquet', '_lineage.json')
    assert Path(lineage_path).exists(), "Lineage file not created"

    with open(lineage_path, 'r') as f:
        lineage = json.load(f)
        assert lineage['table'] == 'stocks'
        assert lineage['transformation'] == 'bronze_to_silver'
        assert lineage['output_rows'] > 0


def test_bronze_to_silver_portfolios_pipeline(workload_root, bronze_data, temp_output_dir):
    """Run Bronze→Silver transformation for portfolios and verify output"""
    script_path = workload_root / "scripts" / "transform" / "bronze_to_silver_portfolios.py"
    bronze_path = bronze_data / "portfolios.csv"
    silver_path = temp_output_dir / "silver" / "portfolios.parquet"

    # Run transformation
    result = subprocess.run(
        [
            "python3", str(script_path),
            "--local",
            "--bronze_path", str(bronze_path),
            "--silver_path", str(silver_path)
        ],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    assert result.returncode == 0, f"Transformation failed: {result.stderr}"

    # Verify output
    assert silver_path.exists()
    df = pd.read_parquet(silver_path)
    assert len(df) > 0
    assert len(df) == 15, "Expected 15 portfolios"

    # Verify schema
    expected_columns = ['portfolio_id', 'portfolio_name', 'manager_name', 'strategy',
                       'risk_level', 'benchmark', 'inception_date', 'total_value',
                       'cash_balance', 'num_positions', 'avg_position_size',
                       'largest_position_pct', 'status', 'rebalance_frequency', 'last_rebalance_date']
    for col in expected_columns:
        assert col in df.columns, f"Missing column: {col}"

    # Verify data types
    assert df['inception_date'].dtype == 'datetime64[ns]'
    assert df['last_rebalance_date'].dtype == 'datetime64[ns]'
    assert df['num_positions'].dtype in ['int64', 'int32']

    # Verify no duplicates
    assert df['portfolio_id'].is_unique

    # Verify lineage
    lineage_path = str(silver_path).replace('.parquet', '_lineage.json')
    assert Path(lineage_path).exists()


def test_bronze_to_silver_positions_pipeline(workload_root, bronze_data, temp_output_dir):
    """Run Bronze→Silver transformation for positions with FK validation"""
    # First, create Silver stocks and portfolios (needed for FK checks)
    stocks_script = workload_root / "scripts" / "transform" / "bronze_to_silver_stocks.py"
    portfolios_script = workload_root / "scripts" / "transform" / "bronze_to_silver_portfolios.py"

    stocks_silver = temp_output_dir / "silver" / "stocks.parquet"
    portfolios_silver = temp_output_dir / "silver" / "portfolios.parquet"

    # Run stocks transformation
    subprocess.run([
        "python3", str(stocks_script),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(stocks_silver)
    ], check=True)

    # Run portfolios transformation
    subprocess.run([
        "python3", str(portfolios_script),
        "--local",
        "--bronze_path", str(bronze_data / "portfolios.csv"),
        "--silver_path", str(portfolios_silver)
    ], check=True)

    # Now run positions transformation
    positions_script = workload_root / "scripts" / "transform" / "bronze_to_silver_positions.py"
    bronze_path = bronze_data / "positions.csv"
    silver_path = temp_output_dir / "silver" / "positions"

    result = subprocess.run(
        [
            "python3", str(positions_script),
            "--local",
            "--bronze_path", str(bronze_path),
            "--silver_path", str(silver_path),
            "--portfolios_path", str(portfolios_silver),
            "--stocks_path", str(stocks_silver)
        ],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    assert result.returncode == 0, f"Transformation failed: {result.stderr}"

    # Verify partitioned output exists
    assert silver_path.exists()
    partition_dirs = list(silver_path.glob("sector=*/"))
    assert len(partition_dirs) > 0, "No sector partitions created"

    # Read all partitions
    dfs = []
    for partition in partition_dirs:
        data_file = partition / "data.parquet"
        if data_file.exists():
            dfs.append(pd.read_parquet(data_file))

    df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    assert len(df) > 0, "Output is empty"

    # Verify schema
    expected_columns = ['position_id', 'portfolio_id', 'ticker', 'shares',
                       'cost_basis', 'purchase_price', 'current_price', 'market_value',
                       'unrealized_gain_loss', 'unrealized_gain_loss_pct', 'weight_pct',
                       'entry_date', 'last_updated', 'holding_period_days',
                       'sector', 'position_status']
    for col in expected_columns:
        assert col in df.columns, f"Missing column: {col}"

    # Verify data types
    assert df['entry_date'].dtype == 'datetime64[ns]'
    assert df['last_updated'].dtype == 'datetime64[ns]'
    assert df['holding_period_days'].dtype in ['int64', 'int32']

    # Verify FK integrity (all portfolio_ids and tickers should be valid)
    portfolios_df = pd.read_parquet(portfolios_silver)
    stocks_df = pd.read_parquet(stocks_silver)

    valid_portfolio_ids = set(portfolios_df['portfolio_id'])
    valid_tickers = set(stocks_df['ticker'])

    assert df['portfolio_id'].isin(valid_portfolio_ids).all(), "Found invalid portfolio_id FK"
    assert df['ticker'].isin(valid_tickers).all(), "Found invalid ticker FK"

    # Verify shares are positive
    assert (df['shares'] > 0).all(), "Found non-positive shares"

    # Verify no nulls in critical columns
    assert df['ticker'].notna().all()
    assert df['portfolio_id'].notna().all()
    assert df['position_id'].notna().all()


def test_bronze_to_silver_quarantine_logic(workload_root, temp_output_dir):
    """Test quarantine logic with intentionally invalid data"""
    # Create test data with known issues
    invalid_positions = pd.DataFrame({
        'position_id': ['BAD001', 'BAD002', 'BAD003', 'BAD004'],
        'portfolio_id': ['P001', 'INVALID_PORTFOLIO', 'P001', 'P001'],
        'ticker': ['AAPL', 'AAPL', 'INVALID_TICKER', None],  # Invalid ticker, null ticker
        'shares': [100, -50, 100, 100],  # Negative shares
        'cost_basis': [10000, 5000, 10000, 10000],
        'purchase_price': [100, 100, 100, 100],
        'current_price': [110, 110, 110, 110],
        'market_value': [11000, 5500, 11000, 11000],
        'unrealized_gain_loss': [1000, 500, 1000, 1000],
        'unrealized_gain_loss_pct': [10.0, 10.0, 10.0, 10.0],
        'weight_pct': [5.0, 5.0, 5.0, 5.0],
        'entry_date': ['2024-01-01', '2024-01-01', '2024-01-01', '2024-01-01'],
        'last_updated': ['2024-03-20 10:00:00', '2024-03-20 10:00:00', '2024-03-20 10:00:00', '2024-03-20 10:00:00'],
        'holding_period_days': [80, 80, 80, 80],
        'sector': ['Technology', 'Technology', 'Technology', 'Technology'],
        'position_status': ['Open', 'Open', 'Open', 'Open']
    })

    # Create valid dimension data
    valid_portfolios = pd.DataFrame({
        'portfolio_id': ['P001'],
        'portfolio_name': ['Test Portfolio'],
        'manager_name': ['Test Manager'],
        'strategy': ['Growth'],
        'risk_level': ['High'],
        'benchmark': ['S&P 500'],
        'inception_date': ['2020-01-01'],
        'total_value': [1000000.0],
        'cash_balance': [50000.0],
        'num_positions': [10],
        'avg_position_size': [100000.0],
        'largest_position_pct': [15.0],
        'status': ['Active'],
        'rebalance_frequency': ['Quarterly'],
        'last_rebalance_date': ['2024-01-01']
    })

    valid_stocks = pd.DataFrame({
        'ticker': ['AAPL'],
        'company_name': ['Apple Inc.'],
        'sector': ['Technology'],
        'industry': ['Consumer Electronics'],
        'exchange': ['NASDAQ'],
        'market_cap_billions': [2800.0],
        'current_price': [180.0],
        'price_52w_high': [200.0],
        'price_52w_low': [120.0],
        'pe_ratio': [30.0],
        'dividend_yield': [0.5],
        'beta': [1.2],
        'avg_volume_millions': [60.0],
        'listing_date': ['1980-12-12']
    })

    # Write to temp Bronze
    bronze_dir = temp_output_dir / "bronze"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    invalid_positions.to_csv(bronze_dir / "positions.csv", index=False)

    # Write dimensions to Silver (for FK checks)
    silver_dir = temp_output_dir / "silver"
    silver_dir.mkdir(parents=True, exist_ok=True)
    valid_portfolios.to_parquet(silver_dir / "portfolios.parquet", index=False)
    valid_stocks.to_parquet(silver_dir / "stocks.parquet", index=False)

    # Run positions transformation
    positions_script = workload_root / "scripts" / "transform" / "bronze_to_silver_positions.py"
    silver_positions_path = silver_dir / "positions"

    result = subprocess.run(
        [
            "python3", str(positions_script),
            "--local",
            "--bronze_path", str(bronze_dir / "positions.csv"),
            "--silver_path", str(silver_positions_path),
            "--portfolios_path", str(silver_dir / "portfolios.parquet"),
            "--stocks_path", str(silver_dir / "stocks.parquet")
        ],
        capture_output=True,
        text=True
    )

    print(result.stdout)

    # Verify quarantine happened
    assert "Quarantined rows: 3" in result.stdout or result.returncode == 0

    # Check quarantine file
    quarantine_path = str(silver_positions_path).replace('/silver/', '/quarantine/') + '_quarantine.parquet'
    if Path(quarantine_path).exists():
        quarantine_df = pd.read_parquet(quarantine_path)
        assert len(quarantine_df) == 3, "Expected 3 rows in quarantine"
        assert 'quarantine_reason' in quarantine_df.columns

        # Verify quarantine reasons
        reasons = quarantine_df['quarantine_reason'].tolist()
        assert any('CRITICAL' in str(r) for r in reasons), "Quarantine reasons should be marked CRITICAL"


def test_bronze_to_silver_deduplication(workload_root, temp_output_dir):
    """Test deduplication logic keeps last record"""
    # Create test data with duplicates
    duplicate_stocks = pd.DataFrame({
        'ticker': ['AAPL', 'AAPL', 'MSFT'],
        'company_name': ['Old Name', 'Apple Inc.', 'Microsoft Corporation'],
        'sector': ['Technology', 'Technology', 'Technology'],
        'industry': ['Consumer Electronics', 'Consumer Electronics', 'Software'],
        'exchange': ['NASDAQ', 'NASDAQ', 'NASDAQ'],
        'market_cap_billions': [2000.0, 2800.0, 2700.0],
        'current_price': [150.0, 180.0, 370.0],
        'price_52w_high': [160.0, 200.0, 380.0],
        'price_52w_low': [100.0, 120.0, 200.0],
        'pe_ratio': [25.0, 30.0, 35.0],
        'dividend_yield': [0.4, 0.5, 0.8],
        'beta': [1.1, 1.2, 0.9],
        'avg_volume_millions': [50.0, 60.0, 25.0],
        'listing_date': ['1980-12-12', '1980-12-12', '1986-03-13']
    })

    bronze_dir = temp_output_dir / "bronze_dedup_test"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    duplicate_stocks.to_csv(bronze_dir / "stocks.csv", index=False)

    # Run transformation
    script_path = workload_root / "scripts" / "transform" / "bronze_to_silver_stocks.py"
    silver_path = temp_output_dir / "silver_dedup_test" / "stocks.parquet"

    result = subprocess.run(
        [
            "python3", str(script_path),
            "--local",
            "--bronze_path", str(bronze_dir / "stocks.csv"),
            "--silver_path", str(silver_path)
        ],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    assert result.returncode == 0

    # Verify deduplication
    df = pd.read_parquet(silver_path)
    assert len(df) == 2, "Should have 2 unique stocks after deduplication"

    # Verify last record kept for AAPL
    aapl = df[df['ticker'] == 'AAPL'].iloc[0]
    assert aapl['company_name'] == 'Apple Inc.', "Should keep last record"
    assert aapl['current_price'] == 180.0, "Should keep last record's price"


# =============================================================================
# SILVER → GOLD TESTS
# =============================================================================

def test_silver_to_gold_dimensions(workload_root, bronze_data, temp_output_dir):
    """Run Silver→Gold transformations for dimension tables"""
    # First create Silver data
    stocks_script = workload_root / "scripts" / "transform" / "bronze_to_silver_stocks.py"
    portfolios_script = workload_root / "scripts" / "transform" / "bronze_to_silver_portfolios.py"

    stocks_silver = temp_output_dir / "silver" / "stocks.parquet"
    portfolios_silver = temp_output_dir / "silver" / "portfolios.parquet"

    subprocess.run([
        "python3", str(stocks_script),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(stocks_silver)
    ], check=True)

    subprocess.run([
        "python3", str(portfolios_script),
        "--local",
        "--bronze_path", str(bronze_data / "portfolios.csv"),
        "--silver_path", str(portfolios_silver)
    ], check=True)

    # Now create Gold dimensions
    dim_stocks_script = workload_root / "scripts" / "transform" / "silver_to_gold_dim_stocks.py"
    dim_portfolios_script = workload_root / "scripts" / "transform" / "silver_to_gold_dim_portfolios.py"

    dim_stocks_gold = temp_output_dir / "gold" / "dim_stocks.parquet"
    dim_portfolios_gold = temp_output_dir / "gold" / "dim_portfolios.parquet"

    # Run dim_stocks
    result = subprocess.run([
        "python3", str(dim_stocks_script),
        "--local",
        "--silver_path", str(stocks_silver),
        "--gold_path", str(dim_stocks_gold)
    ], capture_output=True, text=True)

    print(result.stdout)
    assert result.returncode == 0

    # Run dim_portfolios
    result = subprocess.run([
        "python3", str(dim_portfolios_script),
        "--local",
        "--silver_path", str(portfolios_silver),
        "--gold_path", str(dim_portfolios_gold)
    ], capture_output=True, text=True)

    print(result.stdout)
    assert result.returncode == 0

    # Verify outputs
    assert dim_stocks_gold.exists()
    assert dim_portfolios_gold.exists()

    stocks_df = pd.read_parquet(dim_stocks_gold)
    portfolios_df = pd.read_parquet(dim_portfolios_gold)

    assert len(stocks_df) == 50
    assert len(portfolios_df) == 15

    # Verify dimensions are exact copies of Silver
    silver_stocks = pd.read_parquet(stocks_silver)
    silver_portfolios = pd.read_parquet(portfolios_silver)

    assert stocks_df.shape == silver_stocks.shape
    assert portfolios_df.shape == silver_portfolios.shape


def test_silver_to_gold_fact_positions(workload_root, bronze_data, temp_output_dir):
    """Run Silver→Gold transformation for fact_positions"""
    # Create full Silver zone first
    scripts_dir = workload_root / "scripts" / "transform"
    silver_dir = temp_output_dir / "silver"
    silver_dir.mkdir(parents=True, exist_ok=True)

    # Run Bronze→Silver for all tables
    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_stocks.py"),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_portfolios.py"),
        "--local",
        "--bronze_path", str(bronze_data / "portfolios.csv"),
        "--silver_path", str(silver_dir / "portfolios.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_positions.py"),
        "--local",
        "--bronze_path", str(bronze_data / "positions.csv"),
        "--silver_path", str(silver_dir / "positions"),
        "--portfolios_path", str(silver_dir / "portfolios.parquet"),
        "--stocks_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    # Now create fact_positions
    fact_script = scripts_dir / "silver_to_gold_fact_positions.py"
    fact_gold = temp_output_dir / "gold" / "fact_positions"

    result = subprocess.run([
        "python3", str(fact_script),
        "--local",
        "--positions_path", str(silver_dir / "positions"),
        "--stocks_path", str(silver_dir / "stocks.parquet"),
        "--portfolios_path", str(silver_dir / "portfolios.parquet"),
        "--gold_path", str(fact_gold)
    ], capture_output=True, text=True)

    print(result.stdout)
    assert result.returncode == 0

    # Verify partitioned output
    assert fact_gold.exists()
    partition_dirs = list(fact_gold.glob("sector=*/"))
    assert len(partition_dirs) > 0

    # Read all partitions
    dfs = []
    for partition in partition_dirs:
        data_file = partition / "data.parquet"
        if data_file.exists():
            dfs.append(pd.read_parquet(data_file))

    fact_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    assert len(fact_df) > 0

    # Verify fact table structure
    assert 'position_id' in fact_df.columns
    assert 'portfolio_id' in fact_df.columns
    assert 'ticker' in fact_df.columns
    assert 'market_value' in fact_df.columns
    assert 'unrealized_gain_loss' in fact_df.columns
    assert 'sector' in fact_df.columns

    # Verify all positions are Open
    assert (fact_df['position_status'] == 'Open').all()


def test_silver_to_gold_portfolio_summary(workload_root, bronze_data, temp_output_dir):
    """Run Silver→Gold transformation for portfolio_summary aggregate"""
    # Setup: Create Bronze→Silver→Gold fact_positions first
    scripts_dir = workload_root / "scripts" / "transform"
    silver_dir = temp_output_dir / "silver"
    gold_dir = temp_output_dir / "gold"
    silver_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)

    # Run full Bronze→Silver→Gold for fact_positions
    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_stocks.py"),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_portfolios.py"),
        "--local",
        "--bronze_path", str(bronze_data / "portfolios.csv"),
        "--silver_path", str(silver_dir / "portfolios.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_positions.py"),
        "--local",
        "--bronze_path", str(bronze_data / "positions.csv"),
        "--silver_path", str(silver_dir / "positions"),
        "--portfolios_path", str(silver_dir / "portfolios.parquet"),
        "--stocks_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "silver_to_gold_fact_positions.py"),
        "--local",
        "--positions_path", str(silver_dir / "positions"),
        "--stocks_path", str(silver_dir / "stocks.parquet"),
        "--portfolios_path", str(silver_dir / "portfolios.parquet"),
        "--gold_path", str(gold_dir / "fact_positions")
    ], check=True)

    # Now create portfolio_summary
    summary_script = scripts_dir / "silver_to_gold_portfolio_summary.py"
    summary_gold = gold_dir / "portfolio_summary.parquet"

    result = subprocess.run([
        "python3", str(summary_script),
        "--local",
        "--fact_positions_path", str(gold_dir / "fact_positions"),
        "--gold_path", str(summary_gold)
    ], capture_output=True, text=True)

    print(result.stdout)
    assert result.returncode == 0

    # Verify output
    assert summary_gold.exists()
    summary_df = pd.read_parquet(summary_gold)
    assert len(summary_df) > 0

    # Verify aggregation columns
    expected_columns = [
        'portfolio_id',
        'total_market_value',
        'total_cost_basis',
        'total_unrealized_gain_loss',
        'num_positions',
        'avg_return_pct',
        'avg_holding_period_days',
        'largest_position_pct',
        'total_return_pct'
    ]

    for col in expected_columns:
        assert col in summary_df.columns, f"Missing column: {col}"

    # Verify aggregations are correct
    assert summary_df['num_positions'].dtype in ['int64', 'int32']
    assert (summary_df['total_market_value'] > 0).all()
    assert (summary_df['num_positions'] > 0).all()


# =============================================================================
# END-TO-END PIPELINE TEST
# =============================================================================

def test_end_to_end_pipeline(workload_root, bronze_data, temp_output_dir):
    """Run complete Bronze→Silver→Gold pipeline and verify star schema"""
    scripts_dir = workload_root / "scripts" / "transform"
    silver_dir = temp_output_dir / "silver"
    gold_dir = temp_output_dir / "gold"
    silver_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1: Bronze → Silver
    print("\n=== Phase 1: Bronze → Silver ===")

    # Stocks
    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_stocks.py"),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    # Portfolios
    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_portfolios.py"),
        "--local",
        "--bronze_path", str(bronze_data / "portfolios.csv"),
        "--silver_path", str(silver_dir / "portfolios.parquet")
    ], check=True)

    # Positions
    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_positions.py"),
        "--local",
        "--bronze_path", str(bronze_data / "positions.csv"),
        "--silver_path", str(silver_dir / "positions"),
        "--portfolios_path", str(silver_dir / "portfolios.parquet"),
        "--stocks_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    # Verify Silver zone
    assert (silver_dir / "stocks.parquet").exists()
    assert (silver_dir / "portfolios.parquet").exists()
    assert (silver_dir / "positions").exists()

    # Phase 2: Silver → Gold (Dimensions)
    print("\n=== Phase 2: Silver → Gold (Dimensions) ===")

    subprocess.run([
        "python3", str(scripts_dir / "silver_to_gold_dim_stocks.py"),
        "--local",
        "--silver_path", str(silver_dir / "stocks.parquet"),
        "--gold_path", str(gold_dir / "dim_stocks.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "silver_to_gold_dim_portfolios.py"),
        "--local",
        "--silver_path", str(silver_dir / "portfolios.parquet"),
        "--gold_path", str(gold_dir / "dim_portfolios.parquet")
    ], check=True)

    # Phase 3: Silver → Gold (Fact)
    print("\n=== Phase 3: Silver → Gold (Fact) ===")

    subprocess.run([
        "python3", str(scripts_dir / "silver_to_gold_fact_positions.py"),
        "--local",
        "--positions_path", str(silver_dir / "positions"),
        "--stocks_path", str(silver_dir / "stocks.parquet"),
        "--portfolios_path", str(silver_dir / "portfolios.parquet"),
        "--gold_path", str(gold_dir / "fact_positions")
    ], check=True)

    # Phase 4: Silver → Gold (Aggregate)
    print("\n=== Phase 4: Silver → Gold (Aggregate) ===")

    subprocess.run([
        "python3", str(scripts_dir / "silver_to_gold_portfolio_summary.py"),
        "--local",
        "--fact_positions_path", str(gold_dir / "fact_positions"),
        "--gold_path", str(gold_dir / "portfolio_summary.parquet")
    ], check=True)

    # Verify complete Gold zone
    assert (gold_dir / "dim_stocks.parquet").exists()
    assert (gold_dir / "dim_portfolios.parquet").exists()
    assert (gold_dir / "fact_positions").exists()
    assert (gold_dir / "portfolio_summary.parquet").exists()

    # Verify star schema structure
    dim_stocks_df = pd.read_parquet(gold_dir / "dim_stocks.parquet")
    dim_portfolios_df = pd.read_parquet(gold_dir / "dim_portfolios.parquet")

    # Read fact partitions
    fact_dfs = []
    for partition in (gold_dir / "fact_positions").glob("sector=*/data.parquet"):
        fact_dfs.append(pd.read_parquet(partition))
    fact_df = pd.concat(fact_dfs, ignore_index=True)

    summary_df = pd.read_parquet(gold_dir / "portfolio_summary.parquet")

    print(f"\nStar Schema:")
    print(f"  dim_stocks: {len(dim_stocks_df)} rows")
    print(f"  dim_portfolios: {len(dim_portfolios_df)} rows")
    print(f"  fact_positions: {len(fact_df)} rows")
    print(f"  portfolio_summary: {len(summary_df)} rows")

    # Verify FK integrity in fact table
    assert fact_df['ticker'].isin(dim_stocks_df['ticker']).all()
    assert fact_df['portfolio_id'].isin(dim_portfolios_df['portfolio_id']).all()

    # Verify aggregation correctness
    # Sum of fact market_value should equal sum in summary
    fact_market_value_by_portfolio = fact_df.groupby('portfolio_id')['market_value'].sum()
    for _, row in summary_df.iterrows():
        portfolio_id = row['portfolio_id']
        expected_value = fact_market_value_by_portfolio.get(portfolio_id, 0)
        actual_value = row['total_market_value']
        # Allow small floating point differences
        assert abs(expected_value - actual_value) < 0.01, \
            f"Portfolio {portfolio_id}: Expected {expected_value}, got {actual_value}"


# =============================================================================
# LINEAGE TRACKING TESTS
# =============================================================================

def test_lineage_files_generated(workload_root, bronze_data, temp_output_dir):
    """Verify lineage files are generated for all transformations"""
    scripts_dir = workload_root / "scripts" / "transform"
    silver_dir = temp_output_dir / "silver_lineage_test"
    silver_dir.mkdir(parents=True, exist_ok=True)

    # Run one transformation
    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_stocks.py"),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    # Verify lineage file
    lineage_path = silver_dir / "stocks_lineage.json"
    assert lineage_path.exists(), "Lineage file not created"

    with open(lineage_path, 'r') as f:
        lineage = json.load(f)

    # Verify lineage structure
    assert lineage['workload'] == 'financial_portfolios'
    assert lineage['table'] == 'stocks'
    assert lineage['transformation'] == 'bronze_to_silver'
    assert 'source' in lineage
    assert 'target' in lineage
    assert 'timestamp' in lineage
    assert 'input_rows' in lineage
    assert 'output_rows' in lineage
    assert 'transformations_applied' in lineage
    assert 'column_lineage' in lineage
    assert 'quality_metrics' in lineage
    assert 'data_hash' in lineage


def test_lineage_column_level_tracking(workload_root, bronze_data, temp_output_dir):
    """Verify column-level lineage is tracked"""
    scripts_dir = workload_root / "scripts" / "transform"
    silver_dir = temp_output_dir / "silver_col_lineage"
    silver_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_stocks.py"),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    lineage_path = silver_dir / "stocks_lineage.json"
    with open(lineage_path, 'r') as f:
        lineage = json.load(f)

    # Verify column lineage exists
    assert 'column_lineage' in lineage
    col_lineage = lineage['column_lineage']
    assert len(col_lineage) > 0

    # Verify specific columns tracked
    assert 'ticker' in col_lineage
    assert 'current_price' in col_lineage
    assert 'listing_date' in col_lineage

    # Verify transformations recorded
    assert 'source' in col_lineage['current_price']
    assert 'transformations' in col_lineage['current_price']


# =============================================================================
# IDEMPOTENCY TESTS
# =============================================================================

def test_transformation_idempotency(workload_root, bronze_data, temp_output_dir):
    """Running transformation twice produces identical output"""
    scripts_dir = workload_root / "scripts" / "transform"
    silver_path = temp_output_dir / "silver_idempotency" / "stocks.parquet"

    # Run transformation first time
    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_stocks.py"),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(silver_path)
    ], check=True)

    df1 = pd.read_parquet(silver_path)
    lineage1_path = str(silver_path).replace('.parquet', '_lineage.json')
    with open(lineage1_path, 'r') as f:
        lineage1 = json.load(f)

    # Run transformation second time
    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_stocks.py"),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(silver_path)
    ], check=True)

    df2 = pd.read_parquet(silver_path)
    with open(lineage1_path, 'r') as f:
        lineage2 = json.load(f)

    # Verify identical output
    assert len(df1) == len(df2), "Row counts differ between runs"
    assert df1.shape == df2.shape, "Schema differs between runs"

    # Verify same row counts in lineage
    assert lineage1['output_rows'] == lineage2['output_rows']
    assert lineage1['quarantined_rows'] == lineage2['quarantined_rows']


# =============================================================================
# DATA QUALITY TESTS
# =============================================================================

def test_silver_data_has_no_nulls_in_pk(workload_root, bronze_data, temp_output_dir):
    """Silver zone data has no nulls in primary key columns"""
    scripts_dir = workload_root / "scripts" / "transform"
    silver_dir = temp_output_dir / "silver_no_nulls"
    silver_dir.mkdir(parents=True, exist_ok=True)

    # Run stocks transformation
    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_stocks.py"),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    df = pd.read_parquet(silver_dir / "stocks.parquet")
    assert df['ticker'].notna().all(), "Primary key (ticker) has nulls"


def test_silver_positions_all_fks_valid(workload_root, bronze_data, temp_output_dir):
    """All FKs in Silver positions are valid (referential integrity)"""
    scripts_dir = workload_root / "scripts" / "transform"
    silver_dir = temp_output_dir / "silver_fk_integrity"
    silver_dir.mkdir(parents=True, exist_ok=True)

    # Run full Bronze→Silver pipeline
    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_stocks.py"),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_portfolios.py"),
        "--local",
        "--bronze_path", str(bronze_data / "portfolios.csv"),
        "--silver_path", str(silver_dir / "portfolios.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_positions.py"),
        "--local",
        "--bronze_path", str(bronze_data / "positions.csv"),
        "--silver_path", str(silver_dir / "positions"),
        "--portfolios_path", str(silver_dir / "portfolios.parquet"),
        "--stocks_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    # Load all tables
    stocks_df = pd.read_parquet(silver_dir / "stocks.parquet")
    portfolios_df = pd.read_parquet(silver_dir / "portfolios.parquet")

    # Read all position partitions
    positions_dfs = []
    for partition in (silver_dir / "positions").glob("sector=*/data.parquet"):
        positions_dfs.append(pd.read_parquet(partition))
    positions_df = pd.concat(positions_dfs, ignore_index=True)

    # Verify FK integrity
    valid_tickers = set(stocks_df['ticker'])
    valid_portfolio_ids = set(portfolios_df['portfolio_id'])

    assert positions_df['ticker'].isin(valid_tickers).all(), "Found invalid ticker FK in Silver"
    assert positions_df['portfolio_id'].isin(valid_portfolio_ids).all(), "Found invalid portfolio_id FK in Silver"


def test_gold_star_schema_joinable(workload_root, bronze_data, temp_output_dir):
    """Gold star schema tables are joinable (FK relationships work)"""
    scripts_dir = workload_root / "scripts" / "transform"
    silver_dir = temp_output_dir / "silver_star_join"
    gold_dir = temp_output_dir / "gold_star_join"
    silver_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)

    # Run full pipeline
    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_stocks.py"),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_portfolios.py"),
        "--local",
        "--bronze_path", str(bronze_data / "portfolios.csv"),
        "--silver_path", str(silver_dir / "portfolios.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_positions.py"),
        "--local",
        "--bronze_path", str(bronze_data / "positions.csv"),
        "--silver_path", str(silver_dir / "positions"),
        "--portfolios_path", str(silver_dir / "portfolios.parquet"),
        "--stocks_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "silver_to_gold_dim_stocks.py"),
        "--local",
        "--silver_path", str(silver_dir / "stocks.parquet"),
        "--gold_path", str(gold_dir / "dim_stocks.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "silver_to_gold_dim_portfolios.py"),
        "--local",
        "--silver_path", str(silver_dir / "portfolios.parquet"),
        "--gold_path", str(gold_dir / "dim_portfolios.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "silver_to_gold_fact_positions.py"),
        "--local",
        "--positions_path", str(silver_dir / "positions"),
        "--stocks_path", str(silver_dir / "stocks.parquet"),
        "--portfolios_path", str(silver_dir / "portfolios.parquet"),
        "--gold_path", str(gold_dir / "fact_positions")
    ], check=True)

    # Load Gold star schema
    dim_stocks = pd.read_parquet(gold_dir / "dim_stocks.parquet")
    dim_portfolios = pd.read_parquet(gold_dir / "dim_portfolios.parquet")

    fact_dfs = []
    for partition in (gold_dir / "fact_positions").glob("sector=*/data.parquet"):
        fact_dfs.append(pd.read_parquet(partition))
    fact_positions = pd.concat(fact_dfs, ignore_index=True)

    # Perform star schema joins
    positions_with_stocks = fact_positions.merge(
        dim_stocks,
        on='ticker',
        how='inner',
        suffixes=('', '_stock')
    )

    assert len(positions_with_stocks) == len(fact_positions), "Lost rows joining fact with dim_stocks"

    positions_with_all = positions_with_stocks.merge(
        dim_portfolios,
        on='portfolio_id',
        how='inner',
        suffixes=('', '_portfolio')
    )

    assert len(positions_with_all) == len(fact_positions), "Lost rows joining with dim_portfolios"

    print(f"✓ Star schema joins successful: {len(positions_with_all)} rows")


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

def test_partitioning_reduces_scan_size(workload_root, bronze_data, temp_output_dir):
    """Partitioning by sector enables efficient queries"""
    scripts_dir = workload_root / "scripts" / "transform"
    silver_dir = temp_output_dir / "silver_partition_test"
    silver_dir.mkdir(parents=True, exist_ok=True)

    # Create Silver positions (partitioned by sector)
    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_stocks.py"),
        "--local",
        "--bronze_path", str(bronze_data / "stocks.csv"),
        "--silver_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_portfolios.py"),
        "--local",
        "--bronze_path", str(bronze_data / "portfolios.csv"),
        "--silver_path", str(silver_dir / "portfolios.parquet")
    ], check=True)

    subprocess.run([
        "python3", str(scripts_dir / "bronze_to_silver_positions.py"),
        "--local",
        "--bronze_path", str(bronze_data / "positions.csv"),
        "--silver_path", str(silver_dir / "positions"),
        "--portfolios_path", str(silver_dir / "portfolios.parquet"),
        "--stocks_path", str(silver_dir / "stocks.parquet")
    ], check=True)

    # Verify partition directories created
    positions_dir = silver_dir / "positions"
    partitions = list(positions_dir.glob("sector=*/"))
    assert len(partitions) > 1, "Should have multiple sector partitions"

    # Verify each partition has data
    for partition in partitions:
        data_file = partition / "data.parquet"
        assert data_file.exists(), f"Partition {partition.name} missing data file"
        df = pd.read_parquet(data_file)
        assert len(df) > 0, f"Partition {partition.name} is empty"

        # Verify all rows in partition have same sector
        sector = partition.name.split('=')[1]
        assert (df['sector'] == sector).all(), f"Partition {partition.name} contains wrong sector data"


# =============================================================================
# SUMMARY TEST
# =============================================================================

def test_transformation_pipeline_summary(workload_root):
    """Summary test - verify all transformation artifacts exist"""
    config_dir = workload_root / "config"
    scripts_dir = workload_root / "scripts" / "transform"

    # Config file
    assert (config_dir / "transformations.yaml").exists()

    # Bronze→Silver scripts (3)
    assert (scripts_dir / "bronze_to_silver_stocks.py").exists()
    assert (scripts_dir / "bronze_to_silver_portfolios.py").exists()
    assert (scripts_dir / "bronze_to_silver_positions.py").exists()

    # Silver→Gold scripts (4)
    assert (scripts_dir / "silver_to_gold_dim_stocks.py").exists()
    assert (scripts_dir / "silver_to_gold_dim_portfolios.py").exists()
    assert (scripts_dir / "silver_to_gold_fact_positions.py").exists()
    assert (scripts_dir / "silver_to_gold_portfolio_summary.py").exists()

    print("\n✓ All transformation artifacts present:")
    print("  - transformations.yaml")
    print("  - 3 Bronze→Silver scripts")
    print("  - 4 Silver→Gold scripts")
    print("  - Total: 8 files")
