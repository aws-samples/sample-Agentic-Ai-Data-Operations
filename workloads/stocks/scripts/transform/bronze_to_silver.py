#!/usr/bin/env python3
"""
Bronze -> Silver transformation for stocks table
AWS Glue ETL script with local mode fallback

Transformations:
- Deduplication: Keep last record per ticker
- Type casting: Date, decimal precision (2 decimals for money, 3-4 for ratios)
- Validations: Not null checks, positive values, price range checks
- GDPR metadata columns: consent_given, consent_timestamp, is_deleted, etc.
- Output: Apache Iceberg table in Silver zone

Usage:
  Glue: --bronze_path s3://bucket/bronze/... --silver_path s3://bucket/silver/...
  Local: --local --bronze_path ./data/bronze/stocks.csv --silver_path ./output/silver/stocks.parquet
"""

import sys
import json
from datetime import datetime
from pathlib import Path


def transform_glue_mode(glue_context, args):
    """Transform using AWS Glue (PySpark + Iceberg)"""
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window
    from pyspark.sql.types import BooleanType, TimestampType, StringType

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

    # Step 1: Deduplication - keep last record per ticker
    window = Window.partitionBy("ticker").orderBy(F.desc("ticker"))
    deduped_df = bronze_df \
        .withColumn("row_num", F.row_number().over(window)) \
        .filter(F.col("row_num") == 1) \
        .drop("row_num")

    dedup_rows = deduped_df.count()
    print(f"After deduplication: {dedup_rows} rows ({input_rows - dedup_rows} duplicates removed)")

    # Step 2: Type conversions
    typed_df = deduped_df \
        .withColumn("listing_date", F.to_date(F.col("listing_date"), "yyyy-MM-dd")) \
        .withColumn("market_cap_billions", F.col("market_cap_billions").cast("decimal(12,2)")) \
        .withColumn("current_price", F.col("current_price").cast("decimal(10,2)")) \
        .withColumn("price_52w_high", F.col("price_52w_high").cast("decimal(10,2)")) \
        .withColumn("price_52w_low", F.col("price_52w_low").cast("decimal(10,2)")) \
        .withColumn("pe_ratio", F.col("pe_ratio").cast("decimal(8,2)")) \
        .withColumn("dividend_yield", F.col("dividend_yield").cast("decimal(6,4)")) \
        .withColumn("beta", F.col("beta").cast("decimal(6,3)")) \
        .withColumn("avg_volume_millions", F.col("avg_volume_millions").cast("decimal(10,2)"))

    # Step 3: Validations - separate valid from quarantine
    valid_df = typed_df.filter(
        (F.col("ticker").isNotNull()) &
        (F.col("company_name").isNotNull()) &
        (F.col("sector").isNotNull()) &
        (F.col("industry").isNotNull()) &
        (F.col("exchange").isNotNull()) &
        (F.col("current_price") > 0) &
        (F.col("market_cap_billions") > 0) &
        (F.col("price_52w_high") >= F.col("current_price")) &
        (F.col("price_52w_low") <= F.col("current_price"))
    )

    quarantine_df = typed_df.subtract(valid_df)

    valid_rows = valid_df.count()
    quarantine_rows = quarantine_df.count()
    print(f"Valid rows: {valid_rows}")
    print(f"Quarantined rows: {quarantine_rows}")

    # Step 4: Add GDPR metadata columns
    valid_df = valid_df \
        .withColumn("consent_given", F.lit(True).cast(BooleanType())) \
        .withColumn("consent_timestamp", F.current_timestamp()) \
        .withColumn("is_deleted", F.lit(False).cast(BooleanType())) \
        .withColumn("deletion_requested_at", F.lit(None).cast(TimestampType())) \
        .withColumn("data_subject_id", F.lit(None).cast(StringType()))

    # Step 5: Write valid records to Silver as Iceberg table in Glue Catalog
    table_name = "glue_catalog.stocks_db.silver_stocks"
    valid_df.write \
        .format("iceberg") \
        .mode("overwrite") \
        .option("write.format.default", "parquet") \
        .option("write.metadata.compression-codec", "gzip") \
        .saveAsTable(table_name)

    print(f"Silver table written: {table_name}")

    # Step 6: Write quarantined records to quarantine zone
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

    # Step 7: Generate lineage
    lineage = {
        "workload": "stocks",
        "table": "stocks",
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
            "deduplication_by_ticker",
            "type_casting",
            "null_validations",
            "positive_value_checks",
            "price_range_validations",
            "gdpr_metadata_columns"
        ],
        "column_lineage": {
            "ticker": {"source": "bronze.stocks.ticker", "transformations": []},
            "listing_date": {"source": "bronze.stocks.listing_date", "transformations": ["parse_date"]},
            "market_cap_billions": {"source": "bronze.stocks.market_cap_billions", "transformations": ["cast_decimal"]},
            "current_price": {"source": "bronze.stocks.current_price", "transformations": ["cast_decimal"]},
            "consent_given": {"source": "generated", "transformations": ["gdpr_default_true"]},
            "is_deleted": {"source": "generated", "transformations": ["gdpr_default_false"]}
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
    df = df.drop_duplicates(subset=['ticker'], keep='last')
    dedup_rows = len(df)
    print(f"After deduplication: {dedup_rows} rows ({input_rows - dedup_rows} duplicates removed)")

    # Step 3: Type conversions
    df['listing_date'] = pd.to_datetime(df['listing_date'])
    df['market_cap_billions'] = df['market_cap_billions'].astype(float).round(2)
    df['current_price'] = df['current_price'].astype(float).round(2)
    df['price_52w_high'] = df['price_52w_high'].astype(float).round(2)
    df['price_52w_low'] = df['price_52w_low'].astype(float).round(2)
    df['pe_ratio'] = df['pe_ratio'].astype(float).round(2)
    df['dividend_yield'] = df['dividend_yield'].astype(float).round(4)
    df['beta'] = df['beta'].astype(float).round(3)
    df['avg_volume_millions'] = df['avg_volume_millions'].astype(float).round(2)

    # Step 4: Validations
    valid_mask = (
        df['ticker'].notna() &
        df['company_name'].notna() &
        df['sector'].notna() &
        df['industry'].notna() &
        df['exchange'].notna() &
        (df['current_price'] > 0) &
        (df['market_cap_billions'] > 0) &
        (df['price_52w_high'] >= df['current_price']) &
        (df['price_52w_low'] <= df['current_price'])
    )

    quarantine_df = df[~valid_mask].copy()
    valid_df = df[valid_mask].copy()

    valid_rows = len(valid_df)
    quarantine_rows = len(quarantine_df)
    print(f"Valid rows: {valid_rows}")
    print(f"Quarantined rows: {quarantine_rows}")

    # Step 5: Add GDPR metadata columns
    valid_df['consent_given'] = True
    valid_df['consent_timestamp'] = datetime.utcnow().isoformat() + "Z"
    valid_df['is_deleted'] = False
    valid_df['deletion_requested_at'] = None
    valid_df['data_subject_id'] = None

    # Step 6: Write valid records to Silver (simulate Iceberg with Parquet)
    Path(silver_path).parent.mkdir(parents=True, exist_ok=True)
    valid_df.to_parquet(silver_path, index=False, engine='pyarrow')
    print(f"Silver data written to: {silver_path}")

    # Step 7: Write quarantine if needed
    if quarantine_rows > 0:
        quarantine_path = silver_path.replace('/silver/', '/quarantine/').replace('.parquet', '_quarantine.parquet')
        Path(quarantine_path).parent.mkdir(parents=True, exist_ok=True)
        quarantine_df['quarantine_timestamp'] = datetime.utcnow().isoformat() + "Z"
        quarantine_df['quarantine_reason'] = 'Validation failure'
        quarantine_df.to_parquet(quarantine_path, index=False, engine='pyarrow')
        print(f"Quarantine written to: {quarantine_path}")

    # Step 8: Generate lineage
    data_hash = hashlib.sha256(valid_df.to_json().encode()).hexdigest()

    lineage = {
        "workload": "stocks",
        "table": "stocks",
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
            "deduplication_by_ticker",
            "type_casting",
            "null_validations",
            "positive_value_checks",
            "price_range_validations",
            "gdpr_metadata_columns"
        ],
        "column_lineage": {
            "ticker": {"source": "bronze.stocks.ticker", "transformations": []},
            "listing_date": {"source": "bronze.stocks.listing_date", "transformations": ["parse_date"]},
            "market_cap_billions": {"source": "bronze.stocks.market_cap_billions", "transformations": ["cast_decimal", "round_2"]},
            "current_price": {"source": "bronze.stocks.current_price", "transformations": ["cast_decimal", "round_2"]},
            "price_52w_high": {"source": "bronze.stocks.price_52w_high", "transformations": ["cast_decimal", "round_2"]},
            "price_52w_low": {"source": "bronze.stocks.price_52w_low", "transformations": ["cast_decimal", "round_2"]},
            "pe_ratio": {"source": "bronze.stocks.pe_ratio", "transformations": ["cast_decimal", "round_2"]},
            "dividend_yield": {"source": "bronze.stocks.dividend_yield", "transformations": ["cast_decimal", "round_4"]},
            "beta": {"source": "bronze.stocks.beta", "transformations": ["cast_decimal", "round_3"]},
            "avg_volume_millions": {"source": "bronze.stocks.avg_volume_millions", "transformations": ["cast_decimal", "round_2"]},
            "consent_given": {"source": "generated", "transformations": ["gdpr_default_true"]},
            "consent_timestamp": {"source": "generated", "transformations": ["gdpr_current_timestamp"]},
            "is_deleted": {"source": "generated", "transformations": ["gdpr_default_false"]},
            "deletion_requested_at": {"source": "generated", "transformations": ["gdpr_default_null"]},
            "data_subject_id": {"source": "generated", "transformations": ["gdpr_default_null"]}
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
        print(f"\nTransformation complete (local mode)")
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

        print(f"\nTransformation complete (Glue mode)")
        print(f"  Input: {lineage['input_rows']} rows")
        print(f"  Output: {lineage['output_rows']} rows")
        print(f"  Duplicates: {lineage['duplicate_rows']}")
        print(f"  Quarantined: {lineage['quarantined_rows']}")

        # Lineage tracking removed temporarily (causing Hadoop classpath issues)
        # TODO: Re-enable with proper S3 write using boto3 instead of saveAsTextFile()
        print("  Lineage: skipped (avoiding Hadoop DirectOutputCommitter error)")

        job.commit()
