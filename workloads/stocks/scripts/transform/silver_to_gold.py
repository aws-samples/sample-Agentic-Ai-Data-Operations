#!/usr/bin/env python3
"""
Silver -> Gold transformation for stocks_analytics (Flat Denormalized Table)
AWS Glue ETL script with local mode fallback

Transformation:
- Read all columns from silver.stocks (including GDPR metadata)
- Add computed columns: price_52w_range, price_pct_from_high,
  market_cap_category, yield_category, volatility_category
- Write to Gold as flat denormalized Iceberg table (NOT star schema)

Usage:
  Glue: --silver_path s3://bucket/silver/stocks/ --gold_path s3://bucket/gold/stocks_analytics/
  Local: --local --silver_path ./output/silver/stocks.parquet --gold_path ./output/gold/stocks_analytics.parquet
"""

import sys
import json
from datetime import datetime
from pathlib import Path


def _add_computed_columns_spark(df):
    """Add computed enrichment columns using PySpark."""
    from pyspark.sql import functions as F

    gold_df = df \
        .withColumn(
            "price_52w_range",
            (F.col("price_52w_high") - F.col("price_52w_low")).cast("decimal(10,2)")
        ) \
        .withColumn(
            "price_pct_from_high",
            (((F.col("current_price") - F.col("price_52w_high")) / F.col("price_52w_high")) * 100).cast("decimal(8,4)")
        ) \
        .withColumn(
            "market_cap_category",
            F.when(F.col("market_cap_billions") >= 200, "Mega Cap")
             .when(F.col("market_cap_billions") >= 10, "Large Cap")
             .when(F.col("market_cap_billions") >= 2, "Mid Cap")
             .otherwise("Small Cap")
        ) \
        .withColumn(
            "yield_category",
            F.when(F.col("dividend_yield") >= 4, "High Yield")
             .when(F.col("dividend_yield") >= 2, "Moderate Yield")
             .when(F.col("dividend_yield") > 0, "Low Yield")
             .otherwise("No Yield")
        ) \
        .withColumn(
            "volatility_category",
            F.when(F.col("beta") >= 1.5, "High Volatility")
             .when(F.col("beta") >= 1.0, "Market Volatility")
             .when(F.col("beta") >= 0.5, "Low Volatility")
             .otherwise("Defensive")
        )

    return gold_df


def _add_computed_columns_pandas(df):
    """Add computed enrichment columns using pandas."""
    gold_df = df.copy()

    # Numeric computed columns
    gold_df['price_52w_range'] = round(gold_df['price_52w_high'] - gold_df['price_52w_low'], 2)
    gold_df['price_pct_from_high'] = round(
        ((gold_df['current_price'] - gold_df['price_52w_high']) / gold_df['price_52w_high']) * 100, 4
    )

    # Categorical computed columns
    gold_df['market_cap_category'] = gold_df['market_cap_billions'].apply(
        lambda x: 'Mega Cap' if x >= 200 else ('Large Cap' if x >= 10 else ('Mid Cap' if x >= 2 else 'Small Cap'))
    )

    gold_df['yield_category'] = gold_df['dividend_yield'].apply(
        lambda x: 'High Yield' if x >= 4 else ('Moderate Yield' if x >= 2 else ('Low Yield' if x > 0 else 'No Yield'))
    )

    gold_df['volatility_category'] = gold_df['beta'].apply(
        lambda x: 'High Volatility' if x >= 1.5 else ('Market Volatility' if x >= 1.0 else ('Low Volatility' if x >= 0.5 else 'Defensive'))
    )

    return gold_df


def transform_glue_mode(glue_context, args):
    """Transform using AWS Glue (PySpark + Iceberg)"""

    # Read from Silver (Iceberg table in Glue Catalog)
    spark = glue_context.spark_session
    silver_table = "glue_catalog.stocks_db.silver_stocks"
    silver_df = spark.table(silver_table)

    input_rows = silver_df.count()
    print(f"Input rows from {silver_table}: {input_rows}")

    # Add computed columns
    gold_df = _add_computed_columns_spark(silver_df)

    output_rows = gold_df.count()
    print(f"Output rows: {output_rows}")

    # Write to Gold as Iceberg table in Glue Catalog (overwrite for idempotency)
    gold_table = "glue_catalog.stocks_db.gold_stocks_analytics"
    gold_df.write \
        .format("iceberg") \
        .mode("overwrite") \
        .option("write.format.default", "parquet") \
        .option("write.metadata.compression-codec", "gzip") \
        .saveAsTable(gold_table)

    print(f"Gold table written: {gold_table}")

    # Generate lineage
    lineage = {
        "workload": "stocks",
        "table": "stocks_analytics",
        "transformation": "silver_to_gold",
        "source": "glue_catalog.stocks_db.silver_stocks",
        "target": "glue_catalog.stocks_db.gold_stocks_analytics",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "output_rows": output_rows,
        "transformations_applied": [
            "flat_denormalized_enrichment",
            "computed_price_52w_range",
            "computed_price_pct_from_high",
            "computed_market_cap_category",
            "computed_yield_category",
            "computed_volatility_category"
        ],
        "column_lineage": {
            col: {"source": f"silver.stocks.{col}", "transformations": []}
            for col in silver_df.columns
        },
        "quality_metrics": {
            "completeness": 1.0
        }
    }

    # Add computed column lineage
    lineage["column_lineage"]["price_52w_range"] = {
        "source": "computed",
        "transformations": ["price_52w_high - price_52w_low"]
    }
    lineage["column_lineage"]["price_pct_from_high"] = {
        "source": "computed",
        "transformations": ["((current_price - price_52w_high) / price_52w_high) * 100"]
    }
    lineage["column_lineage"]["market_cap_category"] = {
        "source": "computed",
        "transformations": ["case_when_market_cap_billions"]
    }
    lineage["column_lineage"]["yield_category"] = {
        "source": "computed",
        "transformations": ["case_when_dividend_yield"]
    }
    lineage["column_lineage"]["volatility_category"] = {
        "source": "computed",
        "transformations": ["case_when_beta"]
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

    # Add computed columns
    gold_df = _add_computed_columns_pandas(df)

    output_rows = len(gold_df)
    print(f"Output rows: {output_rows}")

    # Write to Gold (simulate Iceberg with Parquet)
    Path(gold_path).parent.mkdir(parents=True, exist_ok=True)
    gold_df.to_parquet(gold_path, index=False, engine='pyarrow')
    print(f"Gold data written to: {gold_path}")

    # Generate lineage
    data_hash = hashlib.sha256(gold_df.to_json().encode()).hexdigest()

    silver_columns = list(df.columns)
    lineage = {
        "workload": "stocks",
        "table": "stocks_analytics",
        "transformation": "silver_to_gold",
        "source": silver_path,
        "target": gold_path,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "output_rows": output_rows,
        "transformations_applied": [
            "flat_denormalized_enrichment",
            "computed_price_52w_range",
            "computed_price_pct_from_high",
            "computed_market_cap_category",
            "computed_yield_category",
            "computed_volatility_category"
        ],
        "column_lineage": {
            col: {"source": f"silver.stocks.{col}", "transformations": []}
            for col in silver_columns
        },
        "quality_metrics": {
            "completeness": 1.0
        },
        "data_hash": data_hash
    }

    # Add computed column lineage
    lineage["column_lineage"]["price_52w_range"] = {
        "source": "computed",
        "transformations": ["price_52w_high - price_52w_low"]
    }
    lineage["column_lineage"]["price_pct_from_high"] = {
        "source": "computed",
        "transformations": ["((current_price - price_52w_high) / price_52w_high) * 100"]
    }
    lineage["column_lineage"]["market_cap_category"] = {
        "source": "computed",
        "transformations": ["case_when_market_cap_billions"]
    }
    lineage["column_lineage"]["yield_category"] = {
        "source": "computed",
        "transformations": ["case_when_dividend_yield"]
    }
    lineage["column_lineage"]["volatility_category"] = {
        "source": "computed",
        "transformations": ["case_when_beta"]
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
        print(f"\nTransformation complete (local mode)")
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

        print(f"\nTransformation complete (Glue mode)")
        print(f"  Input: {lineage['input_rows']} rows")
        print(f"  Output: {lineage['output_rows']} rows")

        # Lineage tracking removed temporarily (causing Hadoop classpath issues)
        # TODO: Re-enable with proper S3 write using boto3 instead of saveAsTextFile()
        print("  Lineage: skipped (avoiding Hadoop DirectOutputCommitter error)")

        job.commit()
