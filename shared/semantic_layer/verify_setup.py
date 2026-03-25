#!/usr/bin/env python3
"""
Verify Semantic Layer Setup

Comprehensive verification script to check if the semantic layer is properly configured:
1. Metadata files (semantic.yaml)
2. AWS services (Glue, Lake Formation, Bedrock, Neptune, DynamoDB)
3. Embeddings
4. Graph data
5. Query store

Usage:
    python verify_setup.py \
        --workload financial_portfolios \
        --database financial_portfolios_db \
        --neptune-endpoint my-neptune.cluster-xyz.us-east-1.neptune.amazonaws.com

    # Verbose mode (show all checks)
    python verify_setup.py --workload financial_portfolios --database financial_portfolios_db \
        --neptune-endpoint my-neptune.cluster-xyz.us-east-1.neptune.amazonaws.com \
        --verbose
"""

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def check_semantic_yaml(workload: str) -> Tuple[bool, str]:
    """Check if semantic.yaml exists and is valid."""
    try:
        from shared.metadata.semantic_reader import read_semantic_yaml, validate_semantic_yaml

        semantic = read_semantic_yaml(workload)
        validate_semantic_yaml(semantic)

        table_count = len(semantic.get('tables', []))
        return True, f"semantic.yaml found ({table_count} tables)"

    except FileNotFoundError:
        return False, f"semantic.yaml not found for workload '{workload}'"
    except Exception as e:
        return False, f"semantic.yaml validation failed: {e}"


def check_glue_catalog(database: str, region: str) -> Tuple[bool, str]:
    """Check if Glue database exists."""
    try:
        from shared.metadata.glue_fetcher import GlueFetcher

        glue = GlueFetcher(region=region)
        tables = glue.list_tables(database)

        return True, f"Glue database '{database}' found ({len(tables)} tables)"

    except ValueError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Glue catalog check failed: {e}"


def check_lake_formation(database: str, region: str) -> Tuple[bool, str]:
    """Check if Lake Formation LF-Tags are configured."""
    try:
        from shared.metadata.lakeformation_fetcher import LakeFormationFetcher

        lf = LakeFormationFetcher(region=region)
        lf_tags = lf.list_lf_tags()

        required_tags = {'PII_Classification', 'PII_Type', 'Data_Sensitivity'}
        existing_tags = {tag['TagKey'] for tag in lf_tags}

        missing_tags = required_tags - existing_tags

        if missing_tags:
            return False, f"Missing LF-Tags: {', '.join(missing_tags)}"

        return True, f"Lake Formation LF-Tags configured ({len(lf_tags)} tags)"

    except Exception as e:
        return False, f"Lake Formation check failed: {e}"


def check_bedrock_titan(region: str) -> Tuple[bool, str]:
    """Check if Bedrock Titan embeddings are accessible."""
    try:
        from shared.embeddings.titan_client import TitanEmbeddingsClient

        titan = TitanEmbeddingsClient(region=region)
        embedding = titan.generate_embedding("test")

        if len(embedding) == 1024:
            return True, "Bedrock Titan embeddings accessible (1024 dims)"
        else:
            return False, f"Unexpected embedding dimension: {len(embedding)}"

    except Exception as e:
        return False, f"Bedrock Titan check failed: {e}"


def check_neptune_connection(neptune_endpoint: str) -> Tuple[bool, str]:
    """Check if Neptune cluster is accessible."""
    try:
        from gremlin_python.driver import client as gremlin_client

        gremlin = gremlin_client.Client(
            f'wss://{neptune_endpoint}:8182/gremlin',
            'g'
        )

        vertex_count = gremlin.submit("g.V().count()").all().result()[0]
        gremlin.close()

        return True, f"Neptune cluster accessible ({vertex_count} vertices)"

    except Exception as e:
        return False, f"Neptune connection failed: {e}"


def check_neptune_graph(neptune_endpoint: str, database: str) -> Tuple[bool, str]:
    """Check if metadata graph is loaded in Neptune."""
    try:
        from gremlin_python.driver import client as gremlin_client

        gremlin = gremlin_client.Client(
            f'wss://{neptune_endpoint}:8182/gremlin',
            'g'
        )

        # Check for database vertex
        db_vertices = gremlin.submit(
            "g.V().hasLabel('database').has('name', db_name).count()",
            {'db_name': database}
        ).all().result()[0]

        if db_vertices == 0:
            gremlin.close()
            return False, f"Database '{database}' not found in Neptune graph"

        # Check for table vertices
        table_count = gremlin.submit(
            "g.V().hasLabel('table').has('database', db_name).count()",
            {'db_name': database}
        ).all().result()[0]

        # Check for column vertices
        column_count = gremlin.submit(
            "g.V().hasLabel('column').has('database', db_name).count()",
            {'db_name': database}
        ).all().result()[0]

        gremlin.close()

        return True, f"Graph loaded ({table_count} tables, {column_count} columns)"

    except Exception as e:
        return False, f"Neptune graph check failed: {e}"


def check_synodb(region: str) -> Tuple[bool, str]:
    """Check if SynoDB (DynamoDB) table exists."""
    try:
        from shared.synodb.setup import get_table_info

        info = get_table_info(region=region)

        if info['TableStatus'] != 'ACTIVE':
            return False, f"SynoDB table not active: {info['TableStatus']}"

        return True, f"SynoDB table active ({info['ItemCount']} queries)"

    except Exception as e:
        return False, f"SynoDB check failed: {e}"


def check_synodb_queries(workload: str, region: str) -> Tuple[bool, str]:
    """Check if seed queries are loaded in SynoDB."""
    try:
        from shared.synodb.search import SynoDBSearch

        search = SynoDBSearch(region=region)
        queries = search.get_most_successful_queries(workload, top_k=10)

        if not queries:
            return False, f"No queries found for workload '{workload}'"

        return True, f"Seed queries loaded ({len(queries)} found)"

    except Exception as e:
        return False, f"SynoDB queries check failed: {e}"


def run_verification(
    workload: str,
    database: str,
    neptune_endpoint: str,
    region: str,
    verbose: bool
) -> Tuple[int, int]:
    """
    Run all verification checks.

    Returns:
        (passed_count, total_count)
    """
    checks = [
        ("Semantic YAML", lambda: check_semantic_yaml(workload)),
        ("Glue Catalog", lambda: check_glue_catalog(database, region)),
        ("Lake Formation", lambda: check_lake_formation(database, region)),
        ("Bedrock Titan", lambda: check_bedrock_titan(region)),
        ("Neptune Connection", lambda: check_neptune_connection(neptune_endpoint)),
        ("Neptune Graph", lambda: check_neptune_graph(neptune_endpoint, database)),
        ("SynoDB Table", lambda: check_synodb(region)),
        ("SynoDB Queries", lambda: check_synodb_queries(workload, region)),
    ]

    passed = 0
    failed = 0

    print("\n" + "=" * 80)
    print("SEMANTIC LAYER VERIFICATION")
    print("=" * 80)
    print(f"Workload: {workload}")
    print(f"Database: {database}")
    print(f"Neptune: {neptune_endpoint}")
    print(f"Region: {region}")
    print("=" * 80)

    for check_name, check_func in checks:
        try:
            success, message = check_func()

            if success:
                status = "✓ PASS"
                passed += 1
            else:
                status = "✗ FAIL"
                failed += 1

            if verbose or not success:
                print(f"{status:8} {check_name:25} {message}")

        except Exception as e:
            print(f"✗ FAIL   {check_name:25} Unexpected error: {e}")
            failed += 1

    print("=" * 80)
    print(f"Results: {passed} passed, {failed} failed (total: {len(checks)})")
    print("=" * 80)

    return passed, len(checks)


def main():
    parser = argparse.ArgumentParser(
        description='Verify semantic layer setup',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--workload',
        required=True,
        help='Workload name'
    )

    parser.add_argument(
        '--database',
        required=True,
        help='Glue database name'
    )

    parser.add_argument(
        '--neptune-endpoint',
        required=True,
        help='Neptune cluster endpoint'
    )

    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show all checks (including passed)'
    )

    args = parser.parse_args()

    # Run verification
    try:
        passed, total = run_verification(
            workload=args.workload,
            database=args.database,
            neptune_endpoint=args.neptune_endpoint,
            region=args.region,
            verbose=args.verbose
        )

        if passed == total:
            print("\n✓ All checks passed! Semantic layer is ready.")
            sys.exit(0)
        else:
            print(f"\n✗ {total - passed} check(s) failed. See errors above.")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Verification failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
