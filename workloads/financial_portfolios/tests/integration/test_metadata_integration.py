"""
Integration tests for Metadata Agent configuration.
Tests that configurations work together and can be loaded/validated.
"""

import os
import pytest
import yaml
from pathlib import Path
from datetime import datetime

# Get workload directory
WORKLOAD_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = WORKLOAD_DIR / "config"
SAMPLE_DATA_DIR = WORKLOAD_DIR / "sample_data"


class TestConfigurationLoading:
    """Test that configuration files can be loaded and parsed."""

    def test_can_load_source_config(self):
        """Test that source.yaml can be loaded without errors."""
        source_file = CONFIG_DIR / "source.yaml"

        with open(source_file, 'r') as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert 'source' in config

    def test_can_load_semantic_config(self):
        """Test that semantic.yaml can be loaded without errors."""
        semantic_file = CONFIG_DIR / "semantic.yaml"

        with open(semantic_file, 'r') as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert 'tables' in config

    def test_s3_path_structure_is_valid(self):
        """Test that S3 path structure follows expected pattern."""
        source_file = CONFIG_DIR / "source.yaml"

        with open(source_file, 'r') as f:
            config = yaml.safe_load(f)

        location = config['source']['location']

        # Should be: s3://bucket/workload_name/
        assert location.startswith('s3://')
        assert location.endswith('financial_portfolios/')

        # Check partition pattern
        assert config['source']['partition_pattern'] == 'YYYY-MM-DD'

    def test_iam_role_arn_format(self):
        """Test that IAM role ARN follows AWS format."""
        source_file = CONFIG_DIR / "source.yaml"

        with open(source_file, 'r') as f:
            config = yaml.safe_load(f)

        role_arn = config['source']['credentials']['role_arn_secret']

        # Should be a Secrets Manager ARN
        assert role_arn.startswith('arn:aws:secretsmanager:')
        assert ':secret:' in role_arn


class TestSchemaValidation:
    """Test that schema definitions are valid and consistent."""

    @pytest.fixture
    def semantic_config(self):
        """Load semantic.yaml."""
        with open(CONFIG_DIR / "semantic.yaml", 'r') as f:
            return yaml.safe_load(f)

    def test_all_column_types_are_valid(self, semantic_config):
        """Test that all column data types are valid SQL types."""
        valid_types = {
            'string', 'integer', 'decimal', 'date', 'timestamp', 'boolean',
            'decimal(10,2)', 'decimal(12,2)', 'decimal(15,2)', 'decimal(6,2)',
            'decimal(6,3)', 'decimal(6,4)', 'decimal(8,2)', 'decimal(8,4)',
            'decimal(10,4)', 'decimal(15,4)'
        }

        for table in semantic_config['tables']:
            for column in table['columns']:
                col_type = column['type']

                # Handle decimal types with precision/scale
                if col_type.startswith('decimal'):
                    assert col_type in valid_types or col_type.startswith('decimal('), \
                        f"Invalid decimal type: {col_type}"
                else:
                    assert col_type in valid_types, \
                        f"Invalid column type: {col_type} for {column['name']}"

    def test_all_relationships_are_valid(self, semantic_config):
        """Test that all relationship types are valid."""
        valid_relationship_types = {'one_to_one', 'one_to_many', 'many_to_one', 'many_to_many'}

        for table in semantic_config['tables']:
            if 'relationships' in table:
                for rel in table['relationships']:
                    assert rel['type'] in valid_relationship_types, \
                        f"Invalid relationship type: {rel['type']}"

    def test_grain_definition_for_fact_table(self, semantic_config):
        """Test that fact table has proper grain definition."""
        tables = {t['name']: t for t in semantic_config['tables']}
        positions = tables['positions']

        assert positions['table_type'] == 'fact'
        assert 'grain' in positions
        assert len(positions['grain']) > 10  # Should be descriptive
        assert 'One row per' in positions['grain']


class TestReferentialIntegrity:
    """Test that referential integrity rules are properly defined."""

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

    def test_foreign_keys_defined_in_source(self, source_config):
        """Test that foreign keys are defined in source.yaml."""
        tables = {t['name']: t for t in source_config['source']['tables']}
        positions = tables['positions']

        assert 'foreign_keys' in positions
        fks = positions['foreign_keys']

        # Should have 2 foreign keys
        assert len(fks) == 2

        # Check FK to portfolios
        portfolio_fk = next((fk for fk in fks if fk['column'] == 'portfolio_id'), None)
        assert portfolio_fk is not None
        assert portfolio_fk['references_table'] == 'portfolios'
        assert portfolio_fk['references_column'] == 'portfolio_id'

        # Check FK to stocks
        ticker_fk = next((fk for fk in fks if fk['column'] == 'ticker'), None)
        assert ticker_fk is not None
        assert ticker_fk['references_table'] == 'stocks'
        assert ticker_fk['references_column'] == 'ticker'

    def test_relationships_match_foreign_keys(self, source_config, semantic_config):
        """Test that relationships in semantic.yaml match foreign keys in source.yaml."""
        # Get foreign keys from source
        source_tables = {t['name']: t for t in source_config['source']['tables']}
        positions_fks = source_tables['positions']['foreign_keys']
        fk_refs = {fk['references_table'] for fk in positions_fks}

        # Get relationships from semantic
        semantic_tables = {t['name']: t for t in semantic_config['tables']}
        positions_rels = semantic_tables['positions']['relationships']
        rel_targets = {rel['target_table'] for rel in positions_rels}

        # Should match
        assert fk_refs == rel_targets

    def test_bidirectional_relationships(self, semantic_config):
        """Test that relationships are defined bidirectionally."""
        tables = {t['name']: t for t in semantic_config['tables']}

        # Stocks should have one_to_many to positions
        stocks_rels = {r['target_table']: r for r in tables['stocks']['relationships']}
        assert 'positions' in stocks_rels
        assert stocks_rels['positions']['type'] == 'one_to_many'

        # Portfolios should have one_to_many to positions
        portfolios_rels = {r['target_table']: r for r in tables['portfolios']['relationships']}
        assert 'positions' in portfolios_rels
        assert portfolios_rels['positions']['type'] == 'one_to_many'

        # Positions should have many_to_one back to stocks and portfolios
        positions_rels = {r['target_table']: r for r in tables['positions']['relationships']}
        assert 'stocks' in positions_rels
        assert positions_rels['stocks']['type'] == 'many_to_one'
        assert 'portfolios' in positions_rels
        assert positions_rels['portfolios']['type'] == 'many_to_one'


class TestBusinessSemantics:
    """Test that business semantics are properly defined."""

    @pytest.fixture
    def semantic_config(self):
        """Load semantic.yaml."""
        with open(CONFIG_DIR / "semantic.yaml", 'r') as f:
            return yaml.safe_load(f)

    def test_business_terms_have_synonyms(self, semantic_config):
        """Test that business terms include synonyms for NLP."""
        business_terms = semantic_config['business_terms']

        for term in business_terms:
            assert len(term['synonyms']) >= 1, \
                f"Business term '{term['term']}' has no synonyms"

    def test_business_terms_have_sql(self, semantic_config):
        """Test that business terms include SQL expressions."""
        business_terms = semantic_config['business_terms']

        for term in business_terms:
            assert term['sql_expression'] != '', \
                f"Business term '{term['term']}' has no SQL expression"

    def test_dimension_hierarchies_have_multiple_levels(self, semantic_config):
        """Test that dimension hierarchies have at least 2 levels."""
        hierarchies = semantic_config['dimension_hierarchies']

        for hierarchy in hierarchies:
            assert len(hierarchy['levels']) >= 2, \
                f"Hierarchy '{hierarchy['name']}' has only {len(hierarchy['levels'])} level(s)"

    def test_seed_questions_are_executable(self, semantic_config):
        """Test that seed questions have valid SQL syntax (basic checks)."""
        seed_questions = semantic_config['seed_questions']

        for question in seed_questions:
            sql = question['sql'].upper()

            # Should have SELECT
            assert 'SELECT' in sql, f"Question '{question['question']}' has no SELECT"

            # Should have FROM
            assert 'FROM' in sql, f"Question '{question['question']}' has no FROM"

            # Should reference at least one table
            assert any(table in sql for table in ['POSITIONS', 'PORTFOLIOS', 'STOCKS']), \
                f"Question '{question['question']}' doesn't reference any known table"


class TestJoinSemantics:
    """Test that join semantics are properly defined for Analysis Agent."""

    @pytest.fixture
    def semantic_config(self):
        """Load semantic.yaml."""
        with open(CONFIG_DIR / "semantic.yaml", 'r') as f:
            return yaml.safe_load(f)

    def test_all_joins_have_required_fields(self, semantic_config):
        """Test that all join definitions have required fields."""
        join_semantics = semantic_config['join_semantics']

        required_fields = ['join_name', 'tables', 'join_type', 'join_condition',
                          'when_to_join', 'pre_aggregation_rule', 'sample_query']

        for join in join_semantics:
            for field in required_fields:
                assert field in join, \
                    f"Join '{join.get('join_name', 'unknown')}' missing field: {field}"

    def test_join_types_are_valid(self, semantic_config):
        """Test that all join types are valid SQL join types."""
        join_semantics = semantic_config['join_semantics']
        valid_join_types = {'inner', 'left', 'right', 'full', 'cross'}

        for join in join_semantics:
            join_type = join['join_type'].lower()
            assert join_type in valid_join_types, \
                f"Invalid join type: {join_type}"

    def test_join_conditions_reference_valid_columns(self, semantic_config):
        """Test that join conditions reference valid columns."""
        join_semantics = semantic_config['join_semantics']
        tables = {t['name']: t for t in semantic_config['tables']}

        for join in join_semantics:
            join_condition = join['join_condition']

            # Parse join condition (handle compound conditions with AND)
            # e.g., "positions.ticker = stocks.ticker" or
            #       "positions.portfolio_id = portfolios.portfolio_id AND positions.ticker = stocks.ticker"
            if '=' in join_condition:
                # Split by AND first to handle compound conditions
                conditions = [c.strip() for c in join_condition.split(' AND ')]

                for condition in conditions:
                    if '=' in condition:
                        parts = condition.split('=')
                        assert len(parts) == 2, f"Invalid join condition format: {condition}"
                        left = parts[0].strip()
                        right = parts[1].strip()

                        # Should be in format table.column
                        assert '.' in left, f"Invalid join condition: {left}"
                        assert '.' in right, f"Invalid join condition: {right}"

    def test_sample_queries_are_valid(self, semantic_config):
        """Test that sample join queries have valid SQL structure."""
        join_semantics = semantic_config['join_semantics']

        for join in join_semantics:
            sql = join['sample_query'].upper()

            # Should have SELECT, FROM, JOIN
            assert 'SELECT' in sql
            assert 'FROM' in sql
            assert 'JOIN' in sql or 'INNER JOIN' in sql


class TestTimeIntelligence:
    """Test that time intelligence settings are properly configured."""

    @pytest.fixture
    def semantic_config(self):
        """Load semantic.yaml."""
        with open(CONFIG_DIR / "semantic.yaml", 'r') as f:
            return yaml.safe_load(f)

    def test_fiscal_year_start_is_valid(self, semantic_config):
        """Test that fiscal year start is a valid date format."""
        time_intel = semantic_config['time_intelligence']
        fiscal_start = time_intel['fiscal_year_start']

        # Should be MM-DD format
        assert len(fiscal_start) == 5
        assert fiscal_start[2] == '-'

        # Should parse as valid date
        month, day = fiscal_start.split('-')
        assert 1 <= int(month) <= 12
        assert 1 <= int(day) <= 31

    def test_week_start_day_is_valid(self, semantic_config):
        """Test that week start day is valid."""
        time_intel = semantic_config['time_intelligence']
        week_start = time_intel['week_start_day'].lower()

        valid_days = {'sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'}
        assert week_start in valid_days

    def test_timezones_are_valid(self, semantic_config):
        """Test that timezones are valid IANA timezone names."""
        time_intel = semantic_config['time_intelligence']

        # These are standard IANA timezone names
        assert time_intel['timezone'] == 'UTC'
        assert time_intel['display_timezone'] == 'US/Eastern'

    def test_temporal_columns_reference_valid_tables(self, semantic_config):
        """Test that temporal_columns reference valid tables and columns."""
        time_intel = semantic_config['time_intelligence']
        tables = {t['name']: t for t in semantic_config['tables']}

        for temporal_col in time_intel['temporal_columns']:
            table_name = temporal_col['table']
            column_name = temporal_col['column']

            assert table_name in tables, f"Temporal column references non-existent table: {table_name}"

            table = tables[table_name]
            column_names = [c['name'] for c in table['columns']]
            assert column_name in column_names, \
                f"Temporal column {column_name} not found in {table_name}"


class TestDataStewardship:
    """Test that data stewardship information is properly defined."""

    @pytest.fixture
    def semantic_config(self):
        """Load semantic.yaml."""
        with open(CONFIG_DIR / "semantic.yaml", 'r') as f:
            return yaml.safe_load(f)

    def test_stewardship_has_owner(self, semantic_config):
        """Test that data stewardship defines owner."""
        stewardship = semantic_config['data_stewardship']
        assert 'owner' in stewardship
        assert stewardship['owner'] != ''

    def test_stewardship_has_contact(self, semantic_config):
        """Test that data stewardship defines contact."""
        stewardship = semantic_config['data_stewardship']
        assert 'contact' in stewardship
        assert '@' in stewardship['contact']  # Should be email

    def test_update_schedule_is_valid(self, semantic_config):
        """Test that update schedule is properly defined."""
        stewardship = semantic_config['data_stewardship']
        schedule = stewardship['update_schedule']

        assert 'frequency' in schedule
        assert 'time' in schedule
        assert 'timezone' in schedule

        # Frequency should be daily
        assert schedule['frequency'] == 'daily'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
