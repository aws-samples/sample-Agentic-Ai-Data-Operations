#!/usr/bin/env python3
"""
Silver → Gold transformation for dim_portfolios (Dimension Table)
AWS Glue ETL script with local mode fallback

Transformation:
- Copy all columns from silver.portfolios to gold.dim_portfolios
- SCD Type 1: Overwrite with current state
- No aggregation or joining needed (dimension table)

Usage:
  Glue: --silver_path s3://bucket/silver/portfolios/ --gold_path s3://bucket/gold/dim_portfolios/
  Local: --local --silver_path ./output/silver/portfolios.parquet --gold_path ./output/gold/dim_portfolios.parquet
"""

import sys
import json
from datetime import datetime
from pathlib import Path

def transform_glue_mode(glue_context, args):
    """Transform using AWS Glue (PySpark + Iceberg)"""
    from pyspark.sql import functions as F

    # Read from Silver (Iceberg table in Glue Catalog)
    spark = glue_context.spark_session
    silver_table = "glue_catalog.financial_portfolios_db.silver_portfolios"
    silver_df = spark.table(silver_table)

    input_rows = silver_df.count()
    print(f"Input rows from {silver_table}: {input_rows}")

    # No transformation needed - dimension table is a direct copy
    gold_df = silver_df

    output_rows = gold_df.count()
    print(f"Output rows: {output_rows}")

    # Write to Gold as Iceberg table in Glue Catalog (SCD Type 1 - overwrite)
    gold_table = "glue_catalog.financial_portfolios_db.gold_dim_portfolios"
    gold_df.write \
        .format("iceberg") \
        .mode("overwrite") \
        .option("write.format.default", "parquet") \
        .option("write.metadata.compression-codec", "gzip") \
        .saveAsTable(gold_table)

    print(f"Gold table written: {gold_table}")

    # Generate lineage
    lineage = {
        "workload": "financial_portfolios",
        "table": "dim_portfolios",
        "transformation": "silver_to_gold",
        "source": "glue_catalog.financial_portfolios_db.silver_portfolios",
        "target": "glue_catalog.financial_portfolios_db.gold_dim_portfolios",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "output_rows": output_rows,
        "transformations_applied": [
            "scd_type_1_overwrite"
        ],
        "column_lineage": {
            col: {"source": f"silver.portfolios.{col}", "transformations": []}
            for col in gold_df.columns
        },
        "quality_metrics": {
            "completeness": 1.0
        }
    }

    return lineage


def transform_local_mode(silver_path, gold_path):
    """Transform using pandas (local testing)"""
    import pandas as pd
    import hashlib

    print(f"Reading from: {silver_path}")

    # Read from Silver
    df = pd.read_parquet(silver_path)
    input_rows = len(df)
    print(f"Input rows: {input_rows}")

    # No transformation needed - dimension table is a direct copy
    gold_df = df.copy()

    output_rows = len(gold_df)
    print(f"Output rows: {output_rows}")

    # Write to Gold (simulate Iceberg with Parquet)
    Path(gold_path).parent.mkdir(parents=True, exist_ok=True)
    gold_df.to_parquet(gold_path, index=False, engine='pyarrow')
    print(f"Gold data written to: {gold_path}")

    # Generate lineage
    data_hash = hashlib.sha256(gold_df.to_json().encode()).hexdigest()

    lineage = {
        "workload": "financial_portfolios",
        "table": "dim_portfolios",
        "transformation": "silver_to_gold",
        "source": silver_path,
        "target": gold_path,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "output_rows": output_rows,
        "transformations_applied": [
            "scd_type_1_overwrite"
        ],
        "column_lineage": {
            col: {"source": f"silver.portfolios.{col}", "transformations": []}
            for col in gold_df.columns
        },
        "quality_metrics": {
            "completeness": 1.0
        },
        "data_hash": data_hash
    }

    # Write lineage
    lineage_path = gold_path.replace('.parquet', '_lineage.json')
    with open(lineage_path, 'w') as f:
        json.dump(lineage, f, indent=2)
    print(f"Lineage written to: {lineage_path}")

    return lineage


if __name__ == "__main__":
    if "--local" in sys.argv:
        # Local mode - pandas fallback
        silver_idx = sys.argv.index("--silver_path") + 1
        gold_idx = sys.argv.index("--gold_path") + 1
        silver_path = sys.argv[silver_idx]
        gold_path = sys.argv[gold_idx]

        lineage = transform_local_mode(silver_path, gold_path)
        print(f"\n✓ Transformation complete (local mode)")
        print(f"  Input: {lineage['input_rows']} rows")
        print(f"  Output: {lineage['output_rows']} rows")

    else:
        # Glue mode - PySpark + Iceberg
        try:
            from awsglue.transforms import *
            from awsglue.utils import getResolvedOptions
            from pyspark.context import SparkContext
            from awsglue.context import GlueContext
            from awsglue.job import Job
        except ImportError:
            print("ERROR: AWS Glue libraries not available. Use --local flag for pandas mode.")
            sys.exit(1)

        args = getResolvedOptions(sys.argv, ['JOB_NAME'])

        sc = SparkContext()
        glue_context = GlueContext(sc)
        spark = glue_context.spark_session
        job = Job(glue_context)
        job.init(args['JOB_NAME'], args)

        lineage = transform_glue_mode(glue_context, args)

        print(f"\n✓ Transformation complete (Glue mode)")
        print(f"  Input: {lineage['input_rows']} rows")
        print(f"  Output: {lineage['output_rows']} rows")

        # Lineage tracking removed temporarily (causing Hadoop classpath issues)
        # TODO: Re-enable with proper S3 write using boto3 instead of saveAsTextFile()
        print("  Lineage: skipped (avoiding Hadoop DirectOutputCommitter error)")

        job.commit()
