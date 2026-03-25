"""
Metadata Embedder

Adds Titan embeddings to unified metadata for semantic search.
Embeds tables, columns, business terms, and queries.
"""

from typing import List, Optional
from shared.schemas.unified_metadata import UnifiedMetadataGraph, UnifiedTable, UnifiedColumn
from shared.embeddings.titan_client import TitanEmbeddingsClient


class MetadataEmbedder:
    """Add Titan embeddings to unified metadata."""

    def __init__(self, region: str = 'us-east-1'):
        """
        Initialize embedder with Titan client.

        Args:
            region: AWS region for Bedrock
        """
        self.titan = TitanEmbeddingsClient(region=region)

    def embed_metadata_graph(
        self,
        metadata: UnifiedMetadataGraph,
        verbose: bool = False
    ) -> UnifiedMetadataGraph:
        """
        Add embeddings to all entities in metadata graph.

        Args:
            metadata: Unified metadata graph (modified in-place)
            verbose: Print progress

        Returns:
            Same metadata graph with embeddings added

        Example:
            >>> from shared.metadata.combiner import combine_metadata
            >>> graph = combine_metadata("financial_portfolios", "financial_portfolios_db")
            >>> embedder = MetadataEmbedder()
            >>> embedded_graph = embedder.embed_metadata_graph(graph)
            >>> embedded_graph.tables[0].embedding_vector is not None
            True
            >>> len(embedded_graph.tables[0].embedding_vector)
            1024
        """
        total_embeddings = 0

        for i, table in enumerate(metadata.tables):
            if verbose:
                print(f"Embedding table {i+1}/{len(metadata.tables)}: {table.name}")

            # Embed table
            self._embed_table(table)
            total_embeddings += 1

            # Embed columns
            for col in table.columns:
                self._embed_column(col, table.name)
                total_embeddings += 1

            # Embed business terms
            for term in table.business_terms:
                self._embed_business_term(term)
                total_embeddings += 1

            # Embed seed queries
            for query in table.seed_queries:
                self._embed_seed_query(query)
                total_embeddings += 1

        # Embed global business terms
        for term in metadata.global_business_terms:
            self._embed_business_term(term)
            total_embeddings += 1

        if verbose:
            print(f"Generated {total_embeddings} embeddings")

        return metadata

    def _embed_table(self, table: UnifiedTable):
        """
        Generate and attach embedding to a table.

        Args:
            table: UnifiedTable (modified in-place)
        """
        # Build rich text representation
        text_parts = [
            f"table: {table.name}",
            f"type: {table.table_type}",
            f"grain: {table.grain}"
        ]

        # Add column names (context)
        if table.columns:
            col_names = [col.name for col in table.columns[:10]]  # Limit to 10
            text_parts.append(f"columns: {', '.join(col_names)}")

        # Add business terms
        if table.business_terms:
            terms = [t.get('term', '') for t in table.business_terms[:5]]
            if terms:
                text_parts.append(f"business terms: {', '.join(terms)}")

        text = ". ".join(text_parts)

        # Generate embedding
        table.embedding_vector = self.titan.generate_embedding(text)

    def _embed_column(self, column: UnifiedColumn, table_name: str):
        """
        Generate and attach embedding to a column.

        Args:
            column: UnifiedColumn (modified in-place)
            table_name: Parent table name for context
        """
        # Build rich text representation
        text_parts = [
            f"column: {column.name}",
            f"table: {table_name}",
            f"role: {column.role}",
            f"type: {column.data_type}"
        ]

        # Add description
        if column.description:
            text_parts.append(column.description)

        # Add business terms (synonyms)
        if column.business_terms:
            text_parts.append(f"also known as: {', '.join(column.business_terms)}")

        # Add aggregation context
        if column.default_aggregation:
            text_parts.append(f"default aggregation: {column.default_aggregation}")

        # Add sample values (helps with semantic understanding)
        if column.sample_values:
            samples = column.sample_values[:3]  # Limit to 3
            text_parts.append(f"example values: {', '.join(str(v) for v in samples)}")

        # Add PII context (important for access control)
        if column.pii_type:
            text_parts.append(f"PII type: {column.pii_type}")

        text = ". ".join(text_parts)

        # Generate embedding
        column.embedding_vector = self.titan.generate_embedding(text)

    def _embed_business_term(self, term: dict):
        """
        Generate and attach embedding to a business term.

        Args:
            term: Business term dict (modified in-place)
        """
        # Build rich text representation
        text_parts = [
            f"business term: {term.get('term', '')}"
        ]

        # Add description
        if term.get('description'):
            text_parts.append(term['description'])

        # Add synonyms
        if term.get('synonyms'):
            text_parts.append(f"synonyms: {', '.join(term['synonyms'])}")

        # Add SQL expression (helps understand calculation)
        if term.get('sql_expression'):
            text_parts.append(f"calculated as: {term['sql_expression']}")

        text = ". ".join(text_parts)

        # Generate and store embedding
        term['embedding'] = self.titan.generate_embedding(text)

    def _embed_seed_query(self, query: dict):
        """
        Generate and attach embedding to a seed query.

        Args:
            query: Seed query dict (modified in-place)
        """
        # Build rich text representation from question + SQL
        text_parts = [
            f"question: {query.get('question', '')}"
        ]

        # Add SQL (helps understand query pattern)
        if query.get('sql'):
            # Truncate SQL to avoid token limit
            sql = query['sql']
            if len(sql) > 500:
                sql = sql[:500] + "..."
            text_parts.append(f"SQL: {sql}")

        # Add explanation
        if query.get('explanation'):
            text_parts.append(query['explanation'])

        text = ". ".join(text_parts)

        # Generate and store embedding
        query['embedding'] = self.titan.generate_embedding(text)

    def embed_table(
        self,
        table: UnifiedTable,
        include_columns: bool = True,
        include_business_terms: bool = True,
        include_seed_queries: bool = True
    ) -> UnifiedTable:
        """
        Embed a single table (convenience method).

        Args:
            table: UnifiedTable to embed (modified in-place)
            include_columns: Whether to embed columns
            include_business_terms: Whether to embed business terms
            include_seed_queries: Whether to embed seed queries

        Returns:
            Same table with embeddings added

        Example:
            >>> embedder = MetadataEmbedder()
            >>> table = UnifiedTable(...)
            >>> embedder.embed_table(table)
            >>> table.embedding_vector is not None
            True
        """
        # Embed table
        self._embed_table(table)

        # Embed columns
        if include_columns:
            for col in table.columns:
                self._embed_column(col, table.name)

        # Embed business terms
        if include_business_terms:
            for term in table.business_terms:
                self._embed_business_term(term)

        # Embed seed queries
        if include_seed_queries:
            for query in table.seed_queries:
                self._embed_seed_query(query)

        return table

    def embed_query_text(self, query_text: str) -> List[float]:
        """
        Generate embedding for a natural language query.

        Args:
            query_text: Natural language query

        Returns:
            1024-dimensional embedding vector

        Example:
            >>> embedder = MetadataEmbedder()
            >>> embedding = embedder.embed_query_text("What is the total portfolio value?")
            >>> len(embedding)
            1024
        """
        # Add context prefix
        text = f"question: {query_text}"
        return self.titan.generate_embedding(text)

    def find_similar_tables(
        self,
        query_text: str,
        metadata: UnifiedMetadataGraph,
        top_k: int = 3
    ) -> List[tuple[str, float]]:
        """
        Find tables most similar to a natural language query.

        Args:
            query_text: Natural language query
            metadata: Unified metadata graph (must have embeddings)
            top_k: Number of top results to return

        Returns:
            List of (table_name, similarity_score) tuples

        Example:
            >>> embedder = MetadataEmbedder()
            >>> graph = embedder.embed_metadata_graph(metadata)
            >>> results = embedder.find_similar_tables(
            ...     "Show me monthly revenue",
            ...     graph,
            ...     top_k=2
            ... )
            >>> len(results)
            2
            >>> results[0][1] > 0.5  # Similarity score > 0.5
            True
        """
        # Generate query embedding
        query_embedding = self.embed_query_text(query_text)

        # Collect table embeddings
        table_embeddings = []
        table_names = []

        for table in metadata.tables:
            if table.embedding_vector:
                table_embeddings.append(table.embedding_vector)
                table_names.append(table.name)

        if not table_embeddings:
            raise ValueError("No table embeddings found in metadata graph")

        # Find most similar
        results = self.titan.find_most_similar(
            query_embedding,
            table_embeddings,
            top_k=top_k
        )

        # Convert indices to table names
        return [(table_names[idx], score) for idx, score in results]

    def find_similar_columns(
        self,
        query_text: str,
        table: UnifiedTable,
        top_k: int = 5
    ) -> List[tuple[str, float]]:
        """
        Find columns most similar to a natural language query.

        Args:
            query_text: Natural language query
            table: UnifiedTable (must have column embeddings)
            top_k: Number of top results to return

        Returns:
            List of (column_name, similarity_score) tuples

        Example:
            >>> embedder = MetadataEmbedder()
            >>> results = embedder.find_similar_columns(
            ...     "revenue",
            ...     table,
            ...     top_k=3
            ... )
            >>> len(results) <= 3
            True
        """
        # Generate query embedding
        query_embedding = self.embed_query_text(query_text)

        # Collect column embeddings
        column_embeddings = []
        column_names = []

        for col in table.columns:
            if col.embedding_vector:
                column_embeddings.append(col.embedding_vector)
                column_names.append(col.name)

        if not column_embeddings:
            raise ValueError(f"No column embeddings found in table '{table.name}'")

        # Find most similar
        results = self.titan.find_most_similar(
            query_embedding,
            column_embeddings,
            top_k=top_k
        )

        # Convert indices to column names
        return [(column_names[idx], score) for idx, score in results]


def embed_metadata(
    metadata: UnifiedMetadataGraph,
    region: str = 'us-east-1',
    verbose: bool = False
) -> UnifiedMetadataGraph:
    """
    Convenience function to embed a metadata graph.

    Args:
        metadata: Unified metadata graph
        region: AWS region for Bedrock
        verbose: Print progress

    Returns:
        Same metadata graph with embeddings added

    Example:
        >>> from shared.metadata.combiner import combine_metadata
        >>> graph = combine_metadata("financial_portfolios", "financial_portfolios_db")
        >>> embedded_graph = embed_metadata(graph, verbose=True)
        >>> embedded_graph.tables[0].embedding_vector is not None
        True
    """
    embedder = MetadataEmbedder(region=region)
    return embedder.embed_metadata_graph(metadata, verbose=verbose)
