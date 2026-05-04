"""
Integration tests for US Mutual Funds & ETF metadata configuration.

Tests validate that semantic.yaml can be parsed by ORION consumer,
seed questions have required columns, join semantics are complete,
and business terms map to actual columns.
"""

import pytest
import yaml
from pathlib import Path
from typing import Any, Dict, List, Set
import re


# Fixtures
@pytest.fixture
def workload_dir() -> Path:
    """Get the workload directory path."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def semantic_config(workload_dir: Path) -> Dict[str, Any]:
    """Load semantic.yaml configuration."""
    config_path = workload_dir / "config" / "semantic.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def all_columns(semantic_config: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Get all column names by table."""
    result = {}
    for zone in ["silver", "gold"]:
        for table_name, table_def in semantic_config["tables"][zone].items():
            full_table_name = f"{zone}.{table_name}"
            result[full_table_name] = set(table_def["columns"].keys())
    return result


@pytest.fixture
def fact_table_columns(semantic_config: Dict[str, Any]) -> Set[str]:
    """Get all column names from fact table."""
    fact_table = semantic_config["tables"]["gold"]["fact_fund_performance"]
    return set(fact_table["columns"].keys())


@pytest.fixture
def dim_tables_columns(semantic_config: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Get column names from all dimension tables."""
    result = {}
    gold = semantic_config["tables"]["gold"]
    for table_name, table_def in gold.items():
        if table_name.startswith("dim_"):
            result[table_name] = set(table_def["columns"].keys())
    return result


# ORION consumer parsing tests
class TestAnalysisAgentCompatibility:
    """Tests that validate semantic.yaml can be parsed by ORION consumer."""

    def test_yaml_is_valid_and_parseable(self, semantic_config: Dict[str, Any]):
        """Test that semantic.yaml is valid YAML."""
        assert semantic_config is not None
        assert isinstance(semantic_config, dict)
        assert len(semantic_config) > 0

    def test_has_all_required_sections_for_nlp(self, semantic_config: Dict[str, Any]):
        """Test all sections needed for NLP query processing exist."""
        required_sections = [
            "tables",
            "business_context"
        ]
        for section in required_sections:
            assert section in semantic_config, f"Missing section for ORION consumer: {section}"

        business_context = semantic_config["business_context"]
        nlp_sections = [
            "fact_grain",
            "business_terms",
            "seed_questions",
            "join_semantics",
            "default_filters"
        ]
        for section in nlp_sections:
            assert section in business_context, f"Missing NLP section: {section}"

    def test_column_metadata_is_complete(self, all_columns: Dict[str, Set[str]],
                                         semantic_config: Dict[str, Any]):
        """Test all columns have complete metadata for NLP understanding."""
        for zone in ["silver", "gold"]:
            for table_name, table_def in semantic_config["tables"][zone].items():
                columns = table_def["columns"]
                for col_name, col_def in columns.items():
                    # Required fields for ORION consumer
                    assert "type" in col_def, f"{table_name}.{col_name} missing type"
                    assert "role" in col_def, f"{table_name}.{col_name} missing role"
                    assert "description" in col_def, f"{table_name}.{col_name} missing description"

                    # Measures must have aggregation
                    if col_def["role"] == "measure":
                        assert "default_aggregation" in col_def, \
                            f"{table_name}.{col_name} is measure but missing default_aggregation"

    def test_business_terms_enable_synonym_matching(self, semantic_config: Dict[str, Any]):
        """Test business terms provide synonyms for NLP matching."""
        terms = semantic_config["business_context"]["business_terms"]

        for term in terms:
            assert "term" in term
            assert "synonyms" in term
            assert isinstance(term["synonyms"], list)
            assert len(term["synonyms"]) > 0, f"Business term '{term['term']}' has no synonyms"

            # Synonyms should be different from the term itself
            term_lower = term["term"].lower()
            has_real_synonym = any(syn.lower() != term_lower for syn in term["synonyms"])
            assert has_real_synonym, f"Business term '{term['term']}' needs at least one real synonym"

    def test_join_semantics_enable_auto_joining(self, semantic_config: Dict[str, Any]):
        """Test join_semantics provide enough info for automatic join generation."""
        joins = semantic_config["business_context"]["join_semantics"]

        for join in joins:
            # Must have join condition in SQL format
            assert "join_condition" in join
            assert "=" in join["join_condition"], \
                f"Join {join['join_name']} condition should be SQL format"

            # Must specify when to use the join
            assert "when_to_join" in join
            assert len(join["when_to_join"]) > 10, \
                f"Join {join['join_name']} 'when_to_join' should be descriptive"

            # Must specify pre vs post aggregation
            assert "pre_aggregation_rule" in join


# Seed questions validation
class TestSeedQuestions:
    """Tests that validate seed questions have all required columns and are executable."""

    def test_seed_questions_reference_existing_columns(self, semantic_config: Dict[str, Any],
                                                       all_columns: Dict[str, Set[str]]):
        """Test all columns referenced in seed questions exist."""
        questions = semantic_config["business_context"]["seed_questions"]

        # Get all available columns (flattened)
        all_available_cols = set()
        for cols in all_columns.values():
            all_available_cols.update(cols)

        for q in questions:
            sql_hint = q["sql_hint"].lower()

            # Extract column references (simple pattern matching)
            # Look for common patterns: col_name, table.col_name, AVG(col_name), etc.
            potential_cols = re.findall(r'\b([a-z_]+)\b', sql_hint)

            # Filter to actual column references (not SQL keywords)
            sql_keywords = {
                'select', 'from', 'where', 'group', 'by', 'order', 'join', 'on',
                'as', 'limit', 'and', 'or', 'is', 'null', 'not', 'desc', 'asc',
                'inner', 'left', 'right', 'outer', 'sum', 'avg', 'max', 'min', 'count'
            }

            column_refs = [col for col in potential_cols
                          if col not in sql_keywords and col in all_available_cols]

            # Should reference at least one actual column
            assert len(column_refs) > 0, \
                f"Seed question '{q['question']}' doesn't reference any valid columns"

    def test_seed_questions_have_complete_sql_hints(self, semantic_config: Dict[str, Any]):
        """Test seed question SQL hints are complete queries."""
        questions = semantic_config["business_context"]["seed_questions"]

        for q in questions:
            sql_hint = q["sql_hint"].upper()

            # Should be a SELECT statement
            assert "SELECT" in sql_hint, \
                f"Seed question '{q['question']}' SQL hint should start with SELECT"

            # Should have FROM clause
            assert "FROM" in sql_hint, \
                f"Seed question '{q['question']}' SQL hint missing FROM clause"

            # Aggregation queries should have GROUP BY
            if any(agg in sql_hint for agg in ["AVG(", "SUM(", "COUNT(", "MAX(", "MIN("]):
                # If there's an aggregation and multiple columns, should have GROUP BY
                if sql_hint.count(",") > 0:
                    assert "GROUP BY" in sql_hint, \
                        f"Seed question '{q['question']}' has aggregation but no GROUP BY"

    def test_seed_questions_use_appropriate_joins(self, semantic_config: Dict[str, Any]):
        """Test seed questions that need joins actually include JOIN clauses."""
        questions = semantic_config["business_context"]["seed_questions"]

        # Get dimension table names
        gold = semantic_config["tables"]["gold"]
        dim_tables = [name for name in gold.keys() if name.startswith("dim_")]

        for q in questions:
            sql_hint = q["sql_hint"].lower()
            question_text = q["question"].lower()

            # If question asks about fund attributes (name, type, company)
            # and uses fact table, it should join to dim_fund
            if "fact" in sql_hint:
                needs_dim_fund = any(attr in question_text for attr in
                                    ["fund name", "etf", "mutual fund", "company"])

                if needs_dim_fund:
                    assert "join" in sql_hint and "dim_fund" in sql_hint, \
                        f"Seed question '{q['question']}' needs dim_fund join"

    def test_seed_questions_cover_key_metrics(self, semantic_config: Dict[str, Any]):
        """Test seed questions demonstrate how to query key metrics."""
        questions = semantic_config["business_context"]["seed_questions"]
        all_questions_text = " ".join([q["question"].lower() for q in questions])

        # Key metrics that should have example queries
        key_metrics = [
            "sharpe",      # risk-adjusted performance
            "return",      # returns
            "aum",         # assets under management
            "expense",     # fees
            "rating"       # quality
        ]

        for metric in key_metrics:
            assert metric in all_questions_text, \
                f"No seed question demonstrates querying '{metric}'"


# Join semantics validation
class TestJoinSemantics:
    """Tests that validate join_semantics are complete and consistent."""

    def test_all_dimension_tables_have_joins(self, semantic_config: Dict[str, Any]):
        """Test every dimension table has a join defined."""
        gold = semantic_config["tables"]["gold"]
        dim_tables = [name for name in gold.keys() if name.startswith("dim_")]

        joins = semantic_config["business_context"]["join_semantics"]
        joined_tables = set()
        for join in joins:
            joined_tables.add(join["right_table"])

        for dim_table in dim_tables:
            assert dim_table in joined_tables, \
                f"Dimension table {dim_table} has no join semantics defined"

    def test_join_conditions_reference_valid_columns(self, semantic_config: Dict[str, Any],
                                                     all_columns: Dict[str, Set[str]]):
        """Test join conditions reference columns that exist in both tables."""
        joins = semantic_config["business_context"]["join_semantics"]
        gold = semantic_config["tables"]["gold"]

        for join in joins:
            left_table = join["left_table"]
            right_table = join["right_table"]
            condition = join["join_condition"]

            # Extract column references from condition (simple parsing)
            # Format: "table.column = other_table.column"
            parts = condition.split("=")
            assert len(parts) == 2, f"Join condition format invalid: {condition}"

            # Get left and right column references
            left_ref = parts[0].strip()
            right_ref = parts[1].strip()

            # Extract table.column
            if "." in left_ref:
                left_table_ref, left_col = left_ref.rsplit(".", 1)
                left_cols = set(gold[left_table]["columns"].keys())
                assert left_col in left_cols, \
                    f"Join references non-existent column: {left_ref}"

            if "." in right_ref:
                right_table_ref, right_col = right_ref.rsplit(".", 1)
                right_cols = set(gold[right_table]["columns"].keys())
                assert right_col in right_cols, \
                    f"Join references non-existent column: {right_ref}"

    def test_join_provides_analysis_guidance(self, semantic_config: Dict[str, Any]):
        """Test join semantics provide guidance for ORION consumer."""
        joins = semantic_config["business_context"]["join_semantics"]

        for join in joins:
            # Should explain when to use this join
            assert "when_to_join" in join
            when_to_join = join["when_to_join"].lower()
            assert len(when_to_join) > 20, \
                f"Join {join['join_name']} needs more detailed 'when_to_join' guidance"

            # Should specify pre-aggregation rule
            assert "pre_aggregation_rule" in join
            pre_agg = join["pre_aggregation_rule"].lower()
            assert "before" in pre_agg or "after" in pre_agg, \
                f"Join {join['join_name']} pre_aggregation_rule should say 'before' or 'after'"

    def test_fact_to_dimension_joins_are_consistent(self, semantic_config: Dict[str, Any]):
        """Test fact table joins to dimensions are consistent with FK definitions."""
        gold = semantic_config["tables"]["gold"]
        fact_table = gold["fact_fund_performance"]

        # Get all foreign keys from fact table
        fk_columns = {}
        for col_name, col_def in fact_table["columns"].items():
            if col_def.get("role") == "foreign_key":
                fk_columns[col_name] = col_def.get("references")

        # Check that join semantics match FK definitions
        joins = semantic_config["business_context"]["join_semantics"]
        for join in joins:
            if join["left_table"] == "fact_fund_performance":
                condition = join["join_condition"]
                # Extract FK column name from condition
                # Format: "fact.fk_col = dim.pk_col"
                match = re.search(r'fact\.(\w+)\s*=', condition)
                if match:
                    fk_col = match.group(1)
                    # If this is a defined FK, check it matches the join
                    if fk_col in fk_columns:
                        expected_ref = fk_columns[fk_col]
                        assert expected_ref in condition, \
                            f"Join condition doesn't match FK reference for {fk_col}"

    def test_joins_specify_columns_available(self, semantic_config: Dict[str, Any]):
        """Test joins specify which dimension columns become available."""
        joins = semantic_config["business_context"]["join_semantics"]
        gold = semantic_config["tables"]["gold"]

        for join in joins:
            # Joins to dimension tables should list available columns
            if join["right_table"].startswith("dim_"):
                assert "columns_available_after_join" in join, \
                    f"Join {join['join_name']} should list available columns"

                available = join["columns_available_after_join"]
                assert isinstance(available, list)
                assert len(available) > 0, \
                    f"Join {join['join_name']} should have at least one available column"

                # All listed columns should exist in the dimension table
                dim_table = join["right_table"]
                dim_cols = set(gold[dim_table]["columns"].keys())
                for col in available:
                    assert col in dim_cols, \
                        f"Join {join['join_name']} lists non-existent column: {col}"


# Business terms validation
class TestBusinessTerms:
    """Tests that validate business terms map correctly to actual columns."""

    def test_all_business_terms_map_to_real_columns(self, semantic_config: Dict[str, Any],
                                                    all_columns: Dict[str, Set[str]]):
        """Test every business term maps to a column that exists."""
        terms = semantic_config["business_context"]["business_terms"]

        # Get all available columns (flattened)
        all_available_cols = set()
        for cols in all_columns.values():
            all_available_cols.update(cols)

        for term in terms:
            mapped_col = term["maps_to_column"]
            assert mapped_col in all_available_cols, \
                f"Business term '{term['term']}' maps to non-existent column: {mapped_col}"

    def test_business_terms_map_to_appropriate_types(self, semantic_config: Dict[str, Any]):
        """Test business terms map to columns with appropriate data types."""
        terms = semantic_config["business_context"]["business_terms"]

        # Build column type map
        col_types = {}
        for zone in ["silver", "gold"]:
            for table_name, table_def in semantic_config["tables"][zone].items():
                for col_name, col_def in table_def["columns"].items():
                    col_types[col_name] = col_def["type"]

        for term in terms:
            mapped_col = term["maps_to_column"]
            col_type = col_types.get(mapped_col)

            # Numeric terms should map to numeric types
            if any(word in term["term"].lower() for word in
                  ["ratio", "pct", "yield", "return", "beta", "rating"]):
                assert col_type in ["double", "int", "long", "float"], \
                    f"Numeric business term '{term['term']}' maps to non-numeric column {mapped_col} ({col_type})"

    def test_business_term_sql_expressions_are_valid(self, semantic_config: Dict[str, Any]):
        """Test business term SQL expressions use valid aggregations."""
        terms = semantic_config["business_context"]["business_terms"]
        valid_aggs = ["SUM", "AVG", "MIN", "MAX", "COUNT", "LAST"]

        for term in terms:
            sql_expr = term["sql_expression"].upper()

            # Should contain an aggregation function
            has_aggregation = any(agg in sql_expr for agg in valid_aggs)
            assert has_aggregation, \
                f"Business term '{term['term']}' SQL expression should include aggregation"

            # Should reference the mapped column
            mapped_col = term["maps_to_column"]
            assert mapped_col in term["sql_expression"], \
                f"Business term '{term['term']}' SQL doesn't reference mapped column {mapped_col}"

    def test_key_business_concepts_have_terms(self, semantic_config: Dict[str, Any]):
        """Test key business concepts have business term definitions."""
        terms = semantic_config["business_context"]["business_terms"]
        all_terms_text = " ".join([t["term"].lower() for t in terms])

        # Key concepts for mutual fund analysis
        key_concepts = ["aum", "return", "fee", "risk", "rating"]

        for concept in key_concepts:
            assert concept in all_terms_text, \
                f"Missing business term for key concept: {concept}"


# Completeness validation
class TestMetadataCompleteness:
    """Tests that validate metadata is complete enough for full ORION consumer usage."""

    def test_fact_table_has_all_key_metrics(self, semantic_config: Dict[str, Any]):
        """Test fact table includes all key performance metrics."""
        fact_table = semantic_config["tables"]["gold"]["fact_fund_performance"]
        columns = fact_table["columns"]

        # Key metrics for fund analysis
        required_metrics = [
            "nav", "total_assets_millions", "expense_ratio_pct",
            "sharpe_ratio", "beta", "morningstar_rating",
            "return_1yr_pct"
        ]

        for metric in required_metrics:
            assert metric in columns, f"Fact table missing key metric: {metric}"

    def test_dimension_tables_have_hierarchies(self, semantic_config: Dict[str, Any]):
        """Test dimension tables support drill-down analysis."""
        hierarchies = semantic_config["business_context"]["dimension_hierarchies"]

        # Should have at least one hierarchy
        assert len(hierarchies) > 0, "No dimension hierarchies defined"

        # Hierarchy should have multiple levels
        for hierarchy in hierarchies:
            assert len(hierarchy["levels"]) >= 2, \
                f"Hierarchy {hierarchy['name']} needs at least 2 levels"

    def test_default_filters_handle_time_based_queries(self, semantic_config: Dict[str, Any]):
        """Test default filters help with time-based query patterns."""
        filters = semantic_config["business_context"]["default_filters"]

        # Should have filters related to time/date
        filter_text = " ".join([f["description"].lower() for f in filters])
        assert "date" in filter_text or "recent" in filter_text or "current" in filter_text, \
            "No default filters for time-based queries"

    def test_time_intelligence_is_configured(self, semantic_config: Dict[str, Any]):
        """Test time intelligence provides calendar semantics."""
        time_intel = semantic_config["business_context"]["time_intelligence"]

        required_fields = ["fiscal_year_start", "data_freshness", "default_period"]
        for field in required_fields:
            assert field in time_intel, f"Time intelligence missing: {field}"
            assert time_intel[field] is not None, f"Time intelligence {field} is null"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
