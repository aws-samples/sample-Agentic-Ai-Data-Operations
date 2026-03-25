"""
Integration tests for financial_portfolios quality checks
Tests end-to-end quality check execution with real data
"""

import pytest
import pandas as pd
import sys
from pathlib import Path
import json
import tempfile
import shutil

# Add scripts to path
scripts_path = Path(__file__).parent.parent.parent / "scripts" / "quality"
sys.path.insert(0, str(scripts_path))

from run_quality_checks import QualityChecker


@pytest.fixture
def quality_rules_path():
    """Path to quality rules YAML"""
    return Path(__file__).parent.parent.parent / "config" / "quality_rules.yaml"


@pytest.fixture
def sample_data_dir(tmp_path):
    """Create sample data directory with test data"""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir()

    # Create stocks data (valid)
    stocks_df = pd.DataFrame({
        'ticker': ['AAPL', 'GOOGL', 'MSFT'],
        'company_name': ['Apple Inc.', 'Alphabet Inc.', 'Microsoft Corp.'],
        'sector': ['Technology', 'Technology', 'Technology'],
        'industry': ['Consumer Electronics', 'Internet Services', 'Software'],
        'exchange': ['NASDAQ', 'NASDAQ', 'NASDAQ'],
        'current_price': [150.0, 2800.0, 350.0],
        'market_cap_billions': [2400.0, 1800.0, 2600.0],
        'pe_ratio': [28.5, 22.3, 32.1],
        'dividend_yield_pct': [0.5, 0.0, 0.8],
        'avg_volume_millions': [80.0, 25.0, 30.0],
        'week_52_high': [180.0, 3000.0, 380.0],
        'week_52_low': [120.0, 2200.0, 280.0],
        'listing_date': ['1980-12-12', '2004-08-19', '1986-03-13']
    })
    stocks_df.to_parquet(data_dir / "stocks.parquet", index=False)

    # Create portfolios data (valid)
    portfolios_df = pd.DataFrame({
        'portfolio_id': ['P001', 'P002'],
        'portfolio_name': ['Growth Portfolio', 'Value Portfolio'],
        'manager_name': ['John Smith', 'Jane Doe'],
        'strategy': ['Growth', 'Value'],
        'risk_level': ['High', 'Medium'],
        'total_value': [1000000.0, 750000.0],
        'cash_balance': [50000.0, 25000.0],
        'num_positions': [3, 2],
        'avg_position_size': [333333.0, 375000.0],
        'inception_date': ['2020-01-01', '2019-06-15'],
        'ytd_return_pct': [15.5, 12.3]
    })
    portfolios_df.to_parquet(data_dir / "portfolios.parquet", index=False)

    # Create positions data (valid)
    positions_df = pd.DataFrame({
        'position_id': ['POS001', 'POS002', 'POS003', 'POS004', 'POS005'],
        'portfolio_id': ['P001', 'P001', 'P001', 'P002', 'P002'],
        'ticker': ['AAPL', 'GOOGL', 'MSFT', 'AAPL', 'MSFT'],
        'shares': [2000.0, 100.0, 1000.0, 1500.0, 800.0],
        'cost_basis': [250000.0, 250000.0, 300000.0, 200000.0, 250000.0],
        'purchase_price': [125.0, 2500.0, 300.0, 133.33, 312.5],
        'current_price': [150.0, 2800.0, 350.0, 150.0, 350.0],
        'market_value': [300000.0, 280000.0, 350000.0, 225000.0, 280000.0],
        'unrealized_gain_loss': [50000.0, 30000.0, 50000.0, 25000.0, 30000.0],
        'unrealized_gain_loss_pct': [20.0, 12.0, 16.67, 12.5, 12.0],
        'entry_date': ['2021-01-15', '2021-02-20', '2021-03-10', '2020-08-01', '2020-09-15'],
        'holding_period_days': [1200, 1150, 1100, 1600, 1550],
        'weight_pct': [30.0, 28.0, 35.0, 30.0, 37.3]
    })
    positions_df.to_parquet(data_dir / "positions.parquet", index=False)

    return data_dir


@pytest.fixture
def invalid_data_dir(tmp_path):
    """Create sample data with quality issues"""
    data_dir = tmp_path / "invalid_data"
    data_dir.mkdir()

    # Stocks with issues: nulls, negative price, duplicate PK
    stocks_df = pd.DataFrame({
        'ticker': ['AAPL', 'GOOGL', 'AAPL', 'TSLA'],  # Duplicate AAPL
        'company_name': ['Apple Inc.', None, 'Apple Inc.', 'Tesla Inc.'],  # Null
        'sector': ['Technology', 'Technology', 'Technology', 'Automotive'],
        'industry': ['Consumer Electronics', 'Internet Services', 'Consumer Electronics', 'Auto Manufacturers'],
        'exchange': ['NASDAQ', 'NASDAQ', 'NASDAQ', 'NASDAQ'],
        'current_price': [150.0, 2800.0, 150.0, -100.0],  # Negative price
        'market_cap_billions': [2400.0, 1800.0, 2400.0, 800.0],
        'pe_ratio': [28.5, 22.3, 28.5, 50.0],
        'dividend_yield_pct': [0.5, 0.0, 0.5, 0.0],
        'avg_volume_millions': [80.0, 25.0, 80.0, 50.0],
        'week_52_high': [180.0, 3000.0, 180.0, 300.0],
        'week_52_low': [120.0, 2200.0, 120.0, 100.0],
        'listing_date': ['1980-12-12', '2004-08-19', '1980-12-12', '2010-06-29']
    })
    stocks_df.to_parquet(data_dir / "stocks.parquet", index=False)

    # Portfolios (valid)
    portfolios_df = pd.DataFrame({
        'portfolio_id': ['P001'],
        'portfolio_name': ['Growth Portfolio'],
        'manager_name': ['John Smith'],
        'strategy': ['Growth'],
        'risk_level': ['High'],
        'total_value': [1000000.0],
        'cash_balance': [50000.0],
        'num_positions': [2],
        'avg_position_size': [500000.0],
        'inception_date': ['2020-01-01'],
        'ytd_return_pct': [15.5]
    })
    portfolios_df.to_parquet(data_dir / "portfolios.parquet", index=False)

    # Positions with issues: invalid FK, negative shares, null ticker
    positions_df = pd.DataFrame({
        'position_id': ['POS001', 'POS002', 'POS003'],
        'portfolio_id': ['P001', 'P999', 'P001'],  # P999 invalid FK
        'ticker': ['AAPL', 'GOOGL', None],  # Null ticker
        'shares': [2000.0, 100.0, -500.0],  # Negative shares
        'cost_basis': [250000.0, 250000.0, 100000.0],
        'purchase_price': [125.0, 2500.0, 200.0],
        'current_price': [150.0, 2800.0, 180.0],
        'market_value': [300000.0, 280000.0, 90000.0],
        'unrealized_gain_loss': [50000.0, 30000.0, -10000.0],
        'unrealized_gain_loss_pct': [20.0, 12.0, -10.0],
        'entry_date': ['2021-01-15', '2021-02-20', '2021-03-10'],
        'holding_period_days': [1200, 1150, 1100],
        'weight_pct': [60.0, 56.0, -18.0]
    })
    positions_df.to_parquet(data_dir / "positions.parquet", index=False)

    return data_dir


class TestQualityCheckerInit:
    """Test QualityChecker initialization"""

    def test_init_with_valid_paths(self, quality_rules_path, sample_data_dir):
        """QualityChecker initializes with valid paths"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(sample_data_dir),
            'silver'
        )
        assert checker.rules is not None
        assert checker.zone == 'silver'
        assert checker.data_path == sample_data_dir


class TestQualityChecksWithValidData:
    """Test quality checks pass with valid data"""

    def test_run_all_checks_passes(self, quality_rules_path, sample_data_dir):
        """Quality checks pass with valid data"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(sample_data_dir),
            'silver'
        )
        report = checker.run_all_checks()

        assert report is not None
        assert 'quality_score' in report
        assert report['quality_score']['passes_threshold'] is True
        assert report['quality_score']['blocks_promotion'] is False

    def test_completeness_checks_pass(self, quality_rules_path, sample_data_dir):
        """Completeness checks pass"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(sample_data_dir),
            'silver'
        )

        stocks_df = pd.read_parquet(sample_data_dir / "stocks.parquet")
        results = checker.check_completeness('stocks', stocks_df)

        assert all(r['passed'] for r in results)

    def test_uniqueness_checks_pass(self, quality_rules_path, sample_data_dir):
        """Uniqueness checks pass"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(sample_data_dir),
            'silver'
        )

        stocks_df = pd.read_parquet(sample_data_dir / "stocks.parquet")
        results = checker.check_uniqueness('stocks', stocks_df)

        assert all(r['passed'] for r in results)

    def test_validity_checks_pass(self, quality_rules_path, sample_data_dir):
        """Validity checks pass"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(sample_data_dir),
            'silver'
        )

        stocks_df = pd.read_parquet(sample_data_dir / "stocks.parquet")
        results = checker.check_validity('stocks', stocks_df)

        assert all(r['passed'] for r in results)

    def test_referential_integrity_passes(self, quality_rules_path, sample_data_dir):
        """FK checks pass"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(sample_data_dir),
            'silver'
        )

        dfs = {
            'stocks': pd.read_parquet(sample_data_dir / "stocks.parquet"),
            'portfolios': pd.read_parquet(sample_data_dir / "portfolios.parquet"),
            'positions': pd.read_parquet(sample_data_dir / "positions.parquet")
        }

        results = checker.check_referential_integrity('positions', dfs['positions'], dfs)

        assert all(r['passed'] for r in results)


class TestQualityChecksWithInvalidData:
    """Test quality checks fail with invalid data"""

    def test_run_all_checks_fails(self, quality_rules_path, invalid_data_dir):
        """Quality checks fail with invalid data"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(invalid_data_dir),
            'silver'
        )
        report = checker.run_all_checks()

        assert report is not None
        assert 'quality_score' in report
        # Should fail due to critical issues
        assert report['quality_score']['blocks_promotion'] is True

    def test_duplicate_pk_detected(self, quality_rules_path, invalid_data_dir):
        """Duplicate PKs are detected"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(invalid_data_dir),
            'silver'
        )

        stocks_df = pd.read_parquet(invalid_data_dir / "stocks.parquet")
        results = checker.check_uniqueness('stocks', stocks_df)

        # Should detect duplicate AAPL
        ticker_result = next(r for r in results if r['column'] == 'ticker')
        assert ticker_result['passed'] is False
        assert ticker_result['duplicate_count'] > 0

    def test_null_detection(self, quality_rules_path, invalid_data_dir):
        """Null values are detected"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(invalid_data_dir),
            'silver'
        )

        stocks_df = pd.read_parquet(invalid_data_dir / "stocks.parquet")
        results = checker.check_completeness('stocks', stocks_df)

        # Should detect null in company_name
        company_name_result = next(r for r in results if r['column'] == 'company_name')
        assert company_name_result['passed'] is False
        assert company_name_result['null_count'] > 0

    def test_negative_price_detected(self, quality_rules_path, invalid_data_dir):
        """Negative prices are detected"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(invalid_data_dir),
            'silver'
        )

        stocks_df = pd.read_parquet(invalid_data_dir / "stocks.parquet")
        results = checker.check_validity('stocks', stocks_df)

        # Should detect negative price
        price_result = next(r for r in results if r['column'] == 'current_price')
        assert price_result['passed'] is False
        assert price_result['invalid_count'] > 0

    def test_invalid_fk_detected(self, quality_rules_path, invalid_data_dir):
        """Invalid FKs are detected"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(invalid_data_dir),
            'silver'
        )

        dfs = {
            'stocks': pd.read_parquet(invalid_data_dir / "stocks.parquet"),
            'portfolios': pd.read_parquet(invalid_data_dir / "portfolios.parquet"),
            'positions': pd.read_parquet(invalid_data_dir / "positions.parquet")
        }

        results = checker.check_referential_integrity('positions', dfs['positions'], dfs)

        # Should detect invalid portfolio_id FK
        portfolio_fk_result = next(r for r in results if r['column'] == 'portfolio_id')
        assert portfolio_fk_result['passed'] is False
        assert portfolio_fk_result['invalid_count'] > 0


class TestQuarantineLogic:
    """Test quarantine functionality"""

    def test_quarantine_records_created(self, quality_rules_path, invalid_data_dir):
        """Quarantine records are created for critical failures"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(invalid_data_dir),
            'silver'
        )

        checker.run_all_checks()

        # Should have quarantined some records
        assert len(checker.quarantine_records) > 0

    def test_quarantine_files_saved(self, quality_rules_path, invalid_data_dir):
        """Quarantine files are saved to disk"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(invalid_data_dir),
            'silver'
        )

        checker.run_all_checks()

        # Check quarantine directory exists
        quarantine_dir = invalid_data_dir / 'quarantine'
        assert quarantine_dir.exists()

        # Check quarantine files exist
        quarantine_files = list(quarantine_dir.glob('*.parquet'))
        assert len(quarantine_files) > 0


class TestQualityScoreCalculation:
    """Test quality score calculation"""

    def test_score_calculation_with_valid_data(self, quality_rules_path, sample_data_dir):
        """Quality score is high with valid data"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(sample_data_dir),
            'silver'
        )
        report = checker.run_all_checks()

        # Should have high score
        assert report['quality_score']['overall_score'] >= 0.8

    def test_score_calculation_with_invalid_data(self, quality_rules_path, invalid_data_dir):
        """Quality score is low with invalid data"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(invalid_data_dir),
            'silver'
        )
        report = checker.run_all_checks()

        # Should have low score due to critical failures
        assert report['quality_score']['critical_failures'] > 0

    def test_critical_failures_block_promotion(self, quality_rules_path, invalid_data_dir):
        """Critical failures block zone promotion"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(invalid_data_dir),
            'silver'
        )
        report = checker.run_all_checks()

        assert report['quality_score']['blocks_promotion'] is True


class TestReportGeneration:
    """Test quality report generation"""

    def test_report_file_created(self, quality_rules_path, sample_data_dir):
        """Quality report JSON file is created"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(sample_data_dir),
            'silver'
        )
        checker.run_all_checks()

        report_path = sample_data_dir / 'quality_report_silver.json'
        assert report_path.exists()

    def test_report_structure(self, quality_rules_path, sample_data_dir):
        """Quality report has expected structure"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(sample_data_dir),
            'silver'
        )
        report = checker.run_all_checks()

        assert 'workload' in report
        assert 'zone' in report
        assert 'timestamp' in report
        assert 'quality_score' in report
        assert 'checks' in report
        assert 'sox_compliant' in report

    def test_sox_compliance_flag(self, quality_rules_path, sample_data_dir):
        """SOX compliance flag is set correctly"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(sample_data_dir),
            'silver'
        )
        report = checker.run_all_checks()

        # Valid data should be SOX compliant
        assert report['sox_compliant'] is True


class TestAnomalyDetection:
    """Test anomaly detection"""

    def test_anomaly_detection_runs(self, quality_rules_path, sample_data_dir):
        """Anomaly detection executes without error"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(sample_data_dir),
            'silver'
        )

        stocks_df = pd.read_parquet(sample_data_dir / "stocks.parquet")
        results = checker.detect_anomalies('stocks', stocks_df)

        assert len(results) > 0
        assert all('outliers' in r for r in results)

    def test_z_score_anomaly_detection(self, quality_rules_path, sample_data_dir):
        """Z-score anomaly detection works"""
        checker = QualityChecker(
            str(quality_rules_path),
            str(sample_data_dir),
            'silver'
        )

        stocks_df = pd.read_parquet(sample_data_dir / "stocks.parquet")
        results = checker.detect_anomalies('stocks', stocks_df)

        z_score_results = [r for r in results if r['method'] == 'z_score']
        assert len(z_score_results) > 0
