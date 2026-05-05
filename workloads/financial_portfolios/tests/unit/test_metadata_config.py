"""
Unit tests for Metadata Agent configuration files.
Tests that source.yaml and semantic.yaml are valid and complete.
"""

import os
import pytest
import yaml
from pathlib import Path

# Get workload directory
WORKLOAD_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = WORKLOAD_DIR / "config"

# Expected profiling data
EXPECTED_TABLES = {
    "stocks": {
        "row_count": 50,
        "column_count": 14,
        "primary_key": "ticker",
        "columns": [
            "ticker", "company_name", "sector", "industry", "exchange",
            "market_cap_billions", "current_price", "price_52w_high", "price_52w_low",
            "pe_ratio", "dividend_yield", "beta", "avg_volume_millions", "listing_date"
        ]
    },
    "portfolios": {
        "row_count": 15,
        "column_count": 15,
        "primary_key": "portfolio_id",
        "columns": [
            "portfolio_id", "portfolio_name", "manager_name", "strategy", "risk_level",
            "benchmark", "inception_date", "total_value", "cash_balance", "num_positions",
            "avg_position_size", "largest_position_pct", "status", "rebalance_frequency",
            "last_rebalance_date"
        ]
    },
    "positions": {
        "row_count": 138,
        "column_count": 16,
        "primary_key": "position_id",
        "foreign_keys": [
            {"column": "portfolio_id", "references_table": "portfolios"},
            {"column": "ticker", "references_table": "stocks"}
        ],
        "columns": [
            "position_id", "portfolio_id", "ticker", "shares", "cost_basis",
            "purchase_price", "current_price", "market_value", "unrealized_gain_loss",
            "unrealized_gain_loss_pct", "weight_pct", "entry_date", "last_updated",
            "holding_period_days", "sector", "position_status"
        ]
    }
}

PII_COLUMNS = {
    "stocks": [
        {"column": "company_name", "type": "NAME", "sensitivity": "LOW"}
    ],
    "portfolios": [
        {"column": "portfolio_name", "type": "NAME", "sensitivity": "LOW"},
        {"column": "manager_name", "type": "NAME", "sensitivity": "MEDIUM"}
    ],
    "positions": []
}

MEASURES = {
    "stocks": ["market_cap_billions", "current_price", "price_52w_high", "price_52w_low",
               "pe_ratio", "dividend_yield", "beta", "avg_volume_millions"],
    "portfolios": ["total_value", "cash_balance", "num_positions", "avg_position_size",
                   "largest_position_pct"],
    "positions": ["shares", "cost_basis", "purchase_price", "current_price", "market_value",
                  "unrealized_gain_loss", "unrealized_gain_loss_pct", "weight_pct",
                  "holding_period_days"]
}


class TestSourceConfig:
    """Test source.yaml configuration file."""

    @pytest.fixture
    def source_config(self):
        """Load source.yaml."""
        source_file = CONFIG_DIR / "source.yaml"
        assert source_file.exists(), f"source.yaml not found at {source_file}"

        with open(source_file, 'r') as f:
            config = yaml.safe_load(f)

        return config

    def test_source_yaml_is_valid(self, source_config):
        """Test that source.yaml is valid YAML."""
        assert source_config is not None
        assert isinstance(source_config, dict)

    def test_source_has_required_fields(self, source_config):
        """Test that source.yaml contains all required top-level fields."""
        assert 'source' in source_config
        source = source_config['source']

        required_fields = ['name', 'type', 'format', 'location', 'credentials',
                          'frequency', 'tables']
        for field in required_fields:
            assert field in source, f"Missing required field: {field}"

    def test_source_name_matches_workload(self, source_config):
        """Test that source name matches workload name."""
        assert source_config['source']['name'] == 'financial_portfolios'

    def test_source_type_is_s3(self, source_config):
        """Test that source type is S3."""
        assert source_config['source']['type'] == 's3'
        assert source_config['source']['format'] == 'csv'

    def test_source_location_is_valid(self, source_config):
        """Test that S3 location is valid."""
        location = source_config['source']['location']
        assert location.startswith('s3://')
        assert 'financial_portfolios' in location

    def test_credentials_reference_secrets_manager(self, source_config):
        """Test that credentials reference AWS Secrets Manager."""
        creds = source_config['source']['credentials']
        assert creds['type'] == 'iam_role'
        assert 'role_arn_secret' in creds
        assert creds['role_arn_secret'].startswith('arn:aws:secretsmanager:')

    def test_all_tables_defined(self, source_config):
        """Test that all 3 tables are defined."""
        tables = source_config['source']['tables']
        assert len(tables) == 3

        table_names = [t['name'] for t in tables]
        assert set(table_names) == {'stocks', 'portfolios', 'positions'}

    def test_table_primary_keys(self, source_config):
        """Test that each table has correct primary key."""
        tables = {t['name']: t for t in source_config['source']['tables']}

        assert tables['stocks']['primary_key'] == 'ticker'
        assert tables['portfolios']['primary_key'] == 'portfolio_id'
        assert tables['positions']['primary_key'] == 'position_id'

    def test_foreign_keys_defined(self, source_config):
        """Test that positions table has foreign keys."""
        tables = {t['name']: t for t in source_config['source']['tables']}
        positions = tables['positions']

        assert 'foreign_keys' in positions
        fks = positions['foreign_keys']
        assert len(fks) == 2

        fk_columns = {fk['column'] for fk in fks}
        assert fk_columns == {'portfolio_id', 'ticker'}

    def test_compliance_tags(self, source_config):
        """Test that SOX compliance is specified."""
        compliance = source_config['source']['compliance']
        assert 'SOX' in compliance

    def test_retention_policy(self, source_config):
        """Test that retention policy is 7 years."""
        assert source_config['source']['retention_years'] == 7


class TestSemanticConfig:
    """Test semantic.yaml configuration file."""

    @pytest.fixture
    def semantic_config(self):
        """Load semantic.yaml."""
        semantic_file = CONFIG_DIR / "semantic.yaml"
        assert semantic_file.exists(), f"semantic.yaml not found at {semantic_file}"

        with open(semantic_file, 'r') as f:
            config = yaml.safe_load(f)

        return config

    def test_semantic_yaml_is_valid(self, semantic_config):
        """Test that semantic.yaml is valid YAML."""
        assert semantic_config is not None
        assert isinstance(semantic_config, dict)

    def test_semantic_has_required_sections(self, semantic_config):
        """Test that semantic.yaml contains all required sections."""
        required_sections = ['workload', 'domain', 'use_case', 'schema_format',
                            'tables', 'business_terms', 'dimension_hierarchies',
                            'default_filters', 'time_intelligence', 'seed_questions',
                            'data_stewardship', 'join_semantics']
        for section in required_sections:
            assert section in semantic_config, f"Missing required section: {section}"

    def test_workload_name_matches(self, semantic_config):
        """Test that workload name matches."""
        assert semantic_config['workload'] == 'financial_portfolios'

    def test_domain_is_finance(self, semantic_config):
        """Test that domain is finance."""
        assert semantic_config['domain'] == 'finance'

    def test_use_case_is_reporting(self, semantic_config):
        """Test that use case is reporting and dashboards."""
        assert semantic_config['use_case'] == 'reporting_and_dashboards'
        assert semantic_config['schema_format'] == 'star_schema'

    def test_all_tables_present(self, semantic_config):
        """Test that all 3 tables are defined."""
        tables = semantic_config['tables']
        assert len(tables) == 3

        table_names = [t['name'] for t in tables]
        assert set(table_names) == {'stocks', 'portfolios', 'positions'}

    def test_all_columns_present(self, semantic_config):
        """Test that all columns from profiling are present."""
        tables = {t['name']: t for t in semantic_config['tables']}

        for table_name, expected in EXPECTED_TABLES.items():
            actual_columns = [c['name'] for c in tables[table_name]['columns']]
            expected_columns = expected['columns']

            assert set(actual_columns) == set(expected_columns), \
                f"Column mismatch in {table_name}: expected {expected_columns}, got {actual_columns}"

    def test_primary_keys_defined(self, semantic_config):
        """Test that each table has primary key defined."""
        tables = {t['name']: t for t in semantic_config['tables']}

        assert tables['stocks']['primary_key'] == 'ticker'
        assert tables['portfolios']['primary_key'] == 'portfolio_id'
        assert tables['positions']['primary_key'] == 'position_id'

    def test_grain_defined_for_fact_table(self, semantic_config):
        """Test that fact table (positions) has grain defined."""
        tables = {t['name']: t for t in semantic_config['tables']}

        assert 'grain' in tables['positions']
        assert tables['positions']['grain'] != ''
        assert 'One row per' in tables['positions']['grain']

    def test_table_types_correct(self, semantic_config):
        """Test that table types are correct (dimension vs fact)."""
        tables = {t['name']: t for t in semantic_config['tables']}

        assert tables['stocks']['table_type'] == 'dimension'
        assert tables['portfolios']['table_type'] == 'dimension'
        assert tables['positions']['table_type'] == 'fact'

    def test_all_columns_have_roles(self, semantic_config):
        """Test that all columns have role classification."""
        tables = {t['name']: t for t in semantic_config['tables']}
        valid_roles = {'identifier', 'measure', 'dimension', 'temporal'}

        for table_name, table in tables.items():
            for column in table['columns']:
                assert 'role' in column, f"Column {column['name']} in {table_name} missing role"
                assert column['role'] in valid_roles, \
                    f"Invalid role '{column['role']}' for {column['name']} in {table_name}"

    def test_all_measures_have_aggregation(self, semantic_config):
        """Test that all measure columns have default_aggregation defined."""
        tables = {t['name']: t for t in semantic_config['tables']}
        valid_aggs = {'sum', 'avg', 'count', 'count_distinct', 'min', 'max', 'weighted_avg'}

        for table_name, table in tables.items():
            for column in table['columns']:
                if column['role'] == 'measure':
                    assert 'default_aggregation' in column, \
                        f"Measure {column['name']} in {table_name} missing default_aggregation"
                    assert column['default_aggregation'] in valid_aggs, \
                        f"Invalid aggregation '{column['default_aggregation']}' for {column['name']}"

    def test_pii_columns_tagged(self, semantic_config):
        """Test that all PII columns are properly tagged."""
        tables = {t['name']: t for t in semantic_config['tables']}

        for table_name, expected_pii in PII_COLUMNS.items():
            table = tables[table_name]
            columns = {c['name']: c for c in table['columns']}

            for pii_def in expected_pii:
                col_name = pii_def['column']
                assert col_name in columns, f"PII column {col_name} not found in {table_name}"

                column = columns[col_name]
                assert 'pii_classification' in column
                assert column['pii_classification'] is not None
                assert column['pii_classification']['type'] == pii_def['type']
                assert column['pii_classification']['sensitivity'] == pii_def['sensitivity']

    def test_relationships_defined(self, semantic_config):
        """Test that all table relationships are defined."""
        tables = {t['name']: t for t in semantic_config['tables']}

        # Stocks has one_to_many to positions
        stocks_rels = tables['stocks']['relationships']
        assert len(stocks_rels) == 1
        assert stocks_rels[0]['target_table'] == 'positions'
        assert stocks_rels[0]['type'] == 'one_to_many'

        # Portfolios has one_to_many to positions
        portfolios_rels = tables['portfolios']['relationships']
        assert len(portfolios_rels) == 1
        assert portfolios_rels[0]['target_table'] == 'positions'
        assert portfolios_rels[0]['type'] == 'one_to_many'

        # Positions has many_to_one to both stocks and portfolios
        positions_rels = tables['positions']['relationships']
        assert len(positions_rels) == 2
        rel_targets = {r['target_table'] for r in positions_rels}
        assert rel_targets == {'stocks', 'portfolios'}
        for rel in positions_rels:
            assert rel['type'] == 'many_to_one'

    def test_business_terms_defined(self, semantic_config):
        """Test that business terms and synonyms are defined."""
        business_terms = semantic_config['business_terms']
        assert len(business_terms) >= 3

        # Check required fields
        for term in business_terms:
            assert 'term' in term
            assert 'synonyms' in term
            assert 'sql_expression' in term
            assert 'description' in term

    def test_dimension_hierarchies_defined(self, semantic_config):
        """Test that dimension hierarchies are defined."""
        hierarchies = semantic_config['dimension_hierarchies']
        assert len(hierarchies) >= 2

        hierarchy_names = {h['name'] for h in hierarchies}
        assert 'equity_classification' in hierarchy_names
        assert 'portfolio_management' in hierarchy_names

        # Check hierarchy structure
        for hierarchy in hierarchies:
            assert 'levels' in hierarchy
            assert len(hierarchy['levels']) >= 2

    def test_default_filters_defined(self, semantic_config):
        """Test that default filters are defined."""
        filters = semantic_config['default_filters']
        assert len(filters) >= 2

        # Check filter structure
        for filter_def in filters:
            assert 'name' in filter_def
            assert 'filter' in filter_def
            assert 'applies_to_tables' in filter_def

    def test_time_intelligence_defined(self, semantic_config):
        """Test that time intelligence settings are defined."""
        time_intel = semantic_config['time_intelligence']

        assert time_intel['fiscal_year_start'] == '01-01'
        assert time_intel['week_start_day'] == 'sunday'
        assert time_intel['timezone'] == 'UTC'
        assert time_intel['display_timezone'] == 'US/Eastern'
        assert time_intel['data_freshness_hours'] == 24

        assert 'temporal_columns' in time_intel
        assert len(time_intel['temporal_columns']) >= 3

    def test_seed_questions_defined(self, semantic_config):
        """Test that seed questions are defined."""
        seed_questions = semantic_config['seed_questions']
        assert len(seed_questions) >= 5

        # Check question structure
        for question in seed_questions:
            assert 'question' in question
            assert 'sql' in question
            assert 'explanation' in question

    def test_data_stewardship_defined(self, semantic_config):
        """Test that data stewardship information is defined."""
        stewardship = semantic_config['data_stewardship']

        assert 'owner' in stewardship
        assert 'steward' in stewardship
        assert 'contact' in stewardship
        assert 'update_schedule' in stewardship

    def test_join_semantics_defined(self, semantic_config):
        """Test that join semantics are defined for AWS Semantic Layer consumer."""
        join_semantics = semantic_config['join_semantics']
        assert len(join_semantics) >= 3

        join_names = {j['join_name'] for j in join_semantics}
        assert 'positions_with_stock_details' in join_names
        assert 'positions_with_portfolio_details' in join_names
        assert 'full_position_context' in join_names

        # Check join structure
        for join in join_semantics:
            assert 'tables' in join
            assert 'join_type' in join
            assert 'join_condition' in join
            assert 'when_to_join' in join
            assert 'pre_aggregation_rule' in join
            assert 'sample_query' in join

    def test_weighted_avg_has_weighted_by(self, semantic_config):
        """Test that columns with weighted_avg have weighted_by field."""
        tables = {t['name']: t for t in semantic_config['tables']}

        for table_name, table in tables.items():
            for column in table['columns']:
                if column.get('default_aggregation') == 'weighted_avg':
                    assert 'weighted_by' in column, \
                        f"Column {column['name']} in {table_name} has weighted_avg but no weighted_by"


class TestMetadataCompleteness:
    """Test that metadata configuration is complete and consistent."""

    @pytest.fixture
    def source_config(self):
        """Load source.yaml."""
        with open(CONFIG_DIR / "source.yaml", 'r') as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def semantic_config(self):
        """Load semantic.yaml."""
        with open(CONFIG_DIR / "semantic.yaml", 'r') as f:
            return yaml.safe_load(f)

    def test_table_names_match(self, source_config, semantic_config):
        """Test that table names match between source and semantic configs."""
        source_tables = {t['name'] for t in source_config['source']['tables']}
        semantic_tables = {t['name'] for t in semantic_config['tables']}

        assert source_tables == semantic_tables

    def test_primary_keys_match(self, source_config, semantic_config):
        """Test that primary keys match between configs."""
        source_tables = {t['name']: t for t in source_config['source']['tables']}
        semantic_tables = {t['name']: t for t in semantic_config['tables']}

        for table_name in source_tables.keys():
            assert source_tables[table_name]['primary_key'] == \
                   semantic_tables[table_name]['primary_key']

    def test_foreign_keys_reference_valid_tables(self, semantic_config):
        """Test that all foreign key relationships reference valid tables."""
        table_names = {t['name'] for t in semantic_config['tables']}

        for table in semantic_config['tables']:
            if 'relationships' in table:
                for rel in table['relationships']:
                    assert rel['target_table'] in table_names, \
                        f"Foreign key in {table['name']} references non-existent table {rel['target_table']}"

    def test_all_required_columns_are_non_nullable(self, semantic_config):
        """Test that primary keys and foreign keys are non-nullable."""
        tables = {t['name']: t for t in semantic_config['tables']}

        for table_name, table in tables.items():
            columns = {c['name']: c for c in table['columns']}

            # Primary key must be non-nullable
            pk = table['primary_key']
            assert columns[pk]['nullable'] is False, \
                f"Primary key {pk} in {table_name} is nullable"

            # Foreign keys must be non-nullable
            if 'relationships' in table:
                for rel in table['relationships']:
                    if rel['type'] == 'many_to_one':
                        fk_col = rel['join_column']
                        assert columns[fk_col]['nullable'] is False, \
                            f"Foreign key {fk_col} in {table_name} is nullable"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
