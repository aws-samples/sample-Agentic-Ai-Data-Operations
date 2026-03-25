"""
Unit tests for Metadata Agent configuration files — stocks workload.
Tests that source.yaml and semantic.yaml are valid and complete.
Single-table, ad-hoc analytics, GDPR compliance, no PII.
"""

import pytest
import yaml
from pathlib import Path

# Get workload directory
WORKLOAD_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = WORKLOAD_DIR / "config"

# Expected profiling data — single table
EXPECTED_TABLE = {
    "name": "stocks",
    "row_count": 50,
    "column_count": 14,
    "primary_key": "ticker",
    "columns": [
        "ticker", "company_name", "sector", "industry", "exchange",
        "market_cap_billions", "current_price", "price_52w_high", "price_52w_low",
        "pe_ratio", "dividend_yield", "beta", "avg_volume_millions", "listing_date"
    ]
}

# Column role assignments
COLUMN_ROLES = {
    "ticker": "identifier",
    "company_name": "dimension",
    "sector": "dimension",
    "industry": "dimension",
    "exchange": "dimension",
    "market_cap_billions": "measure",
    "current_price": "measure",
    "price_52w_high": "measure",
    "price_52w_low": "measure",
    "pe_ratio": "measure",
    "dividend_yield": "measure",
    "beta": "measure",
    "avg_volume_millions": "measure",
    "listing_date": "temporal",
}

MEASURES = [
    "market_cap_billions", "current_price", "price_52w_high", "price_52w_low",
    "pe_ratio", "dividend_yield", "beta", "avg_volume_millions"
]


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
        assert source_config['source']['name'] == 'stocks'

    def test_source_type_is_s3(self, source_config):
        """Test that source type is S3 and format is CSV."""
        assert source_config['source']['type'] == 's3'
        assert source_config['source']['format'] == 'csv'

    def test_source_location_uses_variable(self, source_config):
        """Test that S3 location uses variable substitution (no hardcoded bucket)."""
        location = source_config['source']['location']
        assert location.startswith('s3://')
        assert 'stocks' in location
        # Must NOT contain hardcoded bucket names or account IDs
        assert '133661573128' not in location

    def test_credentials_reference_secrets_manager(self, source_config):
        """Test that credentials reference AWS Secrets Manager."""
        creds = source_config['source']['credentials']
        assert creds['type'] == 'iam_role'
        assert 'role_arn_secret' in creds
        assert 'secretsmanager' in creds['role_arn_secret']

    def test_single_table_defined(self, source_config):
        """Test that exactly one table is defined (single-table workload)."""
        tables = source_config['source']['tables']
        assert len(tables) == 1
        assert tables[0]['name'] == 'stocks'

    def test_table_primary_key(self, source_config):
        """Test that the table has correct primary key."""
        table = source_config['source']['tables'][0]
        assert table['primary_key'] == 'ticker'

    def test_no_foreign_keys(self, source_config):
        """Test that single-table workload has no foreign keys."""
        table = source_config['source']['tables'][0]
        assert 'foreign_keys' not in table

    def test_row_count_expected(self, source_config):
        """Test that expected row count is defined."""
        table = source_config['source']['tables'][0]
        assert table['row_count_expected'] == 50

    def test_frequency_is_monthly(self, source_config):
        """Test that update frequency is monthly."""
        assert source_config['source']['frequency'] == 'monthly'

    def test_gdpr_compliance_tag(self, source_config):
        """Test that GDPR compliance is specified."""
        compliance = source_config['source']['compliance']
        assert 'GDPR' in compliance

    def test_gdpr_retention_policy(self, source_config):
        """Test that retention policy follows GDPR defaults (365 days)."""
        source = source_config['source']
        assert source['retention_days'] == 365

    def test_audit_log_retention(self, source_config):
        """Test that audit log retention is 2555 days (7 years) per GDPR."""
        source = source_config['source']
        assert source['audit_log_retention_days'] == 2555

    def test_encryption_configured(self, source_config):
        """Test that GDPR encryption settings are present."""
        encryption = source_config['source']['encryption']
        assert encryption['kms_key_alias'] == 'alias/stocks-gdpr-key'
        assert encryption['at_rest'] == 'AES-256'
        assert encryption['in_transit'] == 'TLS-1.3'

    def test_csv_options(self, source_config):
        """Test that CSV options are defined."""
        csv_opts = source_config['source']['csv_options']
        assert csv_opts['delimiter'] == ','
        assert csv_opts['header'] is True
        assert csv_opts['encoding'] == 'utf-8'

    def test_quality_expectations(self, source_config):
        """Test that quality expectations include PK uniqueness."""
        expectations = source_config['source']['quality_expectations']
        assert 'no_duplicate_primary_keys' in expectations
        assert 'no_null_in_required_fields' in expectations


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

    @pytest.fixture
    def stocks_table(self, semantic_config):
        """Get the stocks table definition."""
        tables = semantic_config['tables']
        assert len(tables) == 1
        return tables[0]

    @pytest.fixture
    def columns_by_name(self, stocks_table):
        """Get columns indexed by name."""
        return {c['name']: c for c in stocks_table['columns']}

    def test_semantic_yaml_is_valid(self, semantic_config):
        """Test that semantic.yaml is valid YAML."""
        assert semantic_config is not None
        assert isinstance(semantic_config, dict)

    def test_semantic_has_required_sections(self, semantic_config):
        """Test that semantic.yaml contains all required sections."""
        required_sections = ['workload', 'domain', 'use_case', 'schema_format',
                            'tables', 'business_terms', 'dimension_hierarchies',
                            'default_filters', 'time_intelligence', 'seed_questions',
                            'data_stewardship']
        for section in required_sections:
            assert section in semantic_config, f"Missing required section: {section}"

    def test_workload_name_matches(self, semantic_config):
        """Test that workload name matches."""
        assert semantic_config['workload'] == 'stocks'

    def test_domain_is_finance(self, semantic_config):
        """Test that domain is finance."""
        assert semantic_config['domain'] == 'finance'

    def test_use_case_is_ad_hoc_analytics(self, semantic_config):
        """Test that use case is ad-hoc analytics (not reporting/dashboards)."""
        assert semantic_config['use_case'] == 'ad_hoc_analytics'
        assert semantic_config['schema_format'] == 'flat_denormalized'

    def test_gdpr_compliance_tag(self, semantic_config):
        """Test that GDPR compliance tag is present."""
        assert 'GDPR' in semantic_config['compliance']

    def test_single_table_defined(self, semantic_config):
        """Test that exactly one table is defined."""
        tables = semantic_config['tables']
        assert len(tables) == 1
        assert tables[0]['name'] == 'stocks'

    def test_table_type_is_flat(self, stocks_table):
        """Test that table type is flat (not dimension/fact — single table workload)."""
        assert stocks_table['table_type'] == 'flat'

    def test_primary_key_is_ticker(self, stocks_table):
        """Test that primary key is ticker."""
        assert stocks_table['primary_key'] == 'ticker'

    def test_grain_defined(self, stocks_table):
        """Test that grain is defined."""
        assert 'grain' in stocks_table
        assert 'One row per' in stocks_table['grain']
        assert 'ticker' in stocks_table['grain'].lower()

    def test_all_14_columns_present(self, stocks_table):
        """Test that all 14 columns from profiling are present."""
        actual_columns = [c['name'] for c in stocks_table['columns']]
        assert len(actual_columns) == 14
        assert set(actual_columns) == set(EXPECTED_TABLE['columns'])

    def test_all_columns_have_required_attributes(self, columns_by_name):
        """Test that every column has: name, type, role, nullable, description, pii_classification."""
        required_attrs = ['name', 'type', 'role', 'nullable', 'description', 'pii_classification']

        for col_name, column in columns_by_name.items():
            for attr in required_attrs:
                assert attr in column, \
                    f"Column '{col_name}' missing required attribute: {attr}"

    def test_all_column_roles_correct(self, columns_by_name):
        """Test that all columns have the correct role assignment."""
        for col_name, expected_role in COLUMN_ROLES.items():
            assert col_name in columns_by_name, f"Column '{col_name}' not found"
            actual_role = columns_by_name[col_name]['role']
            assert actual_role == expected_role, \
                f"Column '{col_name}': expected role '{expected_role}', got '{actual_role}'"

    def test_valid_roles_only(self, columns_by_name):
        """Test that all columns use valid role values."""
        valid_roles = {'identifier', 'measure', 'dimension', 'temporal'}
        for col_name, column in columns_by_name.items():
            assert column['role'] in valid_roles, \
                f"Invalid role '{column['role']}' for column '{col_name}'"

    def test_no_pii_detected(self, columns_by_name):
        """Test that all columns have pii_classification = null (no PII in public market data)."""
        for col_name, column in columns_by_name.items():
            assert column['pii_classification'] is None, \
                f"Column '{col_name}' should have pii_classification=null, got {column['pii_classification']}"

    def test_all_measures_have_aggregation(self, columns_by_name):
        """Test that all measure columns have default_aggregation defined."""
        valid_aggs = {'sum', 'avg', 'count', 'count_distinct', 'min', 'max', 'weighted_avg'}

        for measure_name in MEASURES:
            column = columns_by_name[measure_name]
            assert column['role'] == 'measure', \
                f"Expected '{measure_name}' to be a measure"
            assert 'default_aggregation' in column, \
                f"Measure '{measure_name}' missing default_aggregation"
            assert column['default_aggregation'] in valid_aggs, \
                f"Invalid aggregation '{column['default_aggregation']}' for '{measure_name}'"

    def test_temporal_column_has_date_format(self, columns_by_name):
        """Test that listing_date (temporal column) has date_format."""
        listing_date = columns_by_name['listing_date']
        assert listing_date['role'] == 'temporal'
        assert 'date_format' in listing_date
        assert listing_date['date_format'] == 'YYYY-MM-DD'

    def test_no_relationships_single_table(self, stocks_table):
        """Test that single-table workload has no relationships section."""
        # A single-table workload should not define inter-table relationships
        assert 'relationships' not in stocks_table or stocks_table.get('relationships') is None

    def test_no_join_semantics_single_table(self, semantic_config):
        """Test that single-table workload does not require join_semantics."""
        # join_semantics is optional for single-table workloads
        if 'join_semantics' in semantic_config:
            assert semantic_config['join_semantics'] is None or \
                len(semantic_config['join_semantics']) == 0

    def test_gdpr_metadata_columns_defined(self, stocks_table):
        """Test that GDPR metadata columns are defined for Silver/Gold."""
        assert 'gdpr_metadata_columns' in stocks_table

        gdpr_cols = stocks_table['gdpr_metadata_columns']
        gdpr_col_names = [c['name'] for c in gdpr_cols]

        expected_gdpr_cols = [
            'consent_given', 'consent_timestamp', 'is_deleted',
            'deletion_requested_at', 'data_subject_id'
        ]
        for col_name in expected_gdpr_cols:
            assert col_name in gdpr_col_names, \
                f"Missing GDPR metadata column: {col_name}"

    def test_business_terms_defined(self, semantic_config):
        """Test that business terms and synonyms are defined."""
        business_terms = semantic_config['business_terms']
        assert len(business_terms) >= 3

        for term in business_terms:
            assert 'term' in term
            assert 'synonyms' in term
            assert len(term['synonyms']) >= 1
            assert 'sql_expression' in term
            assert 'description' in term

    def test_dimension_hierarchies_defined(self, semantic_config):
        """Test that dimension hierarchies are defined."""
        hierarchies = semantic_config['dimension_hierarchies']
        assert len(hierarchies) >= 1

        hierarchy_names = {h['name'] for h in hierarchies}
        assert 'equity_classification' in hierarchy_names

        # Check hierarchy structure
        for hierarchy in hierarchies:
            assert 'levels' in hierarchy
            assert len(hierarchy['levels']) >= 2

    def test_equity_classification_hierarchy(self, semantic_config):
        """Test the sector -> industry -> ticker hierarchy."""
        hierarchies = {h['name']: h for h in semantic_config['dimension_hierarchies']}
        equity = hierarchies['equity_classification']

        levels = {l['name']: l for l in equity['levels']}
        assert 'sector' in levels
        assert 'industry' in levels
        assert 'ticker' in levels

        # Verify order: sector (1) -> industry (2) -> ticker (3)
        level_map = {l['name']: l['level'] for l in equity['levels']}
        assert level_map['sector'] < level_map['industry'] < level_map['ticker']

    def test_default_filters_defined(self, semantic_config):
        """Test that default filters are defined."""
        filters = semantic_config['default_filters']
        assert len(filters) >= 2

        for filter_def in filters:
            assert 'name' in filter_def
            assert 'filter' in filter_def
            assert 'applies_to_tables' in filter_def

    def test_gdpr_soft_delete_filter(self, semantic_config):
        """Test that a GDPR soft-delete filter is defined."""
        filters = semantic_config['default_filters']
        filter_names = [f['name'] for f in filters]
        assert 'gdpr_not_deleted' in filter_names

    def test_time_intelligence_defined(self, semantic_config):
        """Test that time intelligence settings are defined."""
        time_intel = semantic_config['time_intelligence']

        assert time_intel['fiscal_year_start'] == '01-01'
        assert time_intel['week_start_day'] == 'sunday'
        assert time_intel['timezone'] == 'UTC'
        assert time_intel['display_timezone'] == 'US/Eastern'

        assert 'temporal_columns' in time_intel
        assert len(time_intel['temporal_columns']) >= 1

    def test_seed_questions_defined(self, semantic_config):
        """Test that seed questions are defined."""
        seed_questions = semantic_config['seed_questions']
        assert len(seed_questions) >= 5

        for question in seed_questions:
            assert 'question' in question
            assert 'sql' in question
            assert 'explanation' in question

    def test_seed_questions_reference_stocks_table(self, semantic_config):
        """Test that seed questions reference the stocks table (single table workload)."""
        seed_questions = semantic_config['seed_questions']

        for question in seed_questions:
            sql_upper = question['sql'].upper()
            assert 'STOCKS' in sql_upper, \
                f"Seed question SQL should reference 'stocks' table: {question['question']}"

    def test_data_stewardship_defined(self, semantic_config):
        """Test that data stewardship information is defined."""
        stewardship = semantic_config['data_stewardship']

        assert 'owner' in stewardship
        assert 'steward' in stewardship
        assert 'contact' in stewardship
        assert '@' in stewardship['contact']
        assert 'update_schedule' in stewardship

    def test_update_schedule_is_monthly(self, semantic_config):
        """Test that update schedule frequency is monthly."""
        schedule = semantic_config['data_stewardship']['update_schedule']
        assert schedule['frequency'] == 'monthly'

    def test_data_sensitivity_summary(self, semantic_config):
        """Test that data sensitivity summary is defined."""
        assert 'data_sensitivity' in semantic_config
        sensitivity = semantic_config['data_sensitivity']

        assert sensitivity['overall'] == 'LOW'
        assert sensitivity['pii_detected'] is False
        assert sensitivity['lf_tags']['Data_Sensitivity'] == 'LOW'
        assert sensitivity['lf_tags']['PII_Classification'] == 'NONE'


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
        source_table = source_config['source']['tables'][0]
        semantic_table = semantic_config['tables'][0]

        assert source_table['primary_key'] == semantic_table['primary_key']

    def test_compliance_tags_match(self, source_config, semantic_config):
        """Test that compliance tags match between configs."""
        source_compliance = set(source_config['source']['compliance'])
        semantic_compliance = set(semantic_config['compliance'])

        assert source_compliance == semantic_compliance

    def test_all_required_columns_are_non_nullable(self, semantic_config):
        """Test that primary key is non-nullable."""
        table = semantic_config['tables'][0]
        columns = {c['name']: c for c in table['columns']}

        pk = table['primary_key']
        assert columns[pk]['nullable'] is False, \
            f"Primary key {pk} is nullable"

    def test_column_count_matches(self, semantic_config):
        """Test that column count matches expected."""
        table = semantic_config['tables'][0]
        assert len(table['columns']) == EXPECTED_TABLE['column_count']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
