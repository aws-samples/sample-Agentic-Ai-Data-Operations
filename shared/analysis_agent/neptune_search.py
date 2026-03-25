"""
Neptune Semantic Search

Find relevant tables and columns using Titan embeddings + Neptune graph traversal.
"""

from typing import List, Dict, Any, Optional, Tuple
from gremlin_python.driver import client as gremlin_client
from shared.embeddings.titan_client import TitanEmbeddingsClient
from shared.schemas.neptune_schema import get_vertex_id


class NeptuneSemanticSearch:
    """Semantic search on Neptune graph using embeddings."""

    def __init__(
        self,
        neptune_endpoint: str,
        region: str = 'us-east-1'
    ):
        """
        Initialize Neptune semantic search.

        Args:
            neptune_endpoint: Neptune cluster endpoint
            region: AWS region for Titan embeddings
        """
        self.neptune_endpoint = neptune_endpoint
        self.region = region

        self.gremlin = gremlin_client.Client(
            f'wss://{neptune_endpoint}:8182/gremlin',
            'g'
        )

        self.titan = TitanEmbeddingsClient(region=region)

    def semantic_search_tables(
        self,
        nl_query: str,
        database: Optional[str] = None,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find relevant tables using semantic search.

        Args:
            nl_query: Natural language query
            database: Optional database filter
            top_k: Number of top results

        Returns:
            List of tables with similarity scores

        Example:
            >>> search = NeptuneSemanticSearch("my-neptune.cluster.amazonaws.com")
            >>> results = search.semantic_search_tables("Show me revenue by region")
            >>> len(results) <= 3
            True
            >>> 'similarity' in results[0]
            True
        """
        # 1. Generate query embedding
        query_embedding = self.titan.generate_embedding(f"query: {nl_query}")

        # 2. Fetch all table vertices (with embeddings)
        if database:
            query = """
            g.V().hasLabel('table').has('database', db_name).valueMap(true)
            """
            params = {'db_name': database}
        else:
            query = "g.V().hasLabel('table').valueMap(true)"
            params = {}

        try:
            tables = self.gremlin.submit(query, params).all().result()
        except Exception as e:
            print(f"Error querying Neptune: {e}")
            return []

        # 3. Compute cosine similarity
        similarities: List[Tuple[Dict, float]] = []

        for table_vertex in tables:
            # Extract properties (Neptune returns lists for multi-valued properties)
            table_props = self._flatten_properties(table_vertex)

            embedding_str = table_props.get('embedding', '')
            if not embedding_str:
                continue

            # Parse embedding (stored as comma-separated string)
            try:
                table_embedding = [float(x) for x in embedding_str.split(',')]
            except (ValueError, AttributeError):
                continue

            # Compute similarity
            similarity = self.titan.cosine_similarity(query_embedding, table_embedding)

            similarities.append((table_props, similarity))

        # 4. Sort and return top_k
        similarities.sort(key=lambda x: x[1], reverse=True)

        results = []
        for table_props, similarity in similarities[:top_k]:
            results.append({
                'table_name': table_props.get('name', ''),
                'database': table_props.get('database', ''),
                'type': table_props.get('type', ''),
                'grain': table_props.get('grain', ''),
                'similarity': round(similarity, 4)
            })

        return results

    def get_table_metadata(
        self,
        database: str,
        table_name: str
    ) -> Dict[str, Any]:
        """
        Get full metadata for a table from Neptune.

        Args:
            database: Database name
            table_name: Table name

        Returns:
            Table metadata with columns, relationships, etc.

        Example:
            >>> search = NeptuneSemanticSearch("my-neptune.cluster.amazonaws.com")
            >>> metadata = search.get_table_metadata("financial_portfolios_db", "positions")
            >>> 'columns' in metadata
            True
        """
        table_id = get_vertex_id('table', database=database, table=table_name)

        # 1. Get table properties
        try:
            table_vertex = self.gremlin.submit(
                "g.V(table_id).valueMap(true)",
                {'table_id': table_id}
            ).all().result()

            if not table_vertex:
                raise ValueError(f"Table '{database}.{table_name}' not found in Neptune")

            table_props = self._flatten_properties(table_vertex[0])

        except Exception as e:
            raise ValueError(f"Error fetching table metadata: {e}") from e

        # 2. Get columns
        columns = self._get_table_columns(table_id)

        # 3. Get relationships (FK edges)
        relationships = self._get_table_relationships(table_id)

        return {
            'table_name': table_props.get('name', ''),
            'database': table_props.get('database', ''),
            'type': table_props.get('type', ''),
            'grain': table_props.get('grain', ''),
            'primary_key': table_props.get('primary_key', '').split(',') if table_props.get('primary_key') else [],
            'location': table_props.get('location', ''),
            'format': table_props.get('format', ''),
            'columns': columns,
            'relationships': relationships
        }

    def _get_table_columns(self, table_id: str) -> List[Dict[str, Any]]:
        """Get all columns for a table."""
        try:
            column_vertices = self.gremlin.submit(
                """
                g.V(table_id)
                  .outE('has_column')
                  .inV()
                  .valueMap(true)
                """,
                {'table_id': table_id}
            ).all().result()

            columns = []
            for col_vertex in column_vertices:
                col_props = self._flatten_properties(col_vertex)

                columns.append({
                    'name': col_props.get('name', ''),
                    'data_type': col_props.get('data_type', ''),
                    'role': col_props.get('role', ''),
                    'description': col_props.get('description', ''),
                    'is_partition_key': col_props.get('is_partition_key', False),
                    'is_nullable': col_props.get('is_nullable', True),
                    'default_aggregation': col_props.get('default_aggregation', ''),
                    'pii_classification': col_props.get('pii_classification', ''),
                    'pii_type': col_props.get('pii_type', ''),
                    'data_sensitivity': col_props.get('data_sensitivity', ''),
                    'is_foreign_key': col_props.get('is_foreign_key', False),
                    'references': col_props.get('references', '')
                })

            return columns

        except Exception as e:
            print(f"Error fetching columns: {e}")
            return []

    def _get_table_relationships(self, table_id: str) -> List[Dict[str, Any]]:
        """Get FK relationships for a table."""
        try:
            # Get outgoing FK edges (this table references others)
            fk_edges = self.gremlin.submit(
                """
                g.V(table_id)
                  .outE('has_column')
                  .inV()
                  .has('is_foreign_key', true)
                  .valueMap('name', 'references')
                """,
                {'table_id': table_id}
            ).all().result()

            relationships = []
            for fk_vertex in fk_edges:
                fk_props = self._flatten_properties(fk_vertex)
                references = fk_props.get('references', '')

                if references:
                    target_table, target_column = references.split('.') if '.' in references else (references, '')

                    relationships.append({
                        'type': 'foreign_key',
                        'source_column': fk_props.get('name', ''),
                        'target_table': target_table,
                        'target_column': target_column
                    })

            return relationships

        except Exception as e:
            print(f"Error fetching relationships: {e}")
            return []

    def get_join_path(
        self,
        database: str,
        source_table: str,
        target_table: str,
        max_hops: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find FK join path between two tables.

        Args:
            database: Database name
            source_table: Source table name
            target_table: Target table name
            max_hops: Maximum number of joins allowed

        Returns:
            List of join steps

        Example:
            >>> search = NeptuneSemanticSearch("my-neptune.cluster.amazonaws.com")
            >>> path = search.get_join_path("financial_portfolios_db", "positions", "portfolios")
            >>> len(path) >= 1
            True
        """
        source_id = get_vertex_id('table', database=database, table=source_table)
        target_id = get_vertex_id('table', database=database, table=target_table)

        try:
            # Traverse FK edges to find path
            path_query = f"""
            g.V(source_id)
              .repeat(
                outE('has_column')
                  .inV()
                  .has('is_foreign_key', true)
                  .outE('references')
                  .inV()
                  .inE('has_column')
                  .outV()
              )
              .until(hasId(target_id))
              .limit(1)
              .path()
              .by(valueMap(true))
            """

            path_result = self.gremlin.submit(
                path_query,
                {'source_id': source_id, 'target_id': target_id}
            ).all().result()

            if not path_result:
                return []

            # Parse path (alternates between table and column vertices)
            path_elements = path_result[0].objects

            join_steps = []
            for i in range(0, len(path_elements) - 1, 2):
                # Extract join information
                source_vertex = self._flatten_properties(path_elements[i])
                fk_column_vertex = self._flatten_properties(path_elements[i + 1]) if i + 1 < len(path_elements) else {}

                join_steps.append({
                    'from_table': source_vertex.get('name', ''),
                    'from_column': fk_column_vertex.get('name', ''),
                    'to_table': fk_column_vertex.get('references', '').split('.')[0] if fk_column_vertex.get('references') else '',
                    'to_column': fk_column_vertex.get('references', '').split('.')[1] if fk_column_vertex.get('references') and '.' in fk_column_vertex.get('references') else ''
                })

            return join_steps

        except Exception as e:
            print(f"Error finding join path: {e}")
            return []

    def list_measures(self, database: str, table_name: str) -> List[str]:
        """Get all measure columns in a table."""
        return self._list_columns_by_role(database, table_name, 'measure')

    def list_dimensions(self, database: str, table_name: str) -> List[str]:
        """Get all dimension columns in a table."""
        return self._list_columns_by_role(database, table_name, 'dimension')

    def _list_columns_by_role(
        self,
        database: str,
        table_name: str,
        role: str
    ) -> List[str]:
        """List columns by role."""
        table_id = get_vertex_id('table', database=database, table=table_name)

        try:
            columns = self.gremlin.submit(
                """
                g.V(table_id)
                  .outE('has_column')
                  .inV()
                  .has('role', role)
                  .values('name')
                """,
                {'table_id': table_id, 'role': role}
            ).all().result()

            return columns

        except Exception as e:
            print(f"Error listing {role} columns: {e}")
            return []

    def _flatten_properties(self, vertex_map: Dict) -> Dict[str, Any]:
        """
        Flatten Neptune vertex properties (Neptune returns lists for multi-valued properties).

        Args:
            vertex_map: Raw vertex map from Neptune

        Returns:
            Flattened dict with scalar values
        """
        flattened = {}

        for key, value in vertex_map.items():
            if key in ['id', 'label']:
                flattened[key] = value
            elif isinstance(value, list) and value:
                # Take first value
                flattened[key] = value[0]
            else:
                flattened[key] = value

        return flattened

    def close(self):
        """Close Neptune client connection."""
        self.gremlin.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
