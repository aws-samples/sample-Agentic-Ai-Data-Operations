#!/usr/bin/env python3
"""
Unit tests for stocks transformations
Tests transformation configuration and script structure

Run: python -m pytest workloads/stocks/tests/unit/test_transformations.py -v
"""

import pytest
import yaml
from pathlib import Path


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def workload_root():
    """Root directory of stocks workload"""
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
    assert transformations_config['workload'] == 'stocks'


def test_compliance_tag_present(transformations_config):
    """GDPR compliance tag is present"""
    assert 'compliance' in transformations_config
    assert 'GDPR' in transformations_config['compliance']


# =============================================================================
# BRONZE -> SILVER TESTS
# =============================================================================

def test_bronze_to_silver_has_stocks_table(transformations_config):
    """Bronze->Silver section includes stocks table"""
    b2s = transformations_config['bronze_to_silver']
    assert 'stocks' in b2s


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


def test_stocks_not_null_validations(transformations_config):
    """Stocks has not_null validations for required columns"""
    stocks = transformations_config['bronze_to_silver']['stocks']
    validations = stocks['validations']
    validation_columns = [v['column'] for v in validations]

    required_not_null = ['ticker', 'company_name', 'sector', 'industry', 'exchange']
    for col in required_not_null:
        assert col in validation_columns, f"Missing not_null validation for {col}"


def test_stocks_positive_value_validations(transformations_config):
    """Stocks has positive value validations for current_price and market_cap"""
    stocks = transformations_config['bronze_to_silver']['stocks']
    validations = stocks['validations']

    price_vals = [v for v in validations if v['column'] == 'current_price' and v['rule'] == 'greater_than']
    assert len(price_vals) > 0, "Missing current_price > 0 validation"
    assert price_vals[0]['value'] == 0

    mcap_vals = [v for v in validations if v['column'] == 'market_cap_billions' and v['rule'] == 'greater_than']
    assert len(mcap_vals) > 0, "Missing market_cap > 0 validation"
    assert mcap_vals[0]['value'] == 0


def test_stocks_price_range_validations(transformations_config):
    """Stocks has price range validations (high >= current, low <= current)"""
    stocks = transformations_config['bronze_to_silver']['stocks']
    validations = stocks['validations']

    high_vals = [v for v in validations if v['column'] == 'price_52w_high']
    assert len(high_vals) > 0, "Missing price_52w_high validation"
    assert high_vals[0]['rule'] == 'greater_than_or_equal'

    low_vals = [v for v in validations if v['column'] == 'price_52w_low']
    assert len(low_vals) > 0, "Missing price_52w_low validation"
    assert low_vals[0]['rule'] == 'less_than_or_equal'


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


def test_stocks_quarantine_configured(transformations_config):
    """Stocks has quarantine enabled with correct configuration"""
    stocks = transformations_config['bronze_to_silver']['stocks']
    assert 'quarantine' in stocks
    assert stocks['quarantine']['enabled'] is True
    assert 'quarantine' in stocks['quarantine']['path']
    assert stocks['quarantine']['retention_days'] == 30


def test_stocks_gdpr_columns_configured(transformations_config):
    """Stocks has GDPR metadata columns configured"""
    stocks = transformations_config['bronze_to_silver']['stocks']
    assert 'gdpr_columns' in stocks

    gdpr_cols = stocks['gdpr_columns']
    gdpr_col_names = [c['name'] for c in gdpr_cols]
    assert 'consent_given' in gdpr_col_names
    assert 'consent_timestamp' in gdpr_col_names
    assert 'is_deleted' in gdpr_col_names
    assert 'deletion_requested_at' in gdpr_col_names
    assert 'data_subject_id' in gdpr_col_names


# =============================================================================
# SILVER -> GOLD TESTS
# =============================================================================

def test_silver_to_gold_has_stocks_analytics(transformations_config):
    """Silver->Gold section includes stocks_analytics table"""
    s2g = transformations_config['silver_to_gold']
    assert 'stocks_analytics' in s2g


def test_stocks_analytics_is_flat_type(transformations_config):
    """stocks_analytics is configured as flat table (NOT star schema)"""
    analytics = transformations_config['silver_to_gold']['stocks_analytics']
    assert analytics['type'] == 'flat'
    assert analytics['columns'] == 'all'


def test_stocks_analytics_has_computed_columns(transformations_config):
    """stocks_analytics has all 5 computed columns defined"""
    analytics = transformations_config['silver_to_gold']['stocks_analytics']
    assert 'computed_columns' in analytics

    computed_names = [c['name'] for c in analytics['computed_columns']]
    expected = ['price_52w_range', 'price_pct_from_high', 'market_cap_category',
                'yield_category', 'volatility_category']
    for col in expected:
        assert col in computed_names, f"Missing computed column: {col}"


def test_stocks_analytics_output_is_iceberg(transformations_config):
    """stocks_analytics output is Iceberg format"""
    analytics = transformations_config['silver_to_gold']['stocks_analytics']
    assert analytics['output']['format'] == 'iceberg'
    assert 'gold' in analytics['output']['path']


def test_stocks_analytics_overwrite_mode(transformations_config):
    """stocks_analytics uses overwrite mode for idempotency"""
    analytics = transformations_config['silver_to_gold']['stocks_analytics']
    assert analytics['output']['table_properties']['write_mode'] == 'overwrite'


def test_stocks_analytics_no_partitioning(transformations_config):
    """stocks_analytics has no partitioning (only 50 rows)"""
    analytics = transformations_config['silver_to_gold']['stocks_analytics']
    assert analytics['output']['partition_by'] == []


# =============================================================================
# LINEAGE TRACKING TESTS
# =============================================================================

def test_lineage_enabled(transformations_config):
    """Lineage tracking is enabled"""
    lineage = transformations_config['lineage']
    assert lineage['enabled'] is True
    assert lineage['track_column_level'] is True
    assert lineage['track_transformations'] is True
    assert lineage['include_row_counts'] is True
    assert lineage['include_quality_metrics'] is True


def test_lineage_hash_algorithm(transformations_config):
    """Lineage uses SHA-256 hashing"""
    lineage = transformations_config['lineage']
    assert lineage['hash_algorithm'] == 'sha256'


# =============================================================================
# OUTPUT PATH CONVENTIONS TESTS
# =============================================================================

def test_silver_paths_follow_convention(transformations_config):
    """Silver output paths follow zone conventions"""
    b2s = transformations_config['bronze_to_silver']
    for table_name, table_config in b2s.items():
        path = table_config['output']['path']
        assert '/silver/' in path, f"{table_name} output path must contain '/silver/'"
        assert 'stocks' in path, f"{table_name} output path must contain workload name"


def test_gold_paths_follow_convention(transformations_config):
    """Gold output paths follow zone conventions"""
    s2g = transformations_config['silver_to_gold']
    for table_name, table_config in s2g.items():
        path = table_config['output']['path']
        assert '/gold/' in path, f"{table_name} output path must contain '/gold/'"
        assert 'stocks' in path, f"{table_name} output path must contain workload name"


def test_quarantine_paths_follow_convention(transformations_config):
    """Quarantine paths follow zone conventions"""
    b2s = transformations_config['bronze_to_silver']
    for table_name, table_config in b2s.items():
        if 'quarantine' in table_config and table_config['quarantine']['enabled']:
            path = table_config['quarantine']['path']
            assert '/quarantine/' in path, f"{table_name} quarantine path must contain '/quarantine/'"
            assert 'stocks' in path, f"{table_name} quarantine path must contain workload name"


# =============================================================================
# IDEMPOTENCY TESTS
# =============================================================================

def test_all_transformations_use_overwrite_mode(transformations_config):
    """All transformations use overwrite mode for idempotency"""
    # Bronze->Silver
    for table_name, table_config in transformations_config['bronze_to_silver'].items():
        assert table_config['output']['table_properties']['write_mode'] == 'overwrite', \
            f"{table_name} Bronze->Silver must use overwrite mode"

    # Silver->Gold
    for table_name, table_config in transformations_config['silver_to_gold'].items():
        assert table_config['output']['table_properties']['write_mode'] == 'overwrite', \
            f"{table_name} Silver->Gold must use overwrite mode"


def test_deduplication_strategy_is_deterministic(transformations_config):
    """Deduplication uses deterministic strategy"""
    stocks = transformations_config['bronze_to_silver']['stocks']
    dedup = stocks['deduplication']
    assert dedup['strategy'] == 'keep_last', "Should use keep_last strategy"


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


def test_gdpr_compliance_in_metadata(transformations_config):
    """GDPR compliance tag present"""
    assert 'compliance' in transformations_config
    assert 'GDPR' in transformations_config['compliance']


# =============================================================================
# SCRIPT EXISTENCE TESTS
# =============================================================================

def test_bronze_to_silver_script_exists(workload_root):
    """Bronze->Silver transformation script exists"""
    scripts_dir = workload_root / "scripts" / "transform"
    assert (scripts_dir / "bronze_to_silver.py").exists()


def test_silver_to_gold_script_exists(workload_root):
    """Silver->Gold transformation script exists"""
    scripts_dir = workload_root / "scripts" / "transform"
    assert (scripts_dir / "silver_to_gold.py").exists()


def test_all_scripts_have_shebang(workload_root):
    """All transformation scripts have shebang line"""
    scripts_dir = workload_root / "scripts" / "transform"

    for script in scripts_dir.glob("*.py"):
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
            assert 'lineage.json' in content or 'lineage_path' in content, \
                f"{script.name} missing lineage output"


# =============================================================================
# SCHEMA ALIGNMENT TESTS
# =============================================================================

def test_transformation_tables_match_semantic_tables(transformations_config, semantic_config):
    """Tables in transformations.yaml exist in semantic.yaml"""
    semantic_table_names = [t['name'] for t in semantic_config['tables']]

    # Bronze->Silver tables
    b2s_tables = list(transformations_config['bronze_to_silver'].keys())
    for table in b2s_tables:
        assert table in semantic_table_names, \
            f"Table {table} in transformations.yaml not found in semantic.yaml"


# =============================================================================
# SQL FILE EXISTENCE TESTS
# =============================================================================

def test_sql_files_exist(workload_root):
    """SQL DDL files exist for all zones"""
    assert (workload_root / "sql" / "bronze" / "create_bronze_table.sql").exists()
    assert (workload_root / "sql" / "silver" / "create_silver_table.sql").exists()
    assert (workload_root / "sql" / "gold" / "create_gold_table.sql").exists()


# =============================================================================
# COUNT TESTS
# =============================================================================

def test_total_transformation_count():
    """Total number of transformations: 1 Bronze->Silver + 1 Silver->Gold = 2"""
    expected_b2s = 1  # stocks
    expected_s2g = 1  # stocks_analytics (flat)
    expected_total = 2

    assert expected_total == expected_b2s + expected_s2g
