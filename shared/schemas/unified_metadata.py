"""
Unified Metadata Data Classes

Defines dataclasses for unified metadata that combines:
- Technical metadata (Glue Data Catalog, Lake Formation)
- Business context (semantic.yaml)
- Embeddings (Titan vectors)

These classes are used by the metadata combiner and Neptune loader.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class UnifiedColumn:
    """
    Unified column metadata combining Glue Catalog + semantic.yaml + Lake Formation.
    """
    # Basic properties
    name: str
    data_type: str
    role: str  # "measure", "dimension", "temporal", "identifier", "attribute"
    description: str

    # From Glue Catalog
    is_partition_key: bool = False
    is_nullable: bool = True

    # From semantic.yaml
    default_aggregation: Optional[str] = None  # "sum", "avg", "count", "count_distinct", "min", "max", "weighted_avg"
    business_terms: List[str] = field(default_factory=list)
    sample_values: List[str] = field(default_factory=list)
    weighted_by: Optional[str] = None  # Column to weight by (for weighted_avg)

    # From Lake Formation
    pii_classification: Optional[str] = None  # "CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"
    pii_type: Optional[str] = None  # "EMAIL", "SSN", "PHONE", "ADDRESS", "DOB", etc.
    data_sensitivity: Optional[str] = None  # "CRITICAL", "HIGH", "MEDIUM", "LOW"

    # Computed (from relationships in semantic.yaml)
    is_foreign_key: bool = False
    references: Optional[str] = None  # "target_table.column"

    # Embedding (from Titan)
    embedding_vector: Optional[List[float]] = None  # 1024 dimensions

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "data_type": self.data_type,
            "role": self.role,
            "description": self.description,
            "is_partition_key": self.is_partition_key,
            "is_nullable": self.is_nullable,
            "default_aggregation": self.default_aggregation,
            "business_terms": self.business_terms,
            "sample_values": self.sample_values,
            "weighted_by": self.weighted_by,
            "pii_classification": self.pii_classification,
            "pii_type": self.pii_type,
            "data_sensitivity": self.data_sensitivity,
            "is_foreign_key": self.is_foreign_key,
            "references": self.references,
            "has_embedding": self.embedding_vector is not None
        }


@dataclass
class UnifiedTable:
    """
    Unified table metadata combining Glue Catalog + semantic.yaml + Lake Formation.
    """
    # Basic properties
    database: str
    name: str
    table_type: str  # "fact", "dimension", "reference"
    grain: str  # e.g., "one row per order"
    primary_key: List[str]
    columns: List[UnifiedColumn]

    # Relationships (from semantic.yaml)
    relationships: List[Dict[str, Any]] = field(default_factory=list)  # FK relationships to other tables

    # Business context (from semantic.yaml)
    business_terms: List[Dict[str, Any]] = field(default_factory=list)  # Business vocabulary
    default_filters: List[Dict[str, Any]] = field(default_factory=list)  # Default WHERE clauses
    seed_queries: List[Dict[str, Any]] = field(default_factory=list)  # Seed SQL examples

    # Embedding (from Titan)
    embedding_vector: Optional[List[float]] = None  # 1024 dimensions

    # Dimension hierarchies (from semantic.yaml)
    dimension_hierarchies: List[Dict[str, Any]] = field(default_factory=list)

    # Glue metadata
    location: Optional[str] = None  # S3 location
    format: Optional[str] = None  # "iceberg", "parquet", "csv"

    def get_column(self, column_name: str) -> Optional[UnifiedColumn]:
        """Get column by name."""
        return next((col for col in self.columns if col.name == column_name), None)

    def get_measures(self) -> List[UnifiedColumn]:
        """Get all measure columns."""
        return [col for col in self.columns if col.role == "measure"]

    def get_dimensions(self) -> List[UnifiedColumn]:
        """Get all dimension columns."""
        return [col for col in self.columns if col.role == "dimension"]

    def get_temporal_columns(self) -> List[UnifiedColumn]:
        """Get all temporal columns."""
        return [col for col in self.columns if col.role == "temporal"]

    def get_identifiers(self) -> List[UnifiedColumn]:
        """Get all identifier columns (PKs, FKs)."""
        return [col for col in self.columns if col.role == "identifier"]

    def get_foreign_keys(self) -> List[UnifiedColumn]:
        """Get all foreign key columns."""
        return [col for col in self.columns if col.is_foreign_key]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "database": self.database,
            "name": self.name,
            "table_type": self.table_type,
            "grain": self.grain,
            "primary_key": self.primary_key,
            "columns": [col.to_dict() for col in self.columns],
            "relationships": self.relationships,
            "business_terms": self.business_terms,
            "default_filters": self.default_filters,
            "seed_queries": self.seed_queries,
            "dimension_hierarchies": self.dimension_hierarchies,
            "location": self.location,
            "format": self.format,
            "has_embedding": self.embedding_vector is not None
        }


@dataclass
class UnifiedMetadataGraph:
    """
    Complete unified metadata graph for a workload.

    Contains all tables with their columns, relationships, and business context.
    Ready to be loaded into Neptune.
    """
    tables: List[UnifiedTable]
    workload: Optional[str] = None
    database: Optional[str] = None

    # Global business context (from semantic.yaml)
    global_business_terms: List[Dict[str, Any]] = field(default_factory=list)
    global_dimension_hierarchies: List[Dict[str, Any]] = field(default_factory=list)
    time_intelligence: Optional[Dict[str, Any]] = None

    def get_table(self, table_name: str) -> Optional[UnifiedTable]:
        """Get table by name."""
        return next((tbl for tbl in self.tables if tbl.name == table_name), None)

    def get_all_measures(self) -> List[tuple[str, UnifiedColumn]]:
        """Get all measure columns across all tables (table_name, column)."""
        measures = []
        for table in self.tables:
            for col in table.get_measures():
                measures.append((table.name, col))
        return measures

    def get_all_dimensions(self) -> List[tuple[str, UnifiedColumn]]:
        """Get all dimension columns across all tables (table_name, column)."""
        dimensions = []
        for table in self.tables:
            for col in table.get_dimensions():
                dimensions.append((table.name, col))
        return dimensions

    def get_all_foreign_keys(self) -> List[tuple[str, UnifiedColumn]]:
        """Get all FK columns across all tables (table_name, column)."""
        fks = []
        for table in self.tables:
            for col in table.get_foreign_keys():
                fks.append((table.name, col))
        return fks

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "workload": self.workload,
            "database": self.database,
            "tables": [tbl.to_dict() for tbl in self.tables],
            "global_business_terms": self.global_business_terms,
            "global_dimension_hierarchies": self.global_dimension_hierarchies,
            "time_intelligence": self.time_intelligence
        }

    def __len__(self) -> int:
        """Return number of tables in graph."""
        return len(self.tables)

    def __repr__(self) -> str:
        """String representation."""
        return f"<UnifiedMetadataGraph workload={self.workload} tables={len(self.tables)}>"
