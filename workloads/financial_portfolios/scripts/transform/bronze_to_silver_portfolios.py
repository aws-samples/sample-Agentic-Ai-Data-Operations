#!/usr/bin/env python3
"""
Bronze → Silver transformation for portfolios table
AWS Glue ETL script with local mode fallback

Transformations:
- Deduplication: Keep last record per portfolio_id
- Type casting: Date, decimal, integer
- Validations: Not null checks, positive values, status validation
- Output: Apache Iceberg table in Silver zone

Usage:
  Glue: --bronze_path s3://bucket/bronze/... --silver_path s3://bucket/silver/...
  Local: --local --bronze_path ./data/bronze/portfolios.csv --silver_path ./output/silver/portfolios.parquet
"""

import sys
import json
from datetime import datetime
from pathlib import Path

def transform_glue_mode(glue_context, args):
    """Transform using AWS Glue (PySpark + Iceberg)"""
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    # Read from Bronze (CSV)
    bronze_df = glue_context.create_dynamic_frame.from_options(
        connection_type="s3",
        connection_options={"paths": [args['bronze_path']]},
        format="csv",
        format_options={
            "withHeader": True,
            "separator": ",",
            "quoteChar": '"',
            "escapeChar": "\\"
        }
    ).toDF()

    input_rows = bronze_df.count()
    print(f"Input rows: {input_rows}")

    # Step 1: Deduplication - keep last record per portfolio_id
    window = Window.partitionBy("portfolio_id").orderBy(F.desc("portfolio_id"))
    deduped_df = bronze_df \
        .withColumn("row_num", F.row_number().over(window)) \
        .filter(F.col("row_num") == 1) \
        .drop("row_num")

    dedup_rows = deduped_df.count()
    print(f"After deduplication: {dedup_rows} rows ({input_rows - dedup_rows} duplicates removed)")

    # Step 2: Type conversions
    typed_df = deduped_df \
        .withColumn("inception_date", F.to_date(F.col("inception_date"), "yyyy-MM-dd")) \
        .withColumn("last_rebalance_date", F.to_date(F.col("last_rebalance_date"), "yyyy-MM-dd")) \
        .withColumn("total_value", F.col("total_value").cast("decimal(15,2)")) \
        .withColumn("cash_balance", F.col("cash_balance").cast("decimal(15,2)")) \
        .withColumn("num_positions", F.col("num_positions").cast("int")) \
        .withColumn("avg_position_size", F.col("avg_position_size").cast("decimal(15,2)")) \
        .withColumn("largest_position_pct", F.col("largest_position_pct").cast("decimal(6,2)"))

    # Step 3: Validations - separate valid from quarantine
    valid_df = typed_df.filter(
        (F.col("portfolio_id").isNotNull()) &
        (F.col("portfolio_name").isNotNull()) &
        (F.col("manager_name").isNotNull()) &
        (F.col("total_value") >= 0) &
        (F.col("cash_balance") >= 0) &
        (F.col("num_positions") >= 0) &
        (F.col("status").isin("Active", "Closed", "Suspended"))
    )

    quarantine_df = typed_df.subtract(valid_df)

    valid_rows = valid_df.count()
    quarantine_rows = quarantine_df.count()
    print(f"Valid rows: {valid_rows}")
    print(f"Quarantined rows: {quarantine_rows}")

    # Step 4: Write valid records to Silver as Iceberg table in Glue Catalog
    # Use saveAsTable() for proper Glue catalog integration
    table_name = "glue_catalog.financial_portfolios_db.silver_portfolios"
    valid_df.write \
        .format("iceberg") \
        .mode("overwrite") \
        .option("write.format.default", "parquet") \
        .option("write.metadata.compression-codec", "gzip") \
        .saveAsTable(table_name)

    print(f"Silver table written: {table_name}")

    # Step 5: Write quarantined records to quarantine zone
    if quarantine_rows > 0:
        quarantine_path = args['bronze_path'].replace('/bronze/', '/quarantine/')
        quarantine_df \
            .withColumn("quarantine_timestamp", F.current_timestamp()) \
            .withColumn("quarantine_reason", F.lit("Validation failure")) \
            .write \
            .format("parquet") \
            .mode("append") \
            .save(quarantine_path)
        print(f"Quarantine written to: {quarantine_path}")

    # Step 6: Generate lineage
    lineage = {
        "workload": "financial_portfolios",
        "table": "portfolios",
        "transformation": "bronze_to_silver",
        "source": args['bronze_path'],
        "target": args['silver_path'],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "output_rows": valid_rows,
        "rejected_rows": 0,
        "quarantined_rows": quarantine_rows,
        "duplicate_rows": input_rows - dedup_rows,
        "transformations_applied": [
            "deduplication_by_portfolio_id",
            "type_casting",
            "null_validations",
            "non_negative_checks",
            "status_validation"
        ],
        "column_lineage": {
            "portfolio_id": {"source": "bronze.portfolios.portfolio_id", "transformations": []},
            "inception_date": {"source": "bronze.portfolios.inception_date", "transformations": ["parse_date"]},
            "last_rebalance_date": {"source": "bronze.portfolios.last_rebalance_date", "transformations": ["parse_date"]},
            "total_value": {"source": "bronze.portfolios.total_value", "transformations": ["cast_decimal", "round_2"]},
            "cash_balance": {"source": "bronze.portfolios.cash_balance", "transformations": ["cast_decimal", "round_2"]},
            "num_positions": {"source": "bronze.portfolios.num_positions", "transformations": ["cast_integer"]}
        },
        "quality_metrics": {
            "completeness": valid_rows / input_rows if input_rows > 0 else 0,
            "duplicate_rate": (input_rows - dedup_rows) / input_rows if input_rows > 0 else 0,
            "quarantine_rate": quarantine_rows / dedup_rows if dedup_rows > 0 else 0
        }
    }

    return lineage


def transform_local_mode(bronze_path, silver_path):
    """Transform using pandas (local testing)"""
    import pandas as pd
    import hashlib

    print(f"Reading from: {bronze_path}")

    # Step 1: Read CSV
    df = pd.read_csv(bronze_path)
    input_rows = len(df)
    print(f"Input rows: {input_rows}")

    # Step 2: Deduplication - keep last
    df = df.drop_duplicates(subset=['portfolio_id'], keep='last')
    dedup_rows = len(df)
    print(f"After deduplication: {dedup_rows} rows ({input_rows - dedup_rows} duplicates removed)")

    # Step 3: Type conversions
    df['inception_date'] = pd.to_datetime(df['inception_date'])
    df['last_rebalance_date'] = pd.to_datetime(df['last_rebalance_date'])
    df['total_value'] = df['total_value'].astype(float).round(2)
    df['cash_balance'] = df['cash_balance'].astype(float).round(2)
    df['num_positions'] = df['num_positions'].astype(int)
    df['avg_position_size'] = df['avg_position_size'].astype(float).round(2)
    df['largest_position_pct'] = df['largest_position_pct'].astype(float).round(2)

    # Step 4: Validations
    valid_mask = (
        df['portfolio_id'].notna() &
        df['portfolio_name'].notna() &
        df['manager_name'].notna() &
        (df['total_value'] >= 0) &
        (df['cash_balance'] >= 0) &
        (df['num_positions'] >= 0) &
        df['status'].isin(['Active', 'Closed', 'Suspended'])
    )

    quarantine_df = df[~valid_mask].copy()
    valid_df = df[valid_mask].copy()

    valid_rows = len(valid_df)
    quarantine_rows = len(quarantine_df)
    print(f"Valid rows: {valid_rows}")
    print(f"Quarantined rows: {quarantine_rows}")

    # Step 5: Write valid records to Silver (simulate Iceberg with Parquet)
    Path(silver_path).parent.mkdir(parents=True, exist_ok=True)
    valid_df.to_parquet(silver_path, index=False, engine='pyarrow')
    print(f"Silver data written to: {silver_path}")

    # Step 6: Write quarantine if needed
    if quarantine_rows > 0:
        quarantine_path = silver_path.replace('/silver/', '/quarantine/').replace('.parquet', '_quarantine.parquet')
        Path(quarantine_path).parent.mkdir(parents=True, exist_ok=True)
        quarantine_df['quarantine_timestamp'] = datetime.utcnow().isoformat() + "Z"
        quarantine_df['quarantine_reason'] = 'Validation failure'
        quarantine_df.to_parquet(quarantine_path, index=False, engine='pyarrow')
        print(f"Quarantine written to: {quarantine_path}")

    # Step 7: Generate lineage
    data_hash = hashlib.sha256(valid_df.to_json().encode()).hexdigest()

    lineage = {
        "workload": "financial_portfolios",
        "table": "portfolios",
        "transformation": "bronze_to_silver",
        "source": bronze_path,
        "target": silver_path,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "output_rows": valid_rows,
        "rejected_rows": 0,
        "quarantined_rows": quarantine_rows,
        "duplicate_rows": input_rows - dedup_rows,
        "transformations_applied": [
            "deduplication_by_portfolio_id",
            "type_casting",
            "null_validations",
            "non_negative_checks",
            "status_validation"
        ],
        "column_lineage": {
            "portfolio_id": {"source": "bronze.portfolios.portfolio_id", "transformations": []},
            "inception_date": {"source": "bronze.portfolios.inception_date", "transformations": ["parse_date"]},
            "last_rebalance_date": {"source": "bronze.portfolios.last_rebalance_date", "transformations": ["parse_date"]},
            "total_value": {"source": "bronze.portfolios.total_value", "transformations": ["cast_decimal", "round_2"]},
            "cash_balance": {"source": "bronze.portfolios.cash_balance", "transformations": ["cast_decimal", "round_2"]},
            "num_positions": {"source": "bronze.portfolios.num_positions", "transformations": ["cast_integer"]},
            "avg_position_size": {"source": "bronze.portfolios.avg_position_size", "transformations": ["cast_decimal", "round_2"]},
            "largest_position_pct": {"source": "bronze.portfolios.largest_position_pct", "transformations": ["cast_decimal", "round_2"]}
        },
        "quality_metrics": {
            "completeness": valid_rows / input_rows if input_rows > 0 else 0,
            "duplicate_rate": (input_rows - dedup_rows) / input_rows if input_rows > 0 else 0,
            "quarantine_rate": quarantine_rows / dedup_rows if dedup_rows > 0 else 0
        },
        "data_hash": data_hash
    }

    # Write lineage
    lineage_path = silver_path.replace('.parquet', '_lineage.json')
    with open(lineage_path, 'w') as f:
        json.dump(lineage, f, indent=2)
    print(f"Lineage written to: {lineage_path}")

    return lineage


if __name__ == "__main__":
    if "--local" in sys.argv:
        # Local mode - pandas fallback
        bronze_idx = sys.argv.index("--bronze_path") + 1
        silver_idx = sys.argv.index("--silver_path") + 1
        bronze_path = sys.argv[bronze_idx]
        silver_path = sys.argv[silver_idx]

        lineage = transform_local_mode(bronze_path, silver_path)
        print(f"\n✓ Transformation complete (local mode)")
        print(f"  Input: {lineage['input_rows']} rows")
        print(f"  Output: {lineage['output_rows']} rows")
        print(f"  Duplicates: {lineage['duplicate_rows']}")
        print(f"  Quarantined: {lineage['quarantined_rows']}")

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

        args = getResolvedOptions(sys.argv, ['JOB_NAME', 'bronze_path', 'silver_path'])

        sc = SparkContext()
        glue_context = GlueContext(sc)
        spark = glue_context.spark_session
        job = Job(glue_context)
        job.init(args['JOB_NAME'], args)

        lineage = transform_glue_mode(glue_context, args)

        print(f"\n✓ Transformation complete (Glue mode)")
        print(f"  Input: {lineage['input_rows']} rows")
        print(f"  Output: {lineage['output_rows']} rows")
        print(f"  Duplicates: {lineage['duplicate_rows']}")
        print(f"  Quarantined: {lineage['quarantined_rows']}")

        # Lineage tracking removed temporarily (causing Hadoop classpath issues)
        # TODO: Re-enable with proper S3 write using boto3 instead of saveAsTextFile()
        print("  Lineage: skipped (avoiding Hadoop DirectOutputCommitter error)")

        job.commit()
