"""
Integration tests for Metadata Agent configuration — stocks workload.
Tests that configurations work together and match actual sample data.
"""

import csv
import pytest
import yaml
from pathlib import Path

# Get workload and project directories
WORKLOAD_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = WORKLOAD_DIR / "config"
PROJECT_ROOT = WORKLOAD_DIR.parent.parent
SAMPLE_DATA_DIR = PROJECT_ROOT / "sample_data"


class TestConfigurationLoading:
    """Test that configuration files can be loaded and parsed."""

    def test_can_load_source_config(self):
        """Test that source.yaml can be loaded without errors."""
        source_file = CONFIG_DIR / "source.yaml"
        assert source_file.exists(), f"source.yaml not found at {source_file}"

        with open(source_file, 'r') as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert 'source' in config

    def test_can_load_semantic_config(self):
        """Test that semantic.yaml can be loaded without errors."""
        semantic_file = CONFIG_DIR / "semantic.yaml"
        assert semantic_file.exists(), f"semantic.yaml not found at {semantic_file}"

        with open(semantic_file, 'r') as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert 'tables' in config

    def test_s3_path_structure_is_valid(self):
        """Test that S3 path structure follows expected pattern."""
        with open(CONFIG_DIR / "source.yaml", 'r') as f:
            config = yaml.safe_load(f)

        location = config['source']['location']

        assert location.startswith('s3://')
        assert location.endswith('stocks/')

    def test_credentials_use_secrets_manager(self):
        """Test that credentials reference Secrets Manager, not hardcoded values."""
        with open(CONFIG_DIR / "source.yaml", 'r') as f:
            config = yaml.safe_load(f)

        role_arn = config['source']['credentials']['role_arn_secret']
        assert 'secretsmanager' in role_arn


class TestConfigConsistency:
    """Test consistency between source.yaml and semantic.yaml."""

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
        """Test that table names are identical in both configs."""
        source_tables = {t['name'] for t in source_config['source']['tables']}
        semantic_tables = {t['name'] for t in semantic_config['tables']}

        assert source_tables == semantic_tables, \
            f"Table mismatch: source={source_tables}, semantic={semantic_tables}"

    def test_primary_keys_match(self, source_config, semantic_config):
        """Test that primary keys are identical in both configs."""
        source_pk = source_config['source']['tables'][0]['primary_key']
        semantic_pk = semantic_config['tables'][0]['primary_key']

        assert source_pk == semantic_pk, \
            f"Primary key mismatch: source={source_pk}, semantic={semantic_pk}"

    def test_workload_name_consistent(self, source_config, semantic_config):
        """Test that workload name is consistent across configs."""
        assert source_config['source']['name'] == 'stocks'
        assert semantic_config['workload'] == 'stocks'

    def test_compliance_tags_consistent(self, source_config, semantic_config):
        """Test that compliance tags match between configs."""
        assert set(source_config['source']['compliance']) == set(semantic_config['compliance'])


class TestSampleDataAlignment:
    """Test that semantic.yaml columns match actual sample data CSV."""

    @pytest.fixture
    def semantic_config(self):
        """Load semantic.yaml."""
        with open(CONFIG_DIR / "semantic.yaml", 'r') as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def csv_columns(self):
        """Read column headers from sample_data/stocks.csv."""
        csv_file = SAMPLE_DATA_DIR / "stocks.csv"
        assert csv_file.exists(), f"stocks.csv not found at {csv_file}"

        with open(csv_file, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)

        return [h.strip() for h in headers]

    @pytest.fixture
    def csv_rows(self):
        """Read all rows from sample_data/stocks.csv."""
        csv_file = SAMPLE_DATA_DIR / "stocks.csv"

        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            return list(reader)

    def test_all_csv_columns_in_semantic(self, semantic_config, csv_columns):
        """Test that every column in the CSV is defined in semantic.yaml."""
        table = semantic_config['tables'][0]
        semantic_columns = {c['name'] for c in table['columns']}

        for csv_col in csv_columns:
            assert csv_col in semantic_columns, \
                f"CSV column '{csv_col}' not found in semantic.yaml"

    def test_all_semantic_columns_in_csv(self, semantic_config, csv_columns):
        """Test that every column in semantic.yaml exists in the CSV."""
        table = semantic_config['tables'][0]
        semantic_columns = [c['name'] for c in table['columns']]
        csv_column_set = set(csv_columns)

        for sem_col in semantic_columns:
            assert sem_col in csv_column_set, \
                f"Semantic column '{sem_col}' not found in CSV"

    def test_column_count_matches(self, semantic_config, csv_columns):
        """Test that column count matches between semantic.yaml and CSV."""
        table = semantic_config['tables'][0]
        assert len(table['columns']) == len(csv_columns), \
            f"Column count mismatch: semantic={len(table['columns'])}, csv={len(csv_columns)}"

    def test_row_count_matches(self, csv_rows):
        """Test that actual CSV row count matches expected."""
        assert len(csv_rows) == 50, \
            f"Expected 50 rows, got {len(csv_rows)}"

    def test_primary_key_unique_in_csv(self, csv_rows):
        """Test that ticker (primary key) is unique in sample data."""
        tickers = [row['ticker'] for row in csv_rows]
        assert len(tickers) == len(set(tickers)), \
            f"Duplicate tickers found in sample data"

    def test_primary_key_not_null_in_csv(self, csv_rows):
        """Test that ticker (primary key) has no null/empty values."""
        for row in csv_rows:
            assert row['ticker'] is not None and row['ticker'].strip() != '', \
                "Found null/empty ticker in sample data"

    def test_exchange_values_match_csv(self, csv_rows):
        """Test that exchange values in CSV match expected (NASDAQ, NYSE)."""
        exchanges = {row['exchange'] for row in csv_rows}
        assert exchanges <= {'NASDAQ', 'NYSE'}, \
            f"Unexpected exchanges: {exchanges - {'NASDAQ', 'NYSE'}}"


class TestSchemaValidation:
    """Test that schema definitions are valid."""

    @pytest.fixture
    def semantic_config(self):
        """Load semantic.yaml."""
        with open(CONFIG_DIR / "semantic.yaml", 'r') as f:
            return yaml.safe_load(f)

    def test_all_column_types_are_valid(self, semantic_config):
        """Test that all column data types are valid SQL types."""
        valid_base_types = {'string', 'integer', 'date', 'timestamp', 'boolean'}

        for table in semantic_config['tables']:
            for column in table['columns']:
                col_type = column['type']
                if col_type.startswith('decimal'):
                    # Decimal types: decimal(p,s) format
                    assert col_type.startswith('decimal(') and col_type.endswith(')'), \
                        f"Invalid decimal type: {col_type}"
                else:
                    assert col_type in valid_base_types, \
                        f"Invalid column type: {col_type} for {column['name']}"


class TestGDPRCompliance:
    """Test GDPR-specific configuration requirements."""

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

    def test_gdpr_metadata_columns_defined(self, semantic_config):
        """Test that GDPR metadata columns are defined for Silver/Gold."""
        table = semantic_config['tables'][0]
        assert 'gdpr_metadata_columns' in table

        gdpr_cols = {c['name'] for c in table['gdpr_metadata_columns']}

        required = {'consent_given', 'consent_timestamp', 'is_deleted',
                   'deletion_requested_at', 'data_subject_id'}

        for col in required:
            assert col in gdpr_cols, f"Missing GDPR metadata column: {col}"

    def test_gdpr_encryption_key_alias(self, source_config):
        """Test that GDPR KMS key alias follows naming convention."""
        kms_alias = source_config['source']['encryption']['kms_key_alias']
        assert kms_alias == 'alias/stocks-gdpr-key'

    def test_data_retention_365_days(self, source_config):
        """Test GDPR data retention is 365 days."""
        assert source_config['source']['retention_days'] == 365

    def test_audit_log_retention_7_years(self, source_config):
        """Test GDPR audit log retention is 2555 days (7 years)."""
        assert source_config['source']['audit_log_retention_days'] == 2555

    def test_all_columns_low_sensitivity(self, semantic_config):
        """Test that data sensitivity is LOW (no PII in public market data)."""
        sensitivity = semantic_config['data_sensitivity']
        assert sensitivity['overall'] == 'LOW'
        assert sensitivity['pii_detected'] is False

    def test_lf_tags_configured(self, semantic_config):
        """Test that Lake Formation tags are configured for GDPR."""
        lf_tags = semantic_config['data_sensitivity']['lf_tags']
        assert lf_tags['Data_Sensitivity'] == 'LOW'
        assert lf_tags['PII_Classification'] == 'NONE'

    def test_gdpr_soft_delete_filter_exists(self, semantic_config):
        """Test that a GDPR soft-delete filter is defined."""
        filters = semantic_config['default_filters']
        gdpr_filters = [f for f in filters if 'gdpr' in f['name'].lower() or 'deleted' in f['name'].lower()]
        assert len(gdpr_filters) >= 1, "Missing GDPR soft-delete filter"

    def test_compliance_owner_is_dpo(self, semantic_config):
        """Test that compliance owner is Data Protection Officer (GDPR)."""
        stewardship = semantic_config['data_stewardship']
        assert 'compliance_owner' in stewardship
        assert 'GDPR' in stewardship['compliance_owner'] or 'DPO' in stewardship['compliance_owner']


class TestSeedQuestions:
    """Test that seed questions are valid for single-table workload."""

    @pytest.fixture
    def semantic_config(self):
        """Load semantic.yaml."""
        with open(CONFIG_DIR / "semantic.yaml", 'r') as f:
            return yaml.safe_load(f)

    def test_seed_questions_have_valid_sql(self, semantic_config):
        """Test that seed questions have valid SQL structure."""
        seed_questions = semantic_config['seed_questions']

        for question in seed_questions:
            sql = question['sql'].upper()
            assert 'SELECT' in sql, f"Missing SELECT: {question['question']}"
            assert 'FROM' in sql, f"Missing FROM: {question['question']}"

    def test_seed_questions_single_table_only(self, semantic_config):
        """Test that seed questions only reference the stocks table (no JOINs)."""
        seed_questions = semantic_config['seed_questions']

        for question in seed_questions:
            sql_upper = question['sql'].upper()
            assert 'STOCKS' in sql_upper, \
                f"Seed question should reference stocks table: {question['question']}"
            # Single-table workload should not have JOINs in seed questions
            assert 'JOIN' not in sql_upper, \
                f"Single-table workload should not have JOINs in seed questions: {question['question']}"

    def test_seed_questions_have_explanations(self, semantic_config):
        """Test that all seed questions have explanations."""
        for question in semantic_config['seed_questions']:
            assert question['explanation'] is not None and len(question['explanation']) > 10


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
