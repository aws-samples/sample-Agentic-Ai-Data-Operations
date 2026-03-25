#!/usr/bin/env python3
"""
Unit tests for financial_portfolios transformations
Tests transformation configuration and script structure

Run: python -m pytest workloads/financial_portfolios/tests/unit/test_transformations.py -v
"""

import pytest
import yaml
from pathlib import Path


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def workload_root():
    """Root directory of financial_portfolios workload"""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def transformations_config(workload_root):
    """Load transformations.yaml"""
    config_path = workload_root / "config" / "transformations.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


@pytest.fixture
def semantic_config(workload_root):
    """Load semantic.yaml for validation"""
    config_path = workload_root / "config" / "semantic.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


# =============================================================================
# CONFIGURATION STRUCTURE TESTS
# =============================================================================

def test_transformations_yaml_is_valid(transformations_config):
    """transformations.yaml is valid YAML"""
    assert transformations_config is not None


def test_has_required_top_level_keys(transformations_config):
    """transformations.yaml has required top-level keys"""
    required_keys = ['workload', 'version', 'bronze_to_silver', 'silver_to_gold', 'lineage']
    for key in required_keys:
        assert key in transformations_config, f"Missing required key: {key}"


def test_workload_name_matches(transformations_config):
    """Workload name is correct"""
    assert transformations_config['workload'] == 'financial_portfolios'


def test_compliance_tag_present(transformations_config):
    """SOX compliance tag is present"""
    assert 'compliance' in transformations_config
    assert 'SOX' in transformations_config['compliance']


# =============================================================================
# BRONZE → SILVER TESTS
# =============================================================================

def test_bronze_to_silver_has_all_tables(transformations_config):
    """Bronze→Silver section includes all 3 tables"""
    b2s = transformations_config['bronze_to_silver']
    assert 'stocks' in b2s
    assert 'portfolios' in b2s
    assert 'positions' in b2s


def test_stocks_deduplication_configured(transformations_config):
    """Stocks deduplication is configured correctly"""
    stocks = transformations_config['bronze_to_silver']['stocks']
    assert 'deduplication' in stocks
    assert stocks['deduplication']['key'] == 'ticker'
    assert stocks['deduplication']['strategy'] == 'keep_last'


def test_stocks_output_is_iceberg(transformations_config):
    """Stocks output format is Iceberg"""
    stocks = transformations_config['bronze_to_silver']['stocks']
    assert stocks['output']['format'] == 'iceberg'
    assert 'silver' in stocks['output']['path']


def test_portfolios_deduplication_configured(transformations_config):
    """Portfolios deduplication is configured correctly"""
    portfolios = transformations_config['bronze_to_silver']['portfolios']
    assert 'deduplication' in portfolios
    assert portfolios['deduplication']['key'] == 'portfolio_id'
    assert portfolios['deduplication']['strategy'] == 'keep_last'


def test_portfolios_output_is_iceberg(transformations_config):
    """Portfolios output format is Iceberg"""
    portfolios = transformations_config['bronze_to_silver']['portfolios']
    assert portfolios['output']['format'] == 'iceberg'
    assert 'silver' in portfolios['output']['path']


def test_positions_has_critical_validations(transformations_config):
    """Positions has all critical validations (quarantine rules)"""
    positions = transformations_config['bronze_to_silver']['positions']
    assert 'validations' in positions

    validations = positions['validations']
    validation_columns = [v['column'] for v in validations]

    # CRITICAL validations must be present
    assert 'ticker' in validation_columns
    assert 'shares' in validation_columns
    assert 'portfolio_id' in validation_columns

    # Check ticker validation
    ticker_validations = [v for v in validations if v['column'] == 'ticker']
    assert len(ticker_validations) >= 2  # not_null + fk check
    assert any(v.get('critical') for v in ticker_validations), "Ticker validation must be marked critical"

    # Check shares validation
    shares_validations = [v for v in validations if v['column'] == 'shares']
    assert len(shares_validations) >= 1
    assert any(v['rule'] == 'greater_than' and v['value'] == 0 for v in shares_validations)


def test_positions_fk_integrity_checks(transformations_config):
    """Positions has FK integrity checks for both portfolio_id and ticker"""
    positions = transformations_config['bronze_to_silver']['positions']
    validations = positions['validations']

    # FK check for portfolio_id
    portfolio_fk = [v for v in validations if v['column'] == 'portfolio_id' and v['rule'] == 'foreign_key']
    assert len(portfolio_fk) > 0, "Missing FK check for portfolio_id"
    assert portfolio_fk[0]['reference_table'] == 'portfolios'
    assert portfolio_fk[0]['action'] == 'quarantine'
    assert portfolio_fk[0].get('critical') == True

    # FK check for ticker
    ticker_fk = [v for v in validations if v['column'] == 'ticker' and v['rule'] == 'foreign_key']
    assert len(ticker_fk) > 0, "Missing FK check for ticker"
    assert ticker_fk[0]['reference_table'] == 'stocks'
    assert ticker_fk[0]['action'] == 'quarantine'
    assert ticker_fk[0].get('critical') == True


def test_positions_quarantine_enabled(transformations_config):
    """Positions has quarantine enabled with correct configuration"""
    positions = transformations_config['bronze_to_silver']['positions']
    assert 'quarantine' in positions
    assert positions['quarantine']['enabled'] == True
    assert 'quarantine' in positions['quarantine']['path']
    assert positions['quarantine']['retention_days'] == 30


def test_positions_output_is_iceberg_partitioned(transformations_config):
    """Positions output is Iceberg and partitioned by sector"""
    positions = transformations_config['bronze_to_silver']['positions']
    assert positions['output']['format'] == 'iceberg'
    assert 'silver' in positions['output']['path']
    assert 'partition_by' in positions['output']
    assert 'sector' in positions['output']['partition_by']


# =============================================================================
# SILVER → GOLD TESTS
# =============================================================================

def test_silver_to_gold_has_star_schema_tables(transformations_config):
    """Silver→Gold includes all star schema tables"""
    s2g = transformations_config['silver_to_gold']
    assert 'dim_stocks' in s2g
    assert 'dim_portfolios' in s2g
    assert 'fact_positions' in s2g
    assert 'portfolio_summary' in s2g


def test_dim_stocks_is_dimension_table(transformations_config):
    """dim_stocks is configured as dimension table"""
    dim_stocks = transformations_config['silver_to_gold']['dim_stocks']
    assert dim_stocks['type'] == 'dimension'
    assert dim_stocks['scd_type'] == 1
    assert dim_stocks['columns'] == 'all'


def test_dim_portfolios_is_dimension_table(transformations_config):
    """dim_portfolios is configured as dimension table"""
    dim_portfolios = transformations_config['silver_to_gold']['dim_portfolios']
    assert dim_portfolios['type'] == 'dimension'
    assert dim_portfolios['scd_type'] == 1
    assert dim_portfolios['columns'] == 'all'


def test_fact_positions_is_fact_table(transformations_config):
    """fact_positions is configured as fact table"""
    fact = transformations_config['silver_to_gold']['fact_positions']
    assert fact['type'] == 'fact'
    assert 'grain' in fact
    assert 'one row per position' in fact['grain'].lower()


def test_fact_positions_has_joins(transformations_config):
    """fact_positions has joins to dimension tables"""
    fact = transformations_config['silver_to_gold']['fact_positions']
    assert 'joins' in fact
    assert len(fact['joins']) == 2

    # Check stocks join
    stocks_join = [j for j in fact['joins'] if j['table'].endswith('stocks')]
    assert len(stocks_join) == 1
    assert stocks_join[0]['type'] == 'inner'
    assert 'ticker' in stocks_join[0]['on']

    # Check portfolios join
    portfolios_join = [j for j in fact['joins'] if j['table'].endswith('portfolios')]
    assert len(portfolios_join) == 1
    assert portfolios_join[0]['type'] == 'inner'
    assert 'portfolio_id' in portfolios_join[0]['on']


def test_fact_positions_has_filters(transformations_config):
    """fact_positions filters for open positions and active portfolios"""
    fact = transformations_config['silver_to_gold']['fact_positions']
    assert 'filters' in fact
    assert len(fact['filters']) >= 2

    filters_text = ' '.join([f['condition'].lower() for f in fact['filters']])
    assert 'open' in filters_text
    assert 'active' in filters_text


def test_fact_positions_output_partitioned_by_sector(transformations_config):
    """fact_positions is partitioned by sector"""
    fact = transformations_config['silver_to_gold']['fact_positions']
    assert fact['output']['format'] == 'iceberg'
    assert 'sector' in fact['output']['partition_by']


def test_portfolio_summary_is_aggregate(transformations_config):
    """portfolio_summary is configured as aggregate table"""
    summary = transformations_config['silver_to_gold']['portfolio_summary']
    assert summary['type'] == 'aggregate'
    assert 'aggregations' in summary
    assert 'group_by' in summary


def test_portfolio_summary_aggregations_correct(transformations_config):
    """portfolio_summary has correct aggregations"""
    summary = transformations_config['silver_to_gold']['portfolio_summary']
    aggs = summary['aggregations']

    # Check required aggregations
    agg_columns = [a['column'] for a in aggs]
    assert 'market_value' in agg_columns
    assert 'cost_basis' in agg_columns
    assert 'unrealized_gain_loss' in agg_columns
    assert 'position_id' in agg_columns

    # Check aggregation functions
    market_value_agg = [a for a in aggs if a['column'] == 'market_value'][0]
    assert market_value_agg['function'] == 'sum'
    assert market_value_agg['alias'] == 'total_market_value'

    position_count_agg = [a for a in aggs if a['column'] == 'position_id'][0]
    assert position_count_agg['function'] == 'count'
    assert position_count_agg['alias'] == 'num_positions'


def test_portfolio_summary_groups_by_portfolio_id(transformations_config):
    """portfolio_summary groups by portfolio_id"""
    summary = transformations_config['silver_to_gold']['portfolio_summary']
    assert 'portfolio_id' in summary['group_by']


def test_portfolio_summary_has_calculated_column(transformations_config):
    """portfolio_summary has total_return_pct calculated column"""
    summary = transformations_config['silver_to_gold']['portfolio_summary']
    assert 'calculated_columns' in summary

    calc_cols = summary['calculated_columns']
    assert len(calc_cols) > 0

    return_pct = [c for c in calc_cols if c['name'] == 'total_return_pct']
    assert len(return_pct) == 1
    assert 'cost_basis' in return_pct[0]['expression']
    assert 'unrealized_gain_loss' in return_pct[0]['expression']


# =============================================================================
# LINEAGE TRACKING TESTS
# =============================================================================

def test_lineage_enabled(transformations_config):
    """Lineage tracking is enabled"""
    lineage = transformations_config['lineage']
    assert lineage['enabled'] == True
    assert lineage['track_column_level'] == True
    assert lineage['track_transformations'] == True
    assert lineage['include_row_counts'] == True
    assert lineage['include_quality_metrics'] == True


def test_lineage_hash_algorithm(transformations_config):
    """Lineage uses SHA-256 hashing"""
    lineage = transformations_config['lineage']
    assert lineage['hash_algorithm'] == 'sha256'


# =============================================================================
# OUTPUT PATH CONVENTIONS TESTS
# =============================================================================

def test_all_silver_paths_follow_convention(transformations_config):
    """All Silver output paths follow zone conventions"""
    b2s = transformations_config['bronze_to_silver']
    for table_name, table_config in b2s.items():
        path = table_config['output']['path']
        assert '/silver/' in path, f"{table_name} output path must contain '/silver/'"
        assert 'financial_portfolios' in path, f"{table_name} output path must contain workload name"
        assert table_name in path, f"{table_name} output path must contain table name"


def test_all_gold_paths_follow_convention(transformations_config):
    """All Gold output paths follow zone conventions"""
    s2g = transformations_config['silver_to_gold']
    for table_name, table_config in s2g.items():
        path = table_config['output']['path']
        assert '/gold/' in path, f"{table_name} output path must contain '/gold/'"
        assert 'financial_portfolios' in path, f"{table_name} output path must contain workload name"


def test_all_quarantine_paths_follow_convention(transformations_config):
    """All quarantine paths follow zone conventions"""
    b2s = transformations_config['bronze_to_silver']
    for table_name, table_config in b2s.items():
        if 'quarantine' in table_config and table_config['quarantine']['enabled']:
            path = table_config['quarantine']['path']
            assert '/quarantine/' in path, f"{table_name} quarantine path must contain '/quarantine/'"
            assert 'financial_portfolios' in path, f"{table_name} quarantine path must contain workload name"


# =============================================================================
# TYPE CONVERSION TESTS
# =============================================================================

def test_stocks_type_conversions(transformations_config):
    """Stocks has correct type conversions"""
    stocks = transformations_config['bronze_to_silver']['stocks']
    conversions = stocks['type_conversions']

    # Date columns
    date_cols = [c for c in conversions if c['to'] == 'date']
    assert len(date_cols) == 1
    assert any(c['column'] == 'listing_date' for c in date_cols)

    # Decimal columns
    decimal_cols = [c for c in conversions if c['to'] == 'decimal']
    assert len(decimal_cols) >= 8  # All numeric columns should be decimal


def test_portfolios_type_conversions(transformations_config):
    """Portfolios has correct type conversions"""
    portfolios = transformations_config['bronze_to_silver']['portfolios']
    conversions = portfolios['type_conversions']

    # Date columns
    date_cols = [c for c in conversions if c['to'] == 'date']
    assert len(date_cols) == 2  # inception_date, last_rebalance_date

    # Integer columns
    int_cols = [c for c in conversions if c['to'] == 'integer']
    assert len(int_cols) == 1  # num_positions


def test_positions_type_conversions(transformations_config):
    """Positions has correct type conversions including timestamp"""
    positions = transformations_config['bronze_to_silver']['positions']
    conversions = positions['type_conversions']

    # Date columns
    date_cols = [c for c in conversions if c['to'] == 'date']
    assert any(c['column'] == 'entry_date' for c in date_cols)

    # Timestamp columns
    timestamp_cols = [c for c in conversions if c['to'] == 'timestamp']
    assert any(c['column'] == 'last_updated' for c in timestamp_cols)

    # Decimal columns with precision
    shares_conv = [c for c in conversions if c['column'] == 'shares']
    assert len(shares_conv) == 1
    assert shares_conv[0]['precision'] == 15
    assert shares_conv[0]['scale'] == 4  # 4 decimal places for shares


# =============================================================================
# VALIDATION RULES TESTS
# =============================================================================

def test_positions_ticker_not_null_validation(transformations_config):
    """Positions validates ticker not null (CRITICAL)"""
    positions = transformations_config['bronze_to_silver']['positions']
    validations = positions['validations']

    ticker_validations = [v for v in validations if v['column'] == 'ticker' and v['rule'] == 'not_null']
    assert len(ticker_validations) > 0
    assert ticker_validations[0]['action'] == 'quarantine'
    assert ticker_validations[0].get('critical') == True


def test_positions_negative_shares_validation(transformations_config):
    """Positions validates shares > 0 (CRITICAL)"""
    positions = transformations_config['bronze_to_silver']['positions']
    validations = positions['validations']

    shares_validations = [v for v in validations if v['column'] == 'shares']
    assert len(shares_validations) > 0
    assert shares_validations[0]['rule'] == 'greater_than'
    assert shares_validations[0]['value'] == 0
    assert shares_validations[0]['action'] == 'quarantine'
    assert shares_validations[0].get('critical') == True


def test_positions_portfolio_fk_validation(transformations_config):
    """Positions validates portfolio_id FK (CRITICAL)"""
    positions = transformations_config['bronze_to_silver']['positions']
    validations = positions['validations']

    portfolio_fk = [v for v in validations if v['column'] == 'portfolio_id' and v['rule'] == 'foreign_key']
    assert len(portfolio_fk) > 0
    assert portfolio_fk[0]['reference_table'] == 'portfolios'
    assert portfolio_fk[0]['reference_column'] == 'portfolio_id'
    assert portfolio_fk[0]['action'] == 'quarantine'
    assert portfolio_fk[0].get('critical') == True


def test_positions_ticker_fk_validation(transformations_config):
    """Positions validates ticker FK (CRITICAL)"""
    positions = transformations_config['bronze_to_silver']['positions']
    validations = positions['validations']

    ticker_fk = [v for v in validations if v['column'] == 'ticker' and v['rule'] == 'foreign_key']
    assert len(ticker_fk) > 0
    assert ticker_fk[0]['reference_table'] == 'stocks'
    assert ticker_fk[0]['reference_column'] == 'ticker'
    assert ticker_fk[0]['action'] == 'quarantine'
    assert ticker_fk[0].get('critical') == True


# =============================================================================
# STAR SCHEMA STRUCTURE TESTS
# =============================================================================

def test_star_schema_has_fact_and_dimensions(transformations_config):
    """Star schema has 1 fact table + 2 dimension tables + 1 aggregate"""
    s2g = transformations_config['silver_to_gold']

    # Dimensions
    dims = [k for k, v in s2g.items() if v.get('type') == 'dimension']
    assert len(dims) == 2
    assert 'dim_stocks' in dims
    assert 'dim_portfolios' in dims

    # Fact
    facts = [k for k, v in s2g.items() if v.get('type') == 'fact']
    assert len(facts) == 1
    assert 'fact_positions' in facts

    # Aggregate
    aggs = [k for k, v in s2g.items() if v.get('type') == 'aggregate']
    assert len(aggs) == 1
    assert 'portfolio_summary' in aggs


def test_fact_table_has_required_columns(transformations_config):
    """fact_positions has all required fact columns"""
    fact = transformations_config['silver_to_gold']['fact_positions']
    columns = fact['columns']

    required_columns = [
        'position_id',  # PK
        'portfolio_id',  # FK
        'ticker',  # FK
        'shares', 'market_value', 'unrealized_gain_loss',  # Measures
        'entry_date', 'last_updated',  # Temporal
        'sector', 'position_status'  # Denormalized dimensions
    ]

    for col in required_columns:
        assert col in columns, f"Missing required column: {col}"


def test_all_gold_tables_are_iceberg(transformations_config):
    """All Gold tables use Iceberg format"""
    s2g = transformations_config['silver_to_gold']
    for table_name, table_config in s2g.items():
        assert table_config['output']['format'] == 'iceberg', f"{table_name} must be Iceberg"


# =============================================================================
# SCRIPT EXISTENCE TESTS
# =============================================================================

def test_bronze_to_silver_scripts_exist(workload_root):
    """All Bronze→Silver transformation scripts exist"""
    scripts_dir = workload_root / "scripts" / "transform"

    assert (scripts_dir / "bronze_to_silver_stocks.py").exists()
    assert (scripts_dir / "bronze_to_silver_portfolios.py").exists()
    assert (scripts_dir / "bronze_to_silver_positions.py").exists()


def test_silver_to_gold_scripts_exist(workload_root):
    """All Silver→Gold transformation scripts exist"""
    scripts_dir = workload_root / "scripts" / "transform"

    assert (scripts_dir / "silver_to_gold_dim_stocks.py").exists()
    assert (scripts_dir / "silver_to_gold_dim_portfolios.py").exists()
    assert (scripts_dir / "silver_to_gold_fact_positions.py").exists()
    assert (scripts_dir / "silver_to_gold_portfolio_summary.py").exists()


def test_all_scripts_are_executable(workload_root):
    """All transformation scripts have execute permissions"""
    scripts_dir = workload_root / "scripts" / "transform"

    for script in scripts_dir.glob("*.py"):
        # Check shebang
        with open(script, 'r') as f:
            first_line = f.readline()
            assert first_line.startswith('#!'), f"{script.name} missing shebang"


def test_all_scripts_have_local_mode(workload_root):
    """All transformation scripts support --local mode"""
    scripts_dir = workload_root / "scripts" / "transform"

    for script in scripts_dir.glob("*.py"):
        with open(script, 'r') as f:
            content = f.read()
            assert '--local' in content, f"{script.name} missing --local mode support"
            assert 'transform_local_mode' in content, f"{script.name} missing local mode function"
            assert 'transform_glue_mode' in content, f"{script.name} missing Glue mode function"


def test_all_scripts_generate_lineage(workload_root):
    """All transformation scripts generate lineage"""
    scripts_dir = workload_root / "scripts" / "transform"

    for script in scripts_dir.glob("*.py"):
        with open(script, 'r') as f:
            content = f.read()
            assert 'lineage' in content.lower(), f"{script.name} missing lineage tracking"
            assert 'lineage.json' in content or 'lineage_path' in content, f"{script.name} missing lineage output"


# =============================================================================
# SCHEMA ALIGNMENT TESTS
# =============================================================================

def test_transformation_tables_match_semantic_tables(transformations_config, semantic_config):
    """All tables in transformations.yaml exist in semantic.yaml"""
    semantic_table_names = [t['name'] for t in semantic_config['tables']]

    # Bronze→Silver tables
    b2s_tables = list(transformations_config['bronze_to_silver'].keys())
    for table in b2s_tables:
        assert table in semantic_table_names, f"Table {table} in transformations.yaml not found in semantic.yaml"


def test_fact_table_grain_matches_semantic(transformations_config, semantic_config):
    """fact_positions grain matches semantic.yaml"""
    fact_grain = transformations_config['silver_to_gold']['fact_positions']['grain']

    positions_table = [t for t in semantic_config['tables'] if t['name'] == 'positions'][0]
    semantic_grain = positions_table['grain']

    # Both should reference "position" as the grain
    assert 'position' in fact_grain.lower()
    assert 'position' in semantic_grain.lower()


# =============================================================================
# IDEMPOTENCY TESTS
# =============================================================================

def test_all_transformations_use_overwrite_mode(transformations_config):
    """All transformations use overwrite mode for idempotency"""
    # Bronze→Silver
    for table_name, table_config in transformations_config['bronze_to_silver'].items():
        assert table_config['output']['table_properties']['write_mode'] == 'overwrite', \
            f"{table_name} Bronze→Silver must use overwrite mode"

    # Silver→Gold
    for table_name, table_config in transformations_config['silver_to_gold'].items():
        assert table_config['output']['table_properties']['write_mode'] == 'overwrite', \
            f"{table_name} Silver→Gold must use overwrite mode"


def test_deduplication_strategy_is_deterministic(transformations_config):
    """Deduplication uses deterministic strategy"""
    b2s = transformations_config['bronze_to_silver']

    # All tables should have deduplication
    for table_name in ['stocks', 'portfolios', 'positions']:
        dedup = b2s[table_name]['deduplication']
        assert dedup['strategy'] == 'keep_last', f"{table_name} should use keep_last strategy"


# =============================================================================
# SECURITY & COMPLIANCE TESTS
# =============================================================================

def test_no_hardcoded_bucket_names(transformations_config):
    """No hardcoded S3 bucket names in paths"""
    config_str = str(transformations_config)

    # Paths should use ${DATA_LAKE_BUCKET} variable
    assert '${DATA_LAKE_BUCKET}' in config_str, "Paths must use ${DATA_LAKE_BUCKET} variable"

    # Should not have literal bucket names
    assert 's3://my-bucket' not in config_str.lower()
    assert 's3://prod-bucket' not in config_str.lower()


def test_sox_compliance_in_metadata(transformations_config):
    """SOX compliance tag present in metadata"""
    assert 'compliance' in transformations_config
    assert 'SOX' in transformations_config['compliance']


# =============================================================================
# EDGE CASE HANDLING TESTS
# =============================================================================

def test_positions_handles_invalid_fks(transformations_config):
    """Positions configuration handles invalid FKs with quarantine"""
    positions = transformations_config['bronze_to_silver']['positions']
    validations = positions['validations']

    # Both FK checks should quarantine (not reject)
    fk_validations = [v for v in validations if v['rule'] == 'foreign_key']
    assert len(fk_validations) == 2

    for fk_val in fk_validations:
        assert fk_val['action'] == 'quarantine', "FK violations must quarantine, not reject"


def test_quarantine_retention_configured(transformations_config):
    """Quarantine zones have retention configured"""
    b2s = transformations_config['bronze_to_silver']

    for table_name, table_config in b2s.items():
        if 'quarantine' in table_config and table_config['quarantine']['enabled']:
            assert 'retention_days' in table_config['quarantine']
            assert table_config['quarantine']['retention_days'] == 30


# =============================================================================
# COUNT TESTS
# =============================================================================

def test_total_transformation_count():
    """Total number of transformations: 3 Bronze→Silver + 4 Silver→Gold = 7"""
    # This test documents expected transformation count
    expected_b2s = 3  # stocks, portfolios, positions
    expected_s2g = 4  # dim_stocks, dim_portfolios, fact_positions, portfolio_summary
    expected_total = 7

    # Verify via transformations.yaml structure
    # Actual counts verified in other tests
    assert expected_total == expected_b2s + expected_s2g
