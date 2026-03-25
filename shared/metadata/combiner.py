"""
Metadata Combiner

Combines metadata from three sources:
1. AWS Glue Data Catalog (technical metadata)
2. semantic.yaml (business context)
3. Lake Formation LF-Tags (access control)

Produces UnifiedMetadataGraph for loading into Neptune.
"""

from typing import Dict, List, Optional, Any
from pathlib import Path

from shared.metadata.glue_fetcher import GlueFetcher
from shared.metadata.semantic_reader import read_semantic_yaml, validate_semantic_yaml, get_table_from_semantic
from shared.metadata.lakeformation_fetcher import LakeFormationFetcher
from shared.schemas.unified_metadata import UnifiedColumn, UnifiedTable, UnifiedMetadataGraph


class MetadataCombiner:
    """Combine metadata from Glue, semantic.yaml, and Lake Formation."""

    def __init__(self, region: str = 'us-east-1'):
        """
        Initialize metadata fetchers.

        Args:
            region: AWS region
        """
        self.glue = GlueFetcher(region=region)
        self.lf = LakeFormationFetcher(region=region)
        self.region = region

    def combine_workload_metadata(
        self,
        workload: str,
        database: str
    ) -> UnifiedMetadataGraph:
        """
        Combine all metadata sources for a workload.

        Args:
            workload: Workload name (e.g., "financial_portfolios")
            database: Glue database name (e.g., "financial_portfolios_db")

        Returns:
            UnifiedMetadataGraph with all tables, columns, relationships

        Raises:
            FileNotFoundError: If semantic.yaml not found
            ValueError: If metadata inconsistencies detected

        Example:
            >>> combiner = MetadataCombiner()
            >>> graph = combiner.combine_workload_metadata("financial_portfolios", "financial_portfolios_db")
            >>> len(graph.tables)
            3
            >>> graph.get_table("positions").table_type
            'fact'
        """
        # 1. Read semantic.yaml
        semantic = read_semantic_yaml(workload)
        validate_semantic_yaml(semantic)

        # 2. Combine metadata for each table
        tables = []
        for table_def in semantic['tables']:
            table_name = table_def['name']

            try:
                unified_table = self._combine_table_metadata(
                    workload=workload,
                    database=database,
                    table_name=table_name,
                    table_def=table_def
                )
                tables.append(unified_table)
            except Exception as e:
                raise ValueError(
                    f"Failed to combine metadata for table '{table_name}': {e}"
                ) from e

        # 3. Extract global business context
        global_business_terms = semantic.get('business_terms', [])
        global_dimension_hierarchies = semantic.get('dimension_hierarchies', [])
        time_intelligence = semantic.get('time_intelligence')

        return UnifiedMetadataGraph(
            tables=tables,
            workload=workload,
            database=database,
            global_business_terms=global_business_terms,
            global_dimension_hierarchies=global_dimension_hierarchies,
            time_intelligence=time_intelligence
        )

    def _combine_table_metadata(
        self,
        workload: str,
        database: str,
        table_name: str,
        table_def: Dict[str, Any]
    ) -> UnifiedTable:
        """
        Combine metadata for a single table.

        Args:
            workload: Workload name
            database: Glue database name
            table_name: Table name
            table_def: Table definition from semantic.yaml

        Returns:
            UnifiedTable with merged metadata
        """
        # 1. Fetch Glue metadata
        try:
            glue_meta = self.glue.fetch_table_metadata(database, table_name)
        except ValueError as e:
            # Table doesn't exist in Glue yet (e.g., during planning phase)
            # Use semantic.yaml types only
            glue_meta = {
                "columns": [],
                "partitions": [],
                "location": None,
                "table_type": None,
                "format": None,
                "parameters": {}
            }

        # 2. Fetch LF-Tags
        try:
            lf_tags = self.lf.fetch_table_lf_tags(database, table_name)
        except Exception:
            # No LF-Tags applied yet (normal for new tables)
            lf_tags = {"table_tags": [], "column_tags": {}}

        # 3. Combine columns
        columns = self._combine_columns(
            table_def=table_def,
            glue_meta=glue_meta,
            lf_tags=lf_tags
        )

        # 4. Mark foreign key columns
        self._mark_foreign_keys(columns, table_def.get('relationships', []))

        # 5. Extract business context
        business_terms = table_def.get('business_terms', [])
        default_filters = table_def.get('default_filters', [])
        seed_queries = table_def.get('seed_questions', [])
        dimension_hierarchies = table_def.get('dimension_hierarchies', [])

        # 6. Extract primary key(s)
        primary_key_raw = table_def.get('primary_key')
        if isinstance(primary_key_raw, str):
            primary_key = [primary_key_raw]
        elif isinstance(primary_key_raw, list):
            primary_key = primary_key_raw
        else:
            primary_key = []

        return UnifiedTable(
            database=database,
            name=table_name,
            table_type=table_def['table_type'],
            grain=table_def['grain'],
            primary_key=primary_key,
            columns=columns,
            relationships=table_def.get('relationships', []),
            business_terms=business_terms,
            default_filters=default_filters,
            seed_queries=seed_queries,
            dimension_hierarchies=dimension_hierarchies,
            location=glue_meta.get('location'),
            format=glue_meta.get('format')
        )

    def _combine_columns(
        self,
        table_def: Dict[str, Any],
        glue_meta: Dict[str, Any],
        lf_tags: Dict[str, Any]
    ) -> List[UnifiedColumn]:
        """
        Combine column metadata from all three sources.

        Args:
            table_def: Table definition from semantic.yaml
            glue_meta: Metadata from Glue Catalog
            lf_tags: LF-Tags from Lake Formation

        Returns:
            List of UnifiedColumn objects
        """
        columns = []
        glue_columns_map = {col['name']: col for col in glue_meta['columns']}
        partition_names = {p['name'] for p in glue_meta['partitions']}
        column_lf_tags = lf_tags.get('column_tags', {})

        for col_def in table_def['columns']:
            col_name = col_def['name']

            # Get Glue column if exists
            glue_col = glue_columns_map.get(col_name)

            # Get LF-Tags for this column
            col_tags = column_lf_tags.get(col_name, [])

            # Determine data type (prefer Glue, fallback to semantic.yaml)
            if glue_col:
                data_type = glue_col['type']
            else:
                data_type = col_def.get('type', 'string')

            # Extract LF-Tag values
            pii_classification = self.lf.get_tag_value(col_tags, 'PII_Classification')
            pii_type = self.lf.get_tag_value(col_tags, 'PII_Type')
            data_sensitivity = self.lf.get_tag_value(col_tags, 'Data_Sensitivity')

            # Create UnifiedColumn
            unified_col = UnifiedColumn(
                name=col_name,
                data_type=data_type,
                role=col_def['role'],
                description=col_def.get('description', ''),
                is_partition_key=(col_name in partition_names),
                is_nullable=col_def.get('nullable', True),
                default_aggregation=col_def.get('default_aggregation'),
                business_terms=col_def.get('business_terms', []),
                sample_values=col_def.get('sample_values', []),
                weighted_by=col_def.get('weighted_by'),
                pii_classification=pii_classification,
                pii_type=pii_type,
                data_sensitivity=data_sensitivity,
                is_foreign_key=False,  # Set in _mark_foreign_keys()
                references=None,
                embedding_vector=None  # Set by embedder in Phase 3
            )

            columns.append(unified_col)

        return columns

    def _mark_foreign_keys(
        self,
        columns: List[UnifiedColumn],
        relationships: List[Dict[str, Any]]
    ):
        """
        Mark columns as foreign keys based on relationships.

        Args:
            columns: List of columns to update (modified in-place)
            relationships: List of relationship definitions from semantic.yaml

        Example relationship:
            {
                "type": "many_to_one",
                "target_table": "portfolios",
                "join_column": "portfolio_id",
                "target_column": "portfolio_id"
            }
        """
        for rel in relationships:
            join_column = rel.get('join_column')
            target_table = rel.get('target_table')
            target_column = rel.get('target_column', join_column)

            if not join_column or not target_table:
                continue

            # Find the column
            for col in columns:
                if col.name == join_column:
                    col.is_foreign_key = True
                    col.references = f"{target_table}.{target_column}"
                    break

    def combine_table_metadata(
        self,
        workload: str,
        database: str,
        table_name: str
    ) -> UnifiedTable:
        """
        Combine metadata for a single table (convenience method).

        Args:
            workload: Workload name
            database: Glue database name
            table_name: Table name

        Returns:
            UnifiedTable with merged metadata

        Example:
            >>> combiner = MetadataCombiner()
            >>> table = combiner.combine_table_metadata(
            ...     "financial_portfolios",
            ...     "financial_portfolios_db",
            ...     "positions"
            ... )
            >>> table.table_type
            'fact'
            >>> len(table.columns)
            10
        """
        semantic = read_semantic_yaml(workload)
        table_def = get_table_from_semantic(semantic, table_name)

        return self._combine_table_metadata(
            workload=workload,
            database=database,
            table_name=table_name,
            table_def=table_def
        )

    def validate_metadata_consistency(
        self,
        graph: UnifiedMetadataGraph
    ) -> List[str]:
        """
        Validate metadata consistency across sources.

        Args:
            graph: Unified metadata graph to validate

        Returns:
            List of warning messages (empty if all checks pass)

        Checks:
        - FK targets exist
        - Primary keys defined
        - Column roles are valid
        - Partition keys exist in columns
        """
        warnings = []

        table_names = {table.name for table in graph.tables}

        for table in graph.tables:
            # Check primary key exists
            if not table.primary_key:
                warnings.append(
                    f"Table '{table.name}': No primary key defined"
                )

            # Check FK targets exist
            for col in table.columns:
                if col.is_foreign_key and col.references:
                    target_table = col.references.split('.')[0]
                    if target_table not in table_names:
                        warnings.append(
                            f"Table '{table.name}', column '{col.name}': "
                            f"FK references non-existent table '{target_table}'"
                        )

            # Check partition keys exist in columns
            partition_cols = {col.name for col in table.columns if col.is_partition_key}
            column_names = {col.name for col in table.columns}

            for pk in partition_cols:
                if pk not in column_names:
                    warnings.append(
                        f"Table '{table.name}': Partition key '{pk}' not in columns"
                    )

            # Check column roles are valid
            valid_roles = {'measure', 'dimension', 'temporal', 'identifier', 'attribute'}
            for col in table.columns:
                if col.role not in valid_roles:
                    warnings.append(
                        f"Table '{table.name}', column '{col.name}': "
                        f"Invalid role '{col.role}' (valid: {valid_roles})"
                    )

        return warnings


def combine_metadata(workload: str, database: str, region: str = 'us-east-1') -> UnifiedMetadataGraph:
    """
    Convenience function to combine metadata for a workload.

    Args:
        workload: Workload name
        database: Glue database name
        region: AWS region

    Returns:
        UnifiedMetadataGraph

    Example:
        >>> graph = combine_metadata("financial_portfolios", "financial_portfolios_db")
        >>> len(graph.tables)
        3
        >>> graph.get_table("positions").table_type
        'fact'
    """
    combiner = MetadataCombiner(region=region)
    return combiner.combine_workload_metadata(workload, database)
