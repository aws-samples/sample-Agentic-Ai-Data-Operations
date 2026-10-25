"""
Neptune Graph Schema Definition

Defines the vertex labels, edge labels, and properties for the unified metadata graph
stored in Amazon Neptune.

This schema combines:
- Technical metadata (Glue Data Catalog, Lake Formation)
- Business context (semantic.yaml)
- Embeddings (Titan 1024-dimensional vectors)
"""

# Gremlin schema definition
GRAPH_SCHEMA = {
    "vertex_labels": [
        "database",       # Database container
        "table",          # Table/view (fact, dimension, reference)
        "column",         # Column with data type, role, aggregation
        "business_term",  # Business vocabulary term with synonyms
        "query"           # Stored query (seed + learned)
    ],

    "edge_labels": [
        "contains",       # database → table
        "has_column",     # table → column
        "foreign_key",    # table → table (FK relationship)
        "references",     # column → column (FK reference)
        "described_by",   # column → business_term
        "has_hierarchy",  # table → column* (dimension hierarchy)
        "uses",           # query → table (query uses table)
        "similar_to"      # query → query (embedding similarity)
    ],

    "properties": {
        "database": [
            "name",           # Database name (string)
            "domain",         # Business domain (string, e.g., "Finance", "Healthcare")
            "owner"           # Team/person owner (string)
        ],

        "table": [
            "name",           # Table name (string)
            "type",           # Table type (string: "fact", "dimension", "reference")
            "grain",          # Row grain description (string, e.g., "one row per order")
            "description",    # Table description (string)
            "embedding",      # Titan embedding vector (float[1024])
            "primary_key"     # Primary key columns (list<string>)
        ],

        "column": [
            "name",                # Column name (string)
            "data_type",           # Data type (string, e.g., "string", "decimal(10,2)")
            "role",                # Column role (string: "measure", "dimension", "temporal", "identifier", "attribute")
            "description",         # Column description (string)
            "aggregation",         # Default aggregation (string: "sum", "avg", "count", "count_distinct", "min", "max", "weighted_avg")
            "pii_type",            # PII type (string, e.g., "EMAIL", "SSN", "PHONE")
            "pii_classification",  # PII classification (string: "CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE")
            "sensitivity",         # Data sensitivity (string: "CRITICAL", "HIGH", "MEDIUM", "LOW")
            "is_partition_key",    # Is partition key (boolean)
            "is_nullable",         # Is nullable (boolean)
            "is_foreign_key",      # Is foreign key (boolean)
            "embedding",           # Titan embedding vector (float[1024])
            "sample_values",       # Sample values (list<string>)
            "business_terms"       # Business terms (list<string>)
        ],

        "business_term": [
            "term",           # Term name (string, e.g., "revenue", "AOV")
            "synonyms",       # Synonyms (list<string>, e.g., ["sales", "turnover"])
            "definition",     # Definition (string)
            "sql_expression", # SQL expression (string, e.g., "SUM(revenue)")
            "embedding"       # Titan embedding vector (float[1024])
        ],

        "query": [
            "query_id",       # Unique query ID (string)
            "nl_text",        # Natural language query text (string)
            "sql",            # Generated SQL (string)
            "workload",       # Workload name (string)
            "success_count",  # Number of times successfully executed (int)
            "last_used",      # Last execution timestamp (timestamp)
            "embedding"       # Titan embedding vector (float[1024])
        ]
    },

    "edge_properties": {
        "foreign_key": {
            "on_column": "string"  # FK column name
        },
        "has_hierarchy": {
            "hierarchy_name": "string",  # Hierarchy name (e.g., "product_hierarchy")
            "level": "int"               # Level in hierarchy (1, 2, 3...)
        },
        "similar_to": {
            "similarity_score": "float"  # Cosine similarity score (0.0 to 1.0)
        }
    }
}


# Vertex ID patterns (for consistent ID generation)
VERTEX_ID_PATTERNS = {
    "database": "{database_name}",
    "table": "{database_name}.{table_name}",
    "column": "{database_name}.{table_name}.{column_name}",
    "business_term": "term:{term_name}",
    "query": "query:{workload}:{query_id}"
}


def get_vertex_id(vertex_type: str, **kwargs) -> str:
    """
    Generate consistent vertex ID based on vertex type.

    Args:
        vertex_type: Type of vertex ("database", "table", "column", "business_term", "query")
        **kwargs: Properties to fill in ID pattern

    Returns:
        Vertex ID string

    Examples:
        >>> get_vertex_id("table", database_name="financial_portfolios_db", table_name="positions")
        'financial_portfolios_db.positions'

        >>> get_vertex_id("column", database_name="db", table_name="tbl", column_name="col")
        'db.tbl.col'
    """
    if vertex_type not in VERTEX_ID_PATTERNS:
        raise ValueError(f"Unknown vertex type: {vertex_type}")

    pattern = VERTEX_ID_PATTERNS[vertex_type]
    return pattern.format(**kwargs)


def validate_property(vertex_type: str, property_name: str) -> bool:
    """
    Check if a property is valid for a vertex type.

    Args:
        vertex_type: Type of vertex
        property_name: Name of property to validate

    Returns:
        True if property is valid for vertex type

    Example:
        >>> validate_property("table", "grain")
        True
        >>> validate_property("table", "invalid_prop")
        False
    """
    return property_name in GRAPH_SCHEMA["properties"].get(vertex_type, [])


def get_embedding_dimension() -> int:
    """Return the dimensionality of Titan embeddings (1024)."""
    return 1024
