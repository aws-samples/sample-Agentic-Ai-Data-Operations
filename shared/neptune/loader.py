"""
Neptune Graph Loader

Loads unified metadata into Amazon Neptune graph database using Gremlin.
Creates vertices (database, table, column, business_term) and edges (relationships).
"""

from typing import Dict, List, Optional, Any
from gremlin_python.driver import client as gremlin_client
from gremlin_python.driver.protocol import GremlinServerError
from shared.schemas.unified_metadata import UnifiedMetadataGraph, UnifiedTable, UnifiedColumn
from shared.schemas.neptune_schema import get_vertex_id


class NeptuneLoader:
    """Load unified metadata into Neptune graph database."""

    def __init__(self, neptune_endpoint: str):
        """
        Initialize Neptune client.

        Args:
            neptune_endpoint: Neptune cluster endpoint (without protocol/port)
                             e.g., "my-cluster.cluster-xyz.us-east-1.neptune.amazonaws.com"
        """
        self.neptune_endpoint = neptune_endpoint
        self.client = gremlin_client.Client(
            f'wss://{neptune_endpoint}:8182/gremlin',
            'g'
        )

    def load_metadata_graph(
        self,
        metadata: UnifiedMetadataGraph,
        clear_existing: bool = False,
        verbose: bool = False
    ):
        """
        Load entire metadata graph into Neptune.

        Args:
            metadata: Unified metadata graph with embeddings
            clear_existing: Whether to clear existing graph first (dangerous!)
            verbose: Print progress

        Example:
            >>> from shared.metadata.combiner import combine_metadata
            >>> from shared.embeddings.metadata_embedder import embed_metadata
            >>> graph = combine_metadata("financial_portfolios", "financial_portfolios_db")
            >>> embedded_graph = embed_metadata(graph)
            >>> loader = NeptuneLoader("my-neptune.cluster-xyz.us-east-1.neptune.amazonaws.com")
            >>> loader.load_metadata_graph(embedded_graph, verbose=True)
        """
        if clear_existing:
            if verbose:
                print("WARNING: Clearing existing graph...")
            self._clear_graph()

        # Load in order: databases → tables → columns → business terms → relationships

        # 1. Create database vertices
        if verbose:
            print(f"Loading database: {metadata.database}")
        self._create_database_vertex(metadata.database, metadata.workload)

        # 2. Create table vertices and edges
        for i, table in enumerate(metadata.tables):
            if verbose:
                print(f"Loading table {i+1}/{len(metadata.tables)}: {table.name}")

            self._create_table_vertex(table, metadata.database)
            self._create_database_table_edge(metadata.database, table.name)

        # 3. Create column vertices and edges
        for table in metadata.tables:
            if verbose:
                print(f"Loading columns for table: {table.name}")

            for col in table.columns:
                self._create_column_vertex(col, metadata.database, table.name)
                self._create_table_column_edge(metadata.database, table.name, col.name)

        # 4. Create FK edges
        for table in metadata.tables:
            for col in table.columns:
                if col.is_foreign_key and col.references:
                    self._create_fk_edge(metadata.database, table.name, col.name, col.references)

        # 5. Create business term vertices and edges
        if verbose:
            print("Loading business terms...")

        # Table-level business terms
        for table in metadata.tables:
            for term in table.business_terms:
                self._create_business_term_vertex(term)

                # Link columns to business terms
                for col in table.columns:
                    if term.get('term') in col.business_terms:
                        self._create_column_term_edge(
                            metadata.database,
                            table.name,
                            col.name,
                            term['term']
                        )

        # Global business terms
        for term in metadata.global_business_terms:
            self._create_business_term_vertex(term)

        if verbose:
            print(f"Successfully loaded {len(metadata.tables)} tables into Neptune")

    def _clear_graph(self):
        """Clear all vertices and edges from graph (USE WITH CAUTION!)."""
        self.client.submit("g.V().drop()").all().result()

    def _create_database_vertex(self, database: str, workload: Optional[str] = None):
        """
        Create or update database vertex.

        Args:
            database: Database name
            workload: Optional workload name
        """
        db_id = get_vertex_id('database', database_name=database)

        query = """
        g.V().hasLabel('database').has('name', db_name)
          .fold()
          .coalesce(
            unfold(),
            addV('database')
              .property(id, db_id)
              .property('name', db_name)
              .property('workload', workload)
          )
        """

        self.client.submit(
            query,
            {
                'db_id': db_id,
                'db_name': database,
                'workload': workload or ''
            }
        ).all().result()

    def _create_table_vertex(self, table: UnifiedTable, database: str):
        """
        Create table vertex.

        Args:
            table: UnifiedTable to create
            database: Parent database name
        """
        table_id = get_vertex_id('table', database_name=database, table_name=table.name)

        # Convert embedding to string for storage
        embedding_str = ','.join(str(f) for f in table.embedding_vector) if table.embedding_vector else ''

        query = """
        g.addV('table')
          .property(id, table_id)
          .property('name', table_name)
          .property('database', db_name)
          .property('type', table_type)
          .property('grain', grain)
          .property('primary_key', pk)
          .property('location', location)
          .property('format', format)
          .property('embedding', embedding)
        """

        self.client.submit(
            query,
            {
                'table_id': table_id,
                'table_name': table.name,
                'db_name': database,
                'table_type': table.table_type,
                'grain': table.grain,
                'pk': ','.join(table.primary_key),
                'location': table.location or '',
                'format': table.format or '',
                'embedding': embedding_str
            }
        ).all().result()

    def _create_database_table_edge(self, database: str, table: str):
        """
        Create edge: database → table.

        Args:
            database: Database name
            table: Table name
        """
        db_id = get_vertex_id('database', database_name=database)
        table_id = get_vertex_id('table', database_name=database, table_name=table)

        query = """
        g.V(db_id)
          .addE('contains')
          .to(g.V(table_id))
        """

        self.client.submit(
            query,
            {'db_id': db_id, 'table_id': table_id}
        ).all().result()

    def _create_column_vertex(self, column: UnifiedColumn, database: str, table: str):
        """
        Create column vertex.

        Args:
            column: UnifiedColumn to create
            database: Parent database name
            table: Parent table name
        """
        col_id = get_vertex_id('column', database_name=database, table_name=table, column_name=column.name)

        # Convert embedding to string
        embedding_str = ','.join(str(f) for f in column.embedding_vector) if column.embedding_vector else ''

        query = """
        g.addV('column')
          .property(id, col_id)
          .property('name', col_name)
          .property('database', db_name)
          .property('table', table_name)
          .property('data_type', data_type)
          .property('role', role)
          .property('description', description)
          .property('is_partition_key', is_partition)
          .property('is_nullable', is_nullable)
          .property('default_aggregation', aggregation)
          .property('pii_classification', pii_class)
          .property('pii_type', pii_type)
          .property('data_sensitivity', sensitivity)
          .property('is_foreign_key', is_fk)
          .property('references', references)
          .property('embedding', embedding)
        """

        self.client.submit(
            query,
            {
                'col_id': col_id,
                'col_name': column.name,
                'db_name': database,
                'table_name': table,
                'data_type': column.data_type,
                'role': column.role,
                'description': column.description,
                'is_partition': column.is_partition_key,
                'is_nullable': column.is_nullable,
                'aggregation': column.default_aggregation or '',
                'pii_class': column.pii_classification or '',
                'pii_type': column.pii_type or '',
                'sensitivity': column.data_sensitivity or '',
                'is_fk': column.is_foreign_key,
                'references': column.references or '',
                'embedding': embedding_str
            }
        ).all().result()

    def _create_table_column_edge(self, database: str, table: str, column: str):
        """
        Create edge: table → column.

        Args:
            database: Database name
            table: Table name
            column: Column name
        """
        table_id = get_vertex_id('table', database_name=database, table_name=table)
        col_id = get_vertex_id('column', database_name=database, table_name=table, column_name=column)

        query = """
        g.V(table_id)
          .addE('has_column')
          .to(g.V(col_id))
        """

        self.client.submit(
            query,
            {'table_id': table_id, 'col_id': col_id}
        ).all().result()

    def _create_fk_edge(self, database: str, table: str, column: str, references: str):
        """
        Create FK edge: column → referenced_column.

        Args:
            database: Database name
            table: Source table name
            column: Source column name
            references: Target reference (format: "target_table.target_column")
        """
        source_col_id = get_vertex_id('column', database_name=database, table_name=table, column_name=column)

        # Parse target reference
        target_table, target_column = references.split('.')
        target_col_id = get_vertex_id('column', database_name=database, table_name=target_table, column=target_column)

        query = """
        g.V(source_id)
          .addE('references')
          .to(g.V(target_id))
          .property('relationship_type', 'foreign_key')
        """

        self.client.submit(
            query,
            {'source_id': source_col_id, 'target_id': target_col_id}
        ).all().result()

    def _create_business_term_vertex(self, term: Dict[str, Any]):
        """
        Create or update business term vertex.

        Args:
            term: Business term dict with 'term', 'description', 'synonyms', 'sql_expression', 'embedding'
        """
        term_name = term.get('term', '')
        if not term_name:
            return

        term_id = get_vertex_id('business_term', term_name=term_name)

        # Convert embedding to string
        embedding = term.get('embedding', [])
        embedding_str = ','.join(str(f) for f in embedding) if embedding else ''

        # Convert synonyms list to string
        synonyms = term.get('synonyms', [])
        synonyms_str = ','.join(synonyms) if synonyms else ''

        query = """
        g.V().hasLabel('business_term').has('term', term_name)
          .fold()
          .coalesce(
            unfold(),
            addV('business_term')
              .property(id, term_id)
              .property('term', term_name)
              .property('description', description)
              .property('synonyms', synonyms)
              .property('sql_expression', sql_expr)
              .property('embedding', embedding)
          )
        """

        self.client.submit(
            query,
            {
                'term_id': term_id,
                'term_name': term_name,
                'description': term.get('description', ''),
                'synonyms': synonyms_str,
                'sql_expr': term.get('sql_expression', ''),
                'embedding': embedding_str
            }
        ).all().result()

    def _create_column_term_edge(self, database: str, table: str, column: str, term: str):
        """
        Create edge: column → business_term.

        Args:
            database: Database name
            table: Table name
            column: Column name
            term: Business term name
        """
        col_id = get_vertex_id('column', database_name=database, table_name=table, column_name=column)
        term_id = get_vertex_id('business_term', term_name=term)

        query = """
        g.V(col_id)
          .addE('described_by')
          .to(g.V(term_id))
        """

        self.client.submit(
            query,
            {'col_id': col_id, 'term_id': term_id}
        ).all().result()

    def load_table(self, table: UnifiedTable, database: str, verbose: bool = False):
        """
        Load a single table into Neptune (convenience method).

        Args:
            table: UnifiedTable to load
            database: Parent database name
            verbose: Print progress

        Example:
            >>> loader = NeptuneLoader("my-neptune.cluster-xyz.us-east-1.neptune.amazonaws.com")
            >>> loader.load_table(table, "financial_portfolios_db")
        """
        if verbose:
            print(f"Loading table: {table.name}")

        # Create database if not exists
        self._create_database_vertex(database)

        # Create table
        self._create_table_vertex(table, database)
        self._create_database_table_edge(database, table.name)

        # Create columns
        for col in table.columns:
            self._create_column_vertex(col, database, table.name)
            self._create_table_column_edge(database, table.name, col.name)

        # Create FK edges
        for col in table.columns:
            if col.is_foreign_key and col.references:
                self._create_fk_edge(database, table.name, col.name, col.references)

        # Create business terms
        for term in table.business_terms:
            self._create_business_term_vertex(term)

            for col in table.columns:
                if term.get('term') in col.business_terms:
                    self._create_column_term_edge(database, table.name, col.name, term['term'])

        if verbose:
            print(f"Successfully loaded table: {table.name}")

    def close(self):
        """Close Neptune client connection."""
        self.client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
