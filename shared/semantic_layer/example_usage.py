#!/usr/bin/env python3
"""
Semantic Layer - Example Usage

Demonstrates end-to-end usage of the semantic layer:
1. Setup (one-time)
2. Natural language query
3. SQL generation
4. Execution
5. Results
"""

import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.semantic_layer import (
    setup_semantic_layer,
    execute_nl_query,
    NeptuneSemanticSearch,
    find_similar_queries
)


def example_setup():
    """Example: One-time setup of semantic layer."""
    print("=" * 80)
    print("EXAMPLE 1: Setup Semantic Layer (one-time)")
    print("=" * 80)

    stats = setup_semantic_layer(
        workload="financial_portfolios",
        database="financial_portfolios_db",
        neptune_endpoint="my-neptune.cluster-xyz.us-east-1.neptune.amazonaws.com",
        region="us-east-1",
        verbose=True
    )

    print(f"\n✓ Setup complete!")
    print(f"  - {stats['table_count']} tables loaded")
    print(f"  - {stats['embedding_count']} embeddings generated")
    print(f"  - {stats['query_count']} seed queries stored")


def example_nl_query():
    """Example: Execute natural language query."""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Natural Language Query → SQL → Results")
    print("=" * 80)

    nl_query = "What is the total portfolio value by region?"
    print(f"\nNatural Language Query: {nl_query}")

    # Execute end-to-end
    gen_result, exec_result = execute_nl_query(
        nl_query=nl_query,
        workload="financial_portfolios",
        database="financial_portfolios_db",
        neptune_endpoint="my-neptune.cluster-xyz.us-east-1.neptune.amazonaws.com",
        athena_database="financial_portfolios_db",
        s3_output_location="s3://my-bucket/athena-results/",
        region="us-east-1",
        max_results=100
    )

    # Show generated SQL
    print(f"\nGenerated SQL:")
    print("-" * 80)
    print(gen_result.sql)
    print("-" * 80)

    print(f"\nExplanation: {gen_result.explanation}")
    print(f"Confidence: {gen_result.confidence:.2f}")
    print(f"Tables Used: {', '.join(gen_result.tables_used)}")

    # Show execution results
    print(f"\nExecution Status: {exec_result.status}")
    print(f"Row Count: {exec_result.row_count}")
    print(f"Execution Time: {exec_result.execution_time_ms}ms")
    print(f"From Cache: {exec_result.from_cache}")

    if exec_result.status == 'success':
        print(f"\nResults:")
        print("-" * 80)
        for i, row in enumerate(exec_result.rows[:5], 1):  # First 5 rows
            print(f"{i}. {row}")
        if exec_result.row_count > 5:
            print(f"... and {exec_result.row_count - 5} more rows")


def example_semantic_search():
    """Example: Semantic search for tables."""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Semantic Search for Relevant Tables")
    print("=" * 80)

    nl_query = "Show me customer portfolio performance"
    print(f"\nQuery: {nl_query}")

    search = NeptuneSemanticSearch(
        neptune_endpoint="my-neptune.cluster-xyz.us-east-1.neptune.amazonaws.com",
        region="us-east-1"
    )

    # Find relevant tables
    tables = search.semantic_search_tables(
        nl_query,
        database="financial_portfolios_db",
        top_k=3
    )

    print(f"\nTop 3 Relevant Tables:")
    print("-" * 80)
    for i, table in enumerate(tables, 1):
        print(f"{i}. {table['table_name']} (similarity: {table['similarity']:.4f})")
        print(f"   Type: {table['type']}, Grain: {table['grain']}")

    # Get metadata for top table
    if tables:
        top_table = tables[0]['table_name']
        print(f"\nMetadata for {top_table}:")
        print("-" * 80)

        metadata = search.get_table_metadata(
            database="financial_portfolios_db",
            table_name=top_table
        )

        measures = [c for c in metadata['columns'] if c['role'] == 'measure']
        dimensions = [c for c in metadata['columns'] if c['role'] == 'dimension']

        print(f"Measures ({len(measures)}):")
        for m in measures[:5]:
            print(f"  - {m['name']} ({m['default_aggregation']})")

        print(f"\nDimensions ({len(dimensions)}):")
        for d in dimensions[:5]:
            print(f"  - {d['name']}")

    search.close()


def example_similar_queries():
    """Example: Find similar past queries."""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Find Similar Past Queries")
    print("=" * 80)

    nl_query = "What is the average portfolio return?"
    print(f"\nQuery: {nl_query}")

    similar = find_similar_queries(
        nl_query=nl_query,
        workload="financial_portfolios",
        top_k=3,
        region="us-east-1"
    )

    if similar:
        print(f"\nTop 3 Similar Queries:")
        print("-" * 80)
        for i, query in enumerate(similar, 1):
            print(f"{i}. {query['nl_text']} (similarity: {query['similarity']:.4f})")
            print(f"   SQL: {query['sql'][:100]}...")
            print(f"   Success Count: {query['success_count']}")
            print()
    else:
        print("No similar queries found.")


def example_query_patterns():
    """Example: Common query patterns."""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Common Query Patterns")
    print("=" * 80)

    patterns = [
        ("Aggregation", "What is the total portfolio value?"),
        ("Group By", "Show me revenue by region"),
        ("Time Series", "What is the monthly trend in AUM?"),
        ("Filtering", "Show me portfolios with value > $1M"),
        ("Ranking", "Who are the top 10 customers by assets?"),
        ("Comparison", "Compare this month's revenue to last month"),
        ("Join", "Show me customer names with their portfolio values")
    ]

    print("\nSupported Query Patterns:")
    print("-" * 80)
    for pattern_type, example in patterns:
        print(f"{pattern_type:15} → {example}")


def main():
    """Run all examples."""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "SEMANTIC LAYER - EXAMPLE USAGE" + " " * 27 + "║")
    print("╚" + "=" * 78 + "╝")

    try:
        # Note: These examples assume Neptune and DynamoDB are set up
        # Uncomment the examples you want to run:

        # example_setup()  # Run once to set up semantic layer
        # example_nl_query()  # Execute NL query end-to-end
        # example_semantic_search()  # Search for tables
        # example_similar_queries()  # Find similar past queries
        example_query_patterns()  # Show supported patterns

        print("\n" + "=" * 80)
        print("✓ Examples complete!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
