"""
Semantic Layer - Neptune + Titan Embeddings

Complete semantic metadata layer for natural language to SQL query generation.

Quick Start:
    >>> from shared.semantic_layer import setup_semantic_layer, execute_nl_query
    >>>
    >>> # One-time setup
    >>> setup_semantic_layer(
    ...     workload="financial_portfolios",
    ...     database="financial_portfolios_db",
    ...     neptune_endpoint="my-neptune.cluster.amazonaws.com"
    ... )
    >>>
    >>> # Query
    >>> result = execute_nl_query(
    ...     "What is total portfolio value by region?",
    ...     workload="financial_portfolios",
    ...     database="financial_portfolios_db",
    ...     neptune_endpoint="my-neptune.cluster.amazonaws.com",
    ...     athena_database="financial_portfolios_db",
    ...     s3_output_location="s3://my-bucket/athena-results/"
    ... )
    >>> print(result.sql)
    >>> print(result.rows)
"""

from shared.metadata.combiner import MetadataCombiner, combine_metadata
from shared.embeddings.titan_client import TitanEmbeddingsClient
from shared.embeddings.metadata_embedder import MetadataEmbedder, embed_metadata
from shared.neptune.loader import NeptuneLoader
from shared.synodb.setup import ensure_table_exists, create_synodb_table
from shared.synodb.loader import SynoDBLoader, load_seed_queries
from shared.synodb.search import SynoDBSearch, find_similar_queries
from shared.analysis_agent.nl_parser import NLQueryParser, parse_nl_query
from shared.analysis_agent.neptune_search import NeptuneSemanticSearch
from shared.analysis_agent.sql_generator import SQLGenerator, generate_sql
from shared.analysis_agent.executor import QueryExecutor, execute_nl_query


def setup_semantic_layer(
    workload: str,
    database: str,
    neptune_endpoint: str,
    region: str = 'us-east-1',
    clear_existing_graph: bool = False,
    verbose: bool = True
) -> dict:
    """
    Complete one-time setup of semantic layer for a workload.

    This function:
    1. Combines metadata from Glue + semantic.yaml + LF-Tags
    2. Generates Titan embeddings for all entities
    3. Loads graph into Neptune
    4. Creates SynoDB table (if not exists)
    5. Loads seed queries into SynoDB

    Args:
        workload: Workload name (e.g., "financial_portfolios")
        database: Glue database name (e.g., "financial_portfolios_db")
        neptune_endpoint: Neptune cluster endpoint
        region: AWS region
        clear_existing_graph: Whether to clear existing Neptune graph (dangerous!)
        verbose: Print progress

    Returns:
        Dict with setup statistics

    Example:
        >>> from shared.semantic_layer import setup_semantic_layer
        >>> stats = setup_semantic_layer(
        ...     workload="financial_portfolios",
        ...     database="financial_portfolios_db",
        ...     neptune_endpoint="my-neptune.cluster.amazonaws.com",
        ...     verbose=True
        ... )
        >>> print(f"Loaded {stats['table_count']} tables")
        >>> print(f"Generated {stats['embedding_count']} embeddings")
        >>> print(f"Loaded {stats['query_count']} seed queries")
    """
    stats = {
        'table_count': 0,
        'column_count': 0,
        'embedding_count': 0,
        'query_count': 0
    }

    if verbose:
        print(f"Setting up semantic layer for {workload}...")

    # Step 1: Combine metadata
    if verbose:
        print("\n1. Combining metadata from Glue + semantic.yaml + LF-Tags...")

    graph = combine_metadata(workload, database, region=region)
    stats['table_count'] = len(graph.tables)
    stats['column_count'] = sum(len(t.columns) for t in graph.tables)

    if verbose:
        print(f"   ✓ Loaded {stats['table_count']} tables, {stats['column_count']} columns")

    # Step 2: Generate embeddings
    if verbose:
        print("\n2. Generating Titan embeddings...")

    embedded_graph = embed_metadata(graph, region=region, verbose=verbose)

    # Count embeddings
    for table in embedded_graph.tables:
        if table.embedding_vector:
            stats['embedding_count'] += 1
        stats['embedding_count'] += sum(1 for col in table.columns if col.embedding_vector)
        stats['embedding_count'] += sum(1 for term in table.business_terms if term.get('embedding'))
        stats['embedding_count'] += sum(1 for query in table.seed_queries if query.get('embedding'))

    if verbose:
        print(f"   ✓ Generated {stats['embedding_count']} embeddings")

    # Step 3: Load into Neptune
    if verbose:
        print("\n3. Loading graph into Neptune...")

    with NeptuneLoader(neptune_endpoint) as loader:
        loader.load_metadata_graph(
            embedded_graph,
            clear_existing=clear_existing_graph,
            verbose=verbose
        )

    if verbose:
        print(f"   ✓ Loaded graph into Neptune")

    # Step 4: Set up SynoDB
    if verbose:
        print("\n4. Setting up SynoDB...")

    ensure_table_exists(region=region)

    query_count = load_seed_queries(
        metadata=embedded_graph,
        workload=workload,
        region=region,
        verbose=verbose
    )
    stats['query_count'] = query_count

    if verbose:
        print(f"   ✓ Loaded {query_count} seed queries into DynamoDB")

    if verbose:
        print(f"\n✓ Semantic layer ready for {workload}!")
        print(f"\nSetup Statistics:")
        print(f"  Tables: {stats['table_count']}")
        print(f"  Columns: {stats['column_count']}")
        print(f"  Embeddings: {stats['embedding_count']}")
        print(f"  Seed Queries: {stats['query_count']}")

    return stats


__all__ = [
    # Setup
    'setup_semantic_layer',

    # Metadata
    'MetadataCombiner',
    'combine_metadata',

    # Embeddings
    'TitanEmbeddingsClient',
    'MetadataEmbedder',
    'embed_metadata',

    # Neptune
    'NeptuneLoader',

    # SynoDB
    'ensure_table_exists',
    'create_synodb_table',
    'SynoDBLoader',
    'load_seed_queries',
    'SynoDBSearch',
    'find_similar_queries',

    # Analysis Agent
    'NLQueryParser',
    'parse_nl_query',
    'NeptuneSemanticSearch',
    'SQLGenerator',
    'generate_sql',
    'QueryExecutor',
    'execute_nl_query',
]
