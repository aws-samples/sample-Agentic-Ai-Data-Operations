"""
Unit tests for US Mutual Funds & ETF metadata configuration files.

Tests validate YAML structure, required fields, S3 paths, column roles,
and semantic layer completeness.
"""

import pytest
import yaml
from pathlib import Path
from typing import Any, Dict, List


# Fixtures
@pytest.fixture
def workload_dir() -> Path:
    """Get the workload directory path."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def source_config(workload_dir: Path) -> Dict[str, Any]:
    """Load source.yaml configuration."""
    config_path = workload_dir / "config" / "source.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def semantic_config(workload_dir: Path) -> Dict[str, Any]:
    """Load semantic.yaml configuration."""
    config_path = workload_dir / "config" / "semantic.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


# Test source.yaml structure
class TestSourceConfig:
    """Tests for source.yaml configuration."""

    def test_required_top_level_fields(self, source_config: Dict[str, Any]):
        """Test all required top-level fields are present."""
        required_fields = [
            "source_id",
            "source_name",
            "source_type",
            "description",
            "connection",
            "tables",
            "credentials",
            "ingestion",
            "metadata"
        ]
        for field in required_fields:
            assert field in source_config, f"Missing required field: {field}"

    def test_source_id_format(self, source_config: Dict[str, Any]):
        """Test source_id follows naming convention."""
        source_id = source_config["source_id"]
        assert isinstance(source_id, str)
        assert len(source_id) > 0
        assert source_id == "us_mutual_funds_etf_synthetic"

    def test_connection_fields(self, source_config: Dict[str, Any]):
        """Test connection section has required fields."""
        connection = source_config["connection"]
        assert "type" in connection
        assert "bucket" in connection
        assert connection["type"] == "glue_pyspark_generation"
        assert connection["bucket"] == "your-datalake-bucket"

    def test_tables_list(self, source_config: Dict[str, Any]):
        """Test tables section contains expected tables."""
        tables = source_config["tables"]
        assert isinstance(tables, list)
        assert len(tables) == 3

        table_names = [t["name"] for t in tables]
        assert "raw_funds" in table_names
        assert "raw_market_data" in table_names
        assert "raw_nav_prices" in table_names

    def test_table_paths_format(self, source_config: Dict[str, Any]):
        """Test all table paths are valid S3 URIs."""
        tables = source_config["tables"]
        for table in tables:
            path = table["path"]
            assert path.startswith("s3://"), f"Invalid S3 path: {path}"
            assert path.endswith("/"), f"S3 path should end with /: {path}"

    def test_table_formats(self, source_config: Dict[str, Any]):
        """Test all tables have parquet format specified."""
        tables = source_config["tables"]
        for table in tables:
            assert table["format"] == "parquet", f"Expected parquet format for {table['name']}"

    def test_credentials_structure(self, source_config: Dict[str, Any]):
        """Test credentials section structure."""
        credentials = source_config["credentials"]
        assert "method" in credentials
        assert credentials["method"] == "iam_role"

    def test_ingestion_config(self, source_config: Dict[str, Any]):
        """Test ingestion configuration."""
        ingestion = source_config["ingestion"]
        assert "frequency" in ingestion
        assert "incremental" in ingestion
        assert ingestion["frequency"] == "one_time_generation"
        assert ingestion["incremental"] is False

    def test_metadata_fields(self, source_config: Dict[str, Any]):
        """Test metadata section has required fields."""
        metadata = source_config["metadata"]
        required_fields = ["owner", "domain", "classification", "retention_days"]
        for field in required_fields:
            assert field in metadata, f"Missing metadata field: {field}"


# Test semantic.yaml structure
class TestSemanticConfig:
    """Tests for semantic.yaml configuration."""

    def test_required_top_level_fields(self, semantic_config: Dict[str, Any]):
        """Test all required top-level fields are present."""
        required_fields = [
            "workload_name",
            "version",
            "created_at",
            "tables",
            "business_context",
            "data_stewardship"
        ]
        for field in required_fields:
            assert field in semantic_config, f"Missing required field: {field}"

    def test_workload_name(self, semantic_config: Dict[str, Any]):
        """Test workload_name matches expected value."""
        assert semantic_config["workload_name"] == "us_mutual_funds_etf"

    def test_tables_structure(self, semantic_config: Dict[str, Any]):
        """Test tables section has silver and gold zones."""
        tables = semantic_config["tables"]
        assert "silver" in tables
        assert "gold" in tables

    def test_silver_tables(self, semantic_config: Dict[str, Any]):
        """Test Silver zone tables are defined."""
        silver = semantic_config["tables"]["silver"]
        expected_tables = ["funds_clean", "market_data_clean", "nav_clean"]
        for table in expected_tables:
            assert table in silver, f"Missing Silver table: {table}"

    def test_gold_tables(self, semantic_config: Dict[str, Any]):
        """Test Gold zone tables are defined."""
        gold = semantic_config["tables"]["gold"]
        expected_tables = ["dim_fund", "dim_category", "dim_date", "fact_fund_performance"]
        for table in expected_tables:
            assert table in gold, f"Missing Gold table: {table}"

    def test_primary_keys_defined(self, semantic_config: Dict[str, Any]):
        """Test all tables have primary keys defined."""
        all_tables = {**semantic_config["tables"]["silver"], **semantic_config["tables"]["gold"]}
        for table_name, table_def in all_tables.items():
            assert "primary_key" in table_def, f"Missing primary_key for {table_name}"

    def test_column_roles_assigned(self, semantic_config: Dict[str, Any]):
        """Test all columns have role assignments."""
        all_tables = {**semantic_config["tables"]["silver"], **semantic_config["tables"]["gold"]}

        for table_name, table_def in all_tables.items():
            columns = table_def.get("columns", {})
            for col_name, col_def in columns.items():
                assert "role" in col_def, f"Missing role for {table_name}.{col_name}"
                valid_roles = ["dimension", "measure", "temporal", "identifier", "foreign_key"]
                assert col_def["role"] in valid_roles, f"Invalid role for {table_name}.{col_name}"

    def test_measure_aggregations(self, semantic_config: Dict[str, Any]):
        """Test all measure columns have default_aggregation specified."""
        all_tables = {**semantic_config["tables"]["silver"], **semantic_config["tables"]["gold"]}

        for table_name, table_def in all_tables.items():
            columns = table_def.get("columns", {})
            for col_name, col_def in columns.items():
                if col_def.get("role") == "measure":
                    assert "default_aggregation" in col_def, \
                        f"Missing default_aggregation for measure {table_name}.{col_name}"
                    valid_aggs = ["SUM", "AVG", "MIN", "MAX", "COUNT", "LAST"]
                    assert col_def["default_aggregation"] in valid_aggs, \
                        f"Invalid aggregation for {table_name}.{col_name}"

    def test_foreign_key_references(self, semantic_config: Dict[str, Any]):
        """Test foreign key columns have references defined."""
        gold = semantic_config["tables"]["gold"]

        for table_name, table_def in gold.items():
            columns = table_def.get("columns", {})
            for col_name, col_def in columns.items():
                if col_def.get("role") == "foreign_key":
                    assert "references" in col_def, \
                        f"Missing references for FK {table_name}.{col_name}"

    def test_business_context_structure(self, semantic_config: Dict[str, Any]):
        """Test business_context section has all required subsections."""
        business_context = semantic_config["business_context"]
        required_sections = [
            "fact_grain",
            "default_filters",
            "dimension_hierarchies",
            "business_terms",
            "time_intelligence",
            "seed_questions",
            "join_semantics"
        ]
        for section in required_sections:
            assert section in business_context, f"Missing business_context section: {section}"

    def test_fact_grain_defined(self, semantic_config: Dict[str, Any]):
        """Test fact_grain is clearly defined."""
        fact_grain = semantic_config["business_context"]["fact_grain"]
        assert isinstance(fact_grain, str)
        assert len(fact_grain) > 0
        assert "fund_ticker" in fact_grain.lower()
        assert "price_date" in fact_grain.lower()

    def test_default_filters(self, semantic_config: Dict[str, Any]):
        """Test default_filters are defined with required fields."""
        filters = semantic_config["business_context"]["default_filters"]
        assert isinstance(filters, list)
        assert len(filters) > 0

        for filter_def in filters:
            assert "name" in filter_def
            assert "description" in filter_def
            assert "sql_expression" in filter_def

    def test_dimension_hierarchies(self, semantic_config: Dict[str, Any]):
        """Test dimension_hierarchies are defined."""
        hierarchies = semantic_config["business_context"]["dimension_hierarchies"]
        assert isinstance(hierarchies, list)
        assert len(hierarchies) > 0

        for hierarchy in hierarchies:
            assert "name" in hierarchy
            assert "levels" in hierarchy
            assert isinstance(hierarchy["levels"], list)
            assert len(hierarchy["levels"]) > 1

    def test_business_terms(self, semantic_config: Dict[str, Any]):
        """Test business_terms are defined with all required fields."""
        terms = semantic_config["business_context"]["business_terms"]
        assert isinstance(terms, list)
        assert len(terms) >= 5  # AUM, returns, fees, risk, rating

        for term in terms:
            assert "term" in term
            assert "synonyms" in term
            assert "maps_to_column" in term
            assert "sql_expression" in term
            assert isinstance(term["synonyms"], list)

    def test_time_intelligence(self, semantic_config: Dict[str, Any]):
        """Test time_intelligence configuration."""
        time_intel = semantic_config["business_context"]["time_intelligence"]
        required_fields = ["fiscal_year_start", "data_freshness", "default_period"]
        for field in required_fields:
            assert field in time_intel, f"Missing time_intelligence field: {field}"

    def test_seed_questions(self, semantic_config: Dict[str, Any]):
        """Test seed_questions are defined with SQL hints."""
        questions = semantic_config["business_context"]["seed_questions"]
        assert isinstance(questions, list)
        assert len(questions) >= 5

        for q in questions:
            assert "question" in q
            assert "sql_hint" in q
            assert isinstance(q["question"], str)
            assert isinstance(q["sql_hint"], str)
            assert len(q["sql_hint"]) > 0

    def test_join_semantics(self, semantic_config: Dict[str, Any]):
        """Test join_semantics are defined for all key joins."""
        joins = semantic_config["business_context"]["join_semantics"]
        assert isinstance(joins, list)
        assert len(joins) >= 3  # fact_to_fund, fact_to_category, fact_to_date

        for join in joins:
            required_fields = [
                "join_name", "left_table", "right_table", "join_type",
                "join_condition", "when_to_join", "pre_aggregation_rule"
            ]
            for field in required_fields:
                assert field in join, f"Missing join_semantics field: {field}"

    def test_data_stewardship(self, semantic_config: Dict[str, Any]):
        """Test data_stewardship section."""
        stewardship = semantic_config["data_stewardship"]
        required_fields = ["owner", "domain", "contact", "last_updated"]
        for field in required_fields:
            assert field in stewardship, f"Missing data_stewardship field: {field}"


# Cross-validation tests
class TestCrossValidation:
    """Tests that validate consistency between config files."""

    def test_workload_name_consistency(self, source_config: Dict[str, Any],
                                      semantic_config: Dict[str, Any]):
        """Test workload name is consistent across configs."""
        # Extract workload name from source_id (remove _synthetic suffix)
        source_workload = source_config["source_id"].replace("_synthetic", "")
        semantic_workload = semantic_config["workload_name"]
        assert source_workload == semantic_workload, \
            f"Workload name mismatch: {source_workload} vs {semantic_workload}"

    def test_all_measures_have_business_terms(self, semantic_config: Dict[str, Any]):
        """Test key measures have business terms defined."""
        # Get all measure columns from fact table
        fact_table = semantic_config["tables"]["gold"]["fact_fund_performance"]
        measure_columns = [
            col_name for col_name, col_def in fact_table["columns"].items()
            if col_def.get("role") == "measure"
        ]

        # Get all business terms
        business_terms = semantic_config["business_context"]["business_terms"]
        mapped_columns = [term["maps_to_column"] for term in business_terms]

        # Key measures that should have business terms
        key_measures = [
            "total_assets_millions", "return_1yr_pct", "expense_ratio_pct",
            "beta", "sharpe_ratio", "morningstar_rating"
        ]

        for measure in key_measures:
            assert measure in mapped_columns, \
                f"Key measure {measure} not mapped to business term"

    def test_seed_questions_reference_valid_columns(self, semantic_config: Dict[str, Any]):
        """Test seed questions reference columns that exist."""
        # Get all available columns from gold tables
        gold = semantic_config["tables"]["gold"]
        all_columns = set()
        for table_def in gold.values():
            all_columns.update(table_def["columns"].keys())

        # Check seed questions
        questions = semantic_config["business_context"]["seed_questions"]
        for q in questions:
            sql_hint = q["sql_hint"].lower()
            # Check for common column references
            for col in ["fund_name", "fund_ticker", "sharpe_ratio", "return_1yr_pct",
                       "total_assets_millions", "expense_ratio_pct", "management_company"]:
                if col.lower() in sql_hint:
                    assert col in all_columns, \
                        f"Seed question references non-existent column: {col}"

    def test_join_semantics_reference_valid_tables(self, semantic_config: Dict[str, Any]):
        """Test join_semantics reference tables that exist."""
        gold = semantic_config["tables"]["gold"]
        table_names = set(gold.keys())

        joins = semantic_config["business_context"]["join_semantics"]
        for join in joins:
            left_table = join["left_table"]
            right_table = join["right_table"]
            assert left_table in table_names, \
                f"Join references non-existent left table: {left_table}"
            assert right_table in table_names, \
                f"Join references non-existent right table: {right_table}"

    def test_foreign_key_references_valid(self, semantic_config: Dict[str, Any]):
        """Test foreign key references point to valid tables and columns."""
        gold = semantic_config["tables"]["gold"]

        # Build a map of valid references
        valid_refs = {}
        for table_name, table_def in gold.items():
            for col_name in table_def["columns"].keys():
                valid_refs[f"{table_name}.{col_name}"] = True

        # Check all foreign key references
        for table_name, table_def in gold.items():
            columns = table_def.get("columns", {})
            for col_name, col_def in columns.items():
                if col_def.get("role") == "foreign_key":
                    ref = col_def.get("references")
                    assert ref in valid_refs, \
                        f"Foreign key {table_name}.{col_name} references invalid column: {ref}"


# Completeness tests
class TestSemanticCompleteness:
    """Tests that validate the semantic layer is complete enough for AWS Semantic Layer consumer."""

    def test_all_fact_measures_have_aggregations(self, semantic_config: Dict[str, Any]):
        """Test all fact table measures have default aggregations."""
        fact_table = semantic_config["tables"]["gold"]["fact_fund_performance"]
        columns = fact_table["columns"]

        for col_name, col_def in columns.items():
            if col_def.get("role") == "measure":
                assert "default_aggregation" in col_def, \
                    f"Fact measure {col_name} missing default_aggregation"

    def test_fact_grain_mentions_key_columns(self, semantic_config: Dict[str, Any]):
        """Test fact_grain explicitly mentions grain columns."""
        fact_grain = semantic_config["business_context"]["fact_grain"].lower()
        grain_cols = semantic_config["tables"]["gold"]["fact_fund_performance"]["grain"]

        for col in grain_cols:
            assert col.lower() in fact_grain, \
                f"Fact grain doesn't mention grain column: {col}"

    def test_has_default_filters_for_common_queries(self, semantic_config: Dict[str, Any]):
        """Test default filters handle common query patterns."""
        filters = semantic_config["business_context"]["default_filters"]
        filter_names = [f["name"] for f in filters]

        # Should have filters for current snapshot queries
        assert any("recent" in name or "current" in name for name in filter_names), \
            "Missing filter for most recent data"

    def test_seed_questions_cover_key_use_cases(self, semantic_config: Dict[str, Any]):
        """Test seed questions cover key analytical use cases."""
        questions = semantic_config["business_context"]["seed_questions"]
        question_text = " ".join([q["question"].lower() for q in questions])

        # Should cover: ranking, aggregation, comparison, filtering
        assert "top" in question_text or "highest" in question_text, \
            "No ranking queries in seed questions"
        assert "total" in question_text or "sum" in question_text or "average" in question_text, \
            "No aggregation queries in seed questions"
        assert "compare" in question_text or "vs" in question_text, \
            "No comparison queries in seed questions"

    def test_business_terms_have_units(self, semantic_config: Dict[str, Any]):
        """Test business terms specify units where applicable."""
        terms = semantic_config["business_context"]["business_terms"]

        # Terms that represent percentages or money should have units
        for term in terms:
            term_name = term["term"].lower()
            if any(word in term_name for word in ["ratio", "yield", "return", "pct", "fee"]):
                # Should have unit or note explaining the measure
                has_context = "unit" in term or "note" in term
                assert has_context, f"Business term '{term['term']}' missing unit/note"

    def test_dimension_hierarchy_is_complete(self, semantic_config: Dict[str, Any]):
        """Test dimension hierarchy covers all aggregation levels."""
        hierarchies = semantic_config["business_context"]["dimension_hierarchies"]

        # Should have at least one hierarchy with 3+ levels
        max_levels = max([len(h["levels"]) for h in hierarchies])
        assert max_levels >= 3, "Dimension hierarchy should have at least 3 levels"

        # Top level should be broad (company/category)
        org_hierarchy = next((h for h in hierarchies if h["name"] == "org_hierarchy"), None)
        assert org_hierarchy is not None, "Missing org_hierarchy"
        assert "management_company" in org_hierarchy["levels"], \
            "Org hierarchy should start with management_company"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
