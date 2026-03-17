"""
Unit tests for product_inventory metadata artifacts.

Validates that source.yaml and semantic.yaml are well-formed,
contain all required fields, and correctly classify columns.
"""

import yaml
from pathlib import Path


# Use absolute paths from workload root
WORKLOAD_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = WORKLOAD_ROOT / "config"
SOURCE_YAML_PATH = CONFIG_DIR / "source.yaml"
SEMANTIC_YAML_PATH = CONFIG_DIR / "semantic.yaml"

EXPECTED_COLUMNS = [
    "product_id", "sku", "product_name", "category", "subcategory", "brand",
    "unit_price", "cost_price", "quantity_on_hand", "reorder_level", "reorder_quantity",
    "warehouse_location", "supplier_id", "supplier_name", "last_restocked_date",
    "expiry_date", "weight_kg", "status",
]

EXPECTED_MEASURES = {
    "unit_price", "cost_price", "quantity_on_hand",
    "reorder_level", "reorder_quantity", "weight_kg"
}

EXPECTED_DIMENSIONS = {
    "category", "subcategory", "brand", "warehouse_location", "status"
}

EXPECTED_TEMPORAL = {
    "last_restocked_date", "expiry_date"
}

EXPECTED_KEYS = {
    "product_id"  # primary key
}

VALID_DATA_TYPES = {"string", "integer", "decimal", "date"}
VALID_COLUMN_ROLES = {"dimension", "measure", "temporal", "attribute"}


class TestSourceYaml:
    """Tests for config/source.yaml."""

    def test_source_yaml_exists(self):
        """source.yaml file must exist on disk."""
        assert SOURCE_YAML_PATH.exists(), f"source.yaml not found at {SOURCE_YAML_PATH}"

    def test_source_yaml_is_valid_yaml(self):
        """source.yaml must parse without errors."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert isinstance(config, dict)

    def test_has_source_section(self):
        """source.yaml must have a top-level 'source' key."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "source" in config

    def test_has_required_source_fields(self):
        """source section must contain name, format, delimiter, schema."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        source = config["source"]
        for field in ("name", "format", "delimiter", "schema"):
            assert field in source, f"Missing required field: {field}"

    def test_has_location(self):
        """source section must have a location field."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "location" in config["source"]

    def test_has_credentials(self):
        """source section must have a credentials block with connection_id."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "credentials" in config["source"]
        assert "connection_id" in config["source"]["credentials"]

    def test_schema_has_columns(self):
        """schema must contain a columns list."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        schema = config["source"]["schema"]
        assert "columns" in schema
        assert isinstance(schema["columns"], list)

    def test_all_columns_present_in_schema(self):
        """All 18 expected columns must be present in the schema."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        schema_columns = [col["name"] for col in config["source"]["schema"]["columns"]]
        for col_name in EXPECTED_COLUMNS:
            assert col_name in schema_columns, f"Column '{col_name}' missing from source.yaml schema"

    def test_column_count(self):
        """Schema must have exactly 18 columns."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        cols = config["source"]["schema"]["columns"]
        assert len(cols) == 18, f"Expected 18 columns, got {len(cols)}"

    def test_every_column_has_type(self):
        """Every column in the schema must have a type field."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        for col in config["source"]["schema"]["columns"]:
            assert "type" in col, f"Column '{col.get('name', 'UNKNOWN')}' missing type"

    def test_data_types_are_valid(self):
        """Every column type must be one of the valid types."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        for col in config["source"]["schema"]["columns"]:
            assert col["type"] in VALID_DATA_TYPES, \
                f"Column '{col['name']}' has invalid type: {col['type']}"

    def test_primary_key_defined(self):
        """product_id must be marked as primary_key."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        schema_columns = {col["name"]: col for col in config["source"]["schema"]["columns"]}
        assert "product_id" in schema_columns
        assert schema_columns["product_id"].get("primary_key") is True

    def test_business_key_defined(self):
        """sku must be marked as business_key."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        schema_columns = {col["name"]: col for col in config["source"]["schema"]["columns"]}
        assert "sku" in schema_columns
        assert schema_columns["sku"].get("business_key") is True

    def test_no_pii_columns(self):
        """This dataset should not have PII columns."""
        with open(SOURCE_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        for col in config["source"]["schema"]["columns"]:
            assert not col.get("pii", False), \
                f"Column '{col['name']}' should not be flagged as PII"


class TestSemanticYaml:
    """Tests for config/semantic.yaml."""

    def test_semantic_yaml_exists(self):
        """semantic.yaml file must exist on disk."""
        assert SEMANTIC_YAML_PATH.exists(), f"semantic.yaml not found at {SEMANTIC_YAML_PATH}"

    def test_semantic_yaml_is_valid_yaml(self):
        """semantic.yaml must parse without errors."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert isinstance(config, dict)

    def test_has_dataset_section(self):
        """semantic.yaml must have a top-level 'dataset' key."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "dataset" in config

    def test_has_columns_section(self):
        """semantic.yaml must have a top-level 'columns' key."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "columns" in config

    def test_all_columns_classified(self):
        """All 18 columns must be present and classified with a role."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        sem_columns = config["columns"]
        for col_name in EXPECTED_COLUMNS:
            assert col_name in sem_columns, f"Column '{col_name}' missing from semantic.yaml"
            col = sem_columns[col_name]
            assert "role" in col, f"Column '{col_name}' missing role classification"
            assert col["role"] in VALID_COLUMN_ROLES, \
                f"Column '{col_name}' has invalid role: {col['role']}"

    def test_measures_have_default_aggregation(self):
        """All measure columns must have default_aggregation specified."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        sem_columns = config["columns"]
        for col_name in EXPECTED_MEASURES:
            col = sem_columns[col_name]
            assert col.get("role") == "measure", \
                f"Column '{col_name}' should have role=measure"
            assert "default_aggregation" in col, \
                f"Measure '{col_name}' missing default_aggregation"
            assert col["default_aggregation"] in ["sum", "avg", "min", "max", "count", "count_distinct"], \
                f"Measure '{col_name}' has invalid default_aggregation: {col['default_aggregation']}"

    def test_dimension_hierarchies_are_valid(self):
        """Dimension hierarchies must reference valid columns."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        sem_columns = config["columns"]

        for col_name, col_def in sem_columns.items():
            if "dimension_hierarchy" in col_def:
                hierarchy = col_def["dimension_hierarchy"]
                assert "name" in hierarchy, f"Column '{col_name}' hierarchy missing name"
                assert "levels" in hierarchy, f"Column '{col_name}' hierarchy missing levels"
                # All levels must be valid column names
                for level in hierarchy["levels"]:
                    assert level in EXPECTED_COLUMNS, \
                        f"Hierarchy level '{level}' in column '{col_name}' is not a valid column"

    def test_primary_key_is_dimension(self):
        """product_id must be classified as dimension with is_primary_key=true."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        product_id = config["columns"]["product_id"]
        assert product_id.get("role") == "dimension"
        assert product_id.get("is_primary_key") is True

    def test_no_pii_flags(self):
        """This dataset should not have PII flags set to true."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        for col_name, col_def in config["columns"].items():
            assert not col_def.get("pii", False), \
                f"Column '{col_name}' should not be flagged as PII"

    def test_business_terms_have_synonyms_and_sql(self):
        """Business terms must have both synonyms and sql_expression."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        if "business_terms" in config:
            for term_name, term_def in config["business_terms"].items():
                assert "synonyms" in term_def, \
                    f"Business term '{term_name}' missing synonyms"
                assert "sql_expression" in term_def, \
                    f"Business term '{term_name}' missing sql_expression"
                assert isinstance(term_def["synonyms"], list), \
                    f"Business term '{term_name}' synonyms must be a list"

    def test_grain_section_present(self):
        """semantic.yaml must have a grain section."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "grain" in config
        grain = config["grain"]
        assert "description" in grain
        assert "grain_columns" in grain
        assert isinstance(grain["grain_columns"], list)

    def test_gold_schema_present(self):
        """semantic.yaml must have a gold_schema section."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "gold_schema" in config
        gold = config["gold_schema"]
        assert "format" in gold
        assert "use_case" in gold
        assert "tables" in gold

    def test_default_filters_present(self):
        """semantic.yaml must have default_filters for Analysis Agent."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "default_filters" in config
        assert isinstance(config["default_filters"], dict)
        assert len(config["default_filters"]) > 0

    def test_seed_questions_present(self):
        """semantic.yaml must include at least 3 seed questions."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "seed_questions" in config
        questions = config["seed_questions"]
        assert len(questions) >= 3, f"Must have at least 3 seed questions, got {len(questions)}"
        for q in questions:
            assert "question" in q
            assert "sql" in q

    def test_time_intelligence_present(self):
        """semantic.yaml must have time_intelligence section."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert "time_intelligence" in config
        ti = config["time_intelligence"]
        assert "fiscal_year_start" in ti
        assert "week_start" in ti
        assert "timezone" in ti

    def test_dataset_domain(self):
        """Dataset domain must be 'Supply Chain & Inventory Management'."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        assert config["dataset"].get("domain") == "Supply Chain & Inventory Management"

    def test_dataset_has_owner_and_steward(self):
        """Dataset must have owner and steward defined."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        dataset = config["dataset"]
        assert "owner" in dataset
        assert "steward" in dataset

    def test_measures_have_correct_aggregations(self):
        """Verify measure columns have semantically correct default_aggregation."""
        with open(SEMANTIC_YAML_PATH, "r") as f:
            config = yaml.safe_load(f)
        sem_columns = config["columns"]

        # Prices should be averaged
        assert sem_columns["unit_price"]["default_aggregation"] == "avg"
        assert sem_columns["cost_price"]["default_aggregation"] == "avg"
        assert sem_columns["weight_kg"]["default_aggregation"] == "avg"
        assert sem_columns["reorder_level"]["default_aggregation"] == "avg"

        # Quantities should be summed
        assert sem_columns["quantity_on_hand"]["default_aggregation"] == "sum"
        assert sem_columns["reorder_quantity"]["default_aggregation"] == "sum"
