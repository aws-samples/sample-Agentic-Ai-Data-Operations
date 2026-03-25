#!/usr/bin/env python3
"""
Load Metadata to Neptune - Complete 7-Step Process

This script performs the complete semantic layer setup:
1. Read semantic.yaml
2. Fetch metadata from Glue Catalog
3. Fetch LF-Tags from Lake Formation
4. Generate Titan embeddings (1024-dim vectors)
5. Load graph into Neptune
6. Create DynamoDB table
7. Load seed queries

Usage:
    python load_to_neptune.py \
        --workload financial_portfolios \
        --database financial_portfolios_db \
        --neptune-endpoint my-cluster.cluster-xyz.us-east-1.neptune.amazonaws.com \
        --region us-east-1

    # With options
    python load_to_neptune.py \
        --workload financial_portfolios \
        --database financial_portfolios_db \
        --neptune-endpoint my-cluster.cluster-xyz.us-east-1.neptune.amazonaws.com \
        --region us-east-1 \
        --clear-graph \
        --dry-run
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Any

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.metadata.combiner import MetadataCombiner
from shared.embeddings.titan_client import TitanEmbeddingsClient
from shared.embeddings.metadata_embedder import MetadataEmbedder
from shared.neptune.loader import NeptuneLoader
from shared.synodb.setup import ensure_table_exists, create_synodb_table
from shared.synodb.loader import SynoDBLoader
from shared.schemas.unified_metadata import UnifiedMetadataGraph


class NeptuneLoadingPipeline:
    """Complete pipeline to load metadata into Neptune."""

    def __init__(
        self,
        workload: str,
        database: str,
        neptune_endpoint: str,
        region: str = 'us-east-1',
        dry_run: bool = False
    ):
        self.workload = workload
        self.database = database
        self.neptune_endpoint = neptune_endpoint
        self.region = region
        self.dry_run = dry_run

        # Statistics
        self.stats = {
            'tables': 0,
            'columns': 0,
            'relationships': 0,
            'business_terms': 0,
            'embeddings': 0,
            'seed_queries': 0,
            'neptune_vertices': 0,
            'neptune_edges': 0
        }

    def run(self, clear_graph: bool = False) -> Dict[str, Any]:
        """
        Run complete 7-step pipeline.

        Returns:
            Dict with statistics
        """
        print("\n" + "=" * 80)
        print("NEPTUNE METADATA LOADING PIPELINE")
        print("=" * 80)
        print(f"Workload:        {self.workload}")
        print(f"Database:        {self.database}")
        print(f"Neptune:         {self.neptune_endpoint}")
        print(f"Region:          {self.region}")
        print(f"Dry Run:         {self.dry_run}")
        print(f"Clear Graph:     {clear_graph}")
        print("=" * 80)

        if self.dry_run:
            print("\n⚠️  DRY RUN MODE - No data will be written to Neptune/DynamoDB")

        try:
            # Step 1: Read semantic.yaml
            print("\n" + "─" * 80)
            print("STEP 1: Read semantic.yaml")
            print("─" * 80)
            semantic = self._step1_read_semantic()

            # Step 2: Fetch Glue metadata
            print("\n" + "─" * 80)
            print("STEP 2: Fetch metadata from Glue Catalog")
            print("─" * 80)
            glue_metadata = self._step2_fetch_glue(semantic)

            # Step 3: Fetch LF-Tags
            print("\n" + "─" * 80)
            print("STEP 3: Fetch LF-Tags from Lake Formation")
            print("─" * 80)
            lf_tags = self._step3_fetch_lf_tags(semantic)

            # Step 4: Combine metadata + generate embeddings
            print("\n" + "─" * 80)
            print("STEP 4: Combine metadata & generate Titan embeddings")
            print("─" * 80)
            unified_graph = self._step4_combine_and_embed()

            # Step 5: Load into Neptune
            print("\n" + "─" * 80)
            print("STEP 5: Load graph into Neptune")
            print("─" * 80)
            self._step5_load_neptune(unified_graph, clear_graph)

            # Step 6: Create DynamoDB table
            print("\n" + "─" * 80)
            print("STEP 6: Create DynamoDB table (SynoDB)")
            print("─" * 80)
            self._step6_create_dynamodb()

            # Step 7: Load seed queries
            print("\n" + "─" * 80)
            print("STEP 7: Load seed queries into SynoDB")
            print("─" * 80)
            self._step7_load_queries(unified_graph)

            # Summary
            self._print_summary()

            return self.stats

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def _step1_read_semantic(self) -> Dict[str, Any]:
        """Step 1: Read semantic.yaml"""
        from shared.metadata.semantic_reader import read_semantic_yaml, validate_semantic_yaml

        start = time.time()

        semantic_path = Path(f"workloads/{self.workload}/config/semantic.yaml")
        print(f"Reading: {semantic_path}")

        if not semantic_path.exists():
            raise FileNotFoundError(
                f"semantic.yaml not found at {semantic_path}\n"
                f"Expected path: workloads/{self.workload}/config/semantic.yaml"
            )

        semantic = read_semantic_yaml(self.workload)
        validate_semantic_yaml(semantic)

        self.stats['tables'] = len(semantic.get('tables', []))

        elapsed = time.time() - start
        print(f"✓ Read {self.stats['tables']} tables from semantic.yaml ({elapsed:.2f}s)")

        # Show table names
        table_names = [t['name'] for t in semantic.get('tables', [])]
        print(f"  Tables: {', '.join(table_names)}")

        return semantic

    def _step2_fetch_glue(self, semantic: Dict[str, Any]) -> Dict[str, Any]:
        """Step 2: Fetch Glue metadata"""
        from shared.metadata.glue_fetcher import GlueFetcher

        start = time.time()

        glue = GlueFetcher(region=self.region)
        print(f"Fetching from Glue database: {self.database}")

        glue_metadata = {}
        for table_def in semantic.get('tables', []):
            table_name = table_def['name']
            try:
                metadata = glue.fetch_table_metadata(self.database, table_name)
                glue_metadata[table_name] = metadata

                column_count = len(metadata['columns'])
                self.stats['columns'] += column_count

                print(f"  ✓ {table_name}: {column_count} columns, "
                      f"format={metadata['format']}")

            except ValueError as e:
                print(f"  ⚠️  {table_name}: Not found in Glue Catalog (will use semantic.yaml types)")
                glue_metadata[table_name] = None

        elapsed = time.time() - start
        print(f"✓ Fetched metadata for {len(glue_metadata)} tables ({elapsed:.2f}s)")

        return glue_metadata

    def _step3_fetch_lf_tags(self, semantic: Dict[str, Any]) -> Dict[str, Any]:
        """Step 3: Fetch LF-Tags"""
        from shared.metadata.lakeformation_fetcher import LakeFormationFetcher

        start = time.time()

        lf = LakeFormationFetcher(region=self.region)
        print(f"Fetching LF-Tags for database: {self.database}")

        lf_tags = {}
        for table_def in semantic.get('tables', []):
            table_name = table_def['name']
            try:
                tags = lf.fetch_table_lf_tags(self.database, table_name)
                lf_tags[table_name] = tags

                table_tag_count = len(tags.get('table_tags', []))
                column_tag_count = len(tags.get('column_tags', {}))

                if table_tag_count > 0 or column_tag_count > 0:
                    print(f"  ✓ {table_name}: {table_tag_count} table tags, "
                          f"{column_tag_count} columns with tags")
                else:
                    print(f"  ○ {table_name}: No LF-Tags applied")

            except Exception as e:
                print(f"  ⚠️  {table_name}: Could not fetch LF-Tags ({e})")
                lf_tags[table_name] = {"table_tags": [], "column_tags": {}}

        elapsed = time.time() - start
        print(f"✓ Fetched LF-Tags for {len(lf_tags)} tables ({elapsed:.2f}s)")

        return lf_tags

    def _step4_combine_and_embed(self) -> UnifiedMetadataGraph:
        """Step 4: Combine metadata and generate embeddings"""
        start = time.time()

        # Combine metadata
        print("Combining Glue + semantic.yaml + LF-Tags...")
        combiner = MetadataCombiner(region=self.region)
        graph = combiner.combine_workload_metadata(
            workload=self.workload,
            database=self.database
        )

        # Count relationships
        for table in graph.tables:
            self.stats['relationships'] += len(table.relationships)
            self.stats['business_terms'] += len(table.business_terms)

        print(f"  ✓ Combined metadata: {len(graph.tables)} tables, "
              f"{sum(len(t.columns) for t in graph.tables)} columns")
        print(f"  ✓ Relationships: {self.stats['relationships']}")
        print(f"  ✓ Business terms: {self.stats['business_terms']}")

        # Generate embeddings
        print("\nGenerating Titan embeddings (1024 dimensions)...")
        embedder = MetadataEmbedder(region=self.region)
        embedded_graph = embedder.embed_metadata_graph(graph, verbose=True)

        # Count embeddings
        for table in embedded_graph.tables:
            if table.embedding_vector:
                self.stats['embeddings'] += 1
            for col in table.columns:
                if col.embedding_vector:
                    self.stats['embeddings'] += 1
            for term in table.business_terms:
                if term.get('embedding'):
                    self.stats['embeddings'] += 1
            for query in table.seed_queries:
                if query.get('embedding'):
                    self.stats['embeddings'] += 1
                    self.stats['seed_queries'] += 1

        elapsed = time.time() - start
        print(f"✓ Generated {self.stats['embeddings']} embeddings ({elapsed:.2f}s)")

        return embedded_graph

    def _step5_load_neptune(
        self,
        graph: UnifiedMetadataGraph,
        clear_graph: bool
    ):
        """Step 5: Load graph into Neptune"""
        if self.dry_run:
            print("⚠️  DRY RUN: Skipping Neptune load")
            print(f"   Would load {len(graph.tables)} tables to Neptune")
            return

        start = time.time()

        if clear_graph:
            print("⚠️  WARNING: Clearing existing Neptune graph...")
            response = input("Type 'yes' to confirm: ")
            if response.lower() != 'yes':
                print("Aborted.")
                sys.exit(1)

        print(f"Connecting to Neptune: {self.neptune_endpoint}")
        loader = NeptuneLoader(self.neptune_endpoint)

        try:
            loader.load_metadata_graph(
                graph,
                clear_existing=clear_graph,
                verbose=True
            )

            # Estimate vertex/edge counts
            self.stats['neptune_vertices'] = (
                1 +  # database
                len(graph.tables) +  # tables
                sum(len(t.columns) for t in graph.tables) +  # columns
                self.stats['business_terms']  # business terms
            )

            self.stats['neptune_edges'] = (
                len(graph.tables) +  # database→table
                sum(len(t.columns) for t in graph.tables) +  # table→column
                self.stats['relationships']  # FK edges
            )

            elapsed = time.time() - start
            print(f"✓ Loaded graph to Neptune ({elapsed:.2f}s)")
            print(f"  Vertices: ~{self.stats['neptune_vertices']}")
            print(f"  Edges: ~{self.stats['neptune_edges']}")

        finally:
            loader.close()

    def _step6_create_dynamodb(self):
        """Step 6: Create DynamoDB table"""
        if self.dry_run:
            print("⚠️  DRY RUN: Skipping DynamoDB table creation")
            return

        start = time.time()

        print(f"Creating/verifying DynamoDB table: synodb_queries")

        try:
            ensure_table_exists(region=self.region)
            elapsed = time.time() - start
            print(f"✓ DynamoDB table ready ({elapsed:.2f}s)")

        except Exception as e:
            print(f"⚠️  Warning: DynamoDB setup failed: {e}")

    def _step7_load_queries(self, graph: UnifiedMetadataGraph):
        """Step 7: Load seed queries"""
        if self.dry_run:
            print("⚠️  DRY RUN: Skipping seed query load")
            print(f"   Would load {self.stats['seed_queries']} seed queries")
            return

        start = time.time()

        print(f"Loading seed queries to DynamoDB...")

        try:
            loader = SynoDBLoader(region=self.region)
            count = loader.load_seed_queries(
                metadata=graph,
                workload=self.workload,
                verbose=True
            )

            elapsed = time.time() - start
            print(f"✓ Loaded {count} seed queries ({elapsed:.2f}s)")

        except Exception as e:
            print(f"⚠️  Warning: Seed query load failed: {e}")

    def _print_summary(self):
        """Print final summary"""
        print("\n" + "=" * 80)
        print("LOADING COMPLETE!")
        print("=" * 80)
        print(f"Workload:             {self.workload}")
        print(f"Database:             {self.database}")
        print("─" * 80)
        print(f"Tables:               {self.stats['tables']}")
        print(f"Columns:              {self.stats['columns']}")
        print(f"Relationships:        {self.stats['relationships']}")
        print(f"Business Terms:       {self.stats['business_terms']}")
        print("─" * 80)
        print(f"Embeddings Generated: {self.stats['embeddings']}")
        print(f"Neptune Vertices:     ~{self.stats['neptune_vertices']}")
        print(f"Neptune Edges:        ~{self.stats['neptune_edges']}")
        print(f"Seed Queries:         {self.stats['seed_queries']}")
        print("=" * 80)

        if not self.dry_run:
            print("\n✓ Semantic layer is ready!")
            print("\nNext steps:")
            print("  1. Verify setup:")
            print(f"     python verify_setup.py --workload {self.workload} "
                  f"--database {self.database} --neptune-endpoint {self.neptune_endpoint}")
            print("  2. Run example queries:")
            print("     python example_usage.py")
        else:
            print("\n⚠️  This was a DRY RUN - no data was written")
            print("   Remove --dry-run to actually load data")


def main():
    parser = argparse.ArgumentParser(
        description='Load metadata into Neptune (7-step process)',
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
        '--dry-run',
        action='store_true',
        help='Dry run mode (no writes to Neptune/DynamoDB)'
    )

    args = parser.parse_args()

    # Run pipeline
    pipeline = NeptuneLoadingPipeline(
        workload=args.workload,
        database=args.database,
        neptune_endpoint=args.neptune_endpoint,
        region=args.region,
        dry_run=args.dry_run
    )

    stats = pipeline.run(clear_graph=args.clear_graph)

    sys.exit(0)


if __name__ == '__main__':
    main()
