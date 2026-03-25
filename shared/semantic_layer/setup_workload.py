#!/usr/bin/env python3
"""
Setup Semantic Layer for a Workload

Command-line tool to initialize the complete semantic layer:
1. Combine metadata (Glue + semantic.yaml + LF-Tags)
2. Generate Titan embeddings
3. Load into Neptune graph database
4. Create SynoDB table and load seed queries

Usage:
    python setup_workload.py \
        --workload financial_portfolios \
        --database financial_portfolios_db \
        --neptune-endpoint my-neptune.cluster-xyz.us-east-1.neptune.amazonaws.com \
        --region us-east-1

    # Clear existing graph before loading (dangerous!)
    python setup_workload.py \
        --workload financial_portfolios \
        --database financial_portfolios_db \
        --neptune-endpoint my-neptune.cluster-xyz.us-east-1.neptune.amazonaws.com \
        --clear-graph

    # Quiet mode (no progress output)
    python setup_workload.py \
        --workload financial_portfolios \
        --database financial_portfolios_db \
        --neptune-endpoint my-neptune.cluster-xyz.us-east-1.neptune.amazonaws.com \
        --quiet
"""

import argparse
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.semantic_layer import setup_semantic_layer


def main():
    parser = argparse.ArgumentParser(
        description='Setup semantic layer for a workload',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--workload',
        required=True,
        help='Workload name (e.g., financial_portfolios)'
    )

    parser.add_argument(
        '--database',
        required=True,
        help='Glue database name (e.g., financial_portfolios_db)'
    )

    parser.add_argument(
        '--neptune-endpoint',
        required=True,
        help='Neptune cluster endpoint (without protocol/port)'
    )

    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )

    parser.add_argument(
        '--clear-graph',
        action='store_true',
        help='Clear existing Neptune graph before loading (WARNING: destructive!)'
    )

    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Quiet mode (no progress output)'
    )

    args = parser.parse_args()

    # Confirm if clearing graph
    if args.clear_graph:
        print("⚠️  WARNING: You are about to clear the existing Neptune graph!")
        response = input("Type 'yes' to confirm: ")
        if response.lower() != 'yes':
            print("Aborted.")
            sys.exit(1)

    # Run setup
    try:
        stats = setup_semantic_layer(
            workload=args.workload,
            database=args.database,
            neptune_endpoint=args.neptune_endpoint,
            region=args.region,
            clear_existing_graph=args.clear_graph,
            verbose=not args.quiet
        )

        if args.quiet:
            print(f"✓ Semantic layer setup complete for {args.workload}")
            print(f"Tables: {stats['table_count']}, "
                  f"Columns: {stats['column_count']}, "
                  f"Embeddings: {stats['embedding_count']}, "
                  f"Queries: {stats['query_count']}")

        sys.exit(0)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        if not args.quiet:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
