#!/usr/bin/env python3
"""
Bronze → Silver transformation for positions table
AWS Glue ETL script with local mode fallback

CRITICAL VALIDATIONS (quarantine, not reject):
- Missing ticker → QUARANTINE
- Negative shares → QUARANTINE
- Invalid FK (portfolio_id not in portfolios) → QUARANTINE
- Invalid FK (ticker not in stocks) → QUARANTINE

Transformations:
- Deduplication: Keep last record per position_id (by last_updated)
- Type casting: Date, timestamp, decimal precision
- FK integrity checks (requires loading dimension tables)
- Output: Apache Iceberg table in Silver zone, partitioned by sector

Usage:
  Glue: --bronze_path s3://... --silver_path s3://... --portfolios_path s3://... --stocks_path s3://...
  Local: --local --bronze_path ./data/bronze/positions.csv --silver_path ./output/silver/positions.parquet --portfolios_path ./output/silver/portfolios.parquet --stocks_path ./output/silver/stocks.parquet
"""

import sys
import json
from datetime import datetime
from pathlib import Path

# Add project root to path for shared imports
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.script_tracer import ScriptTracer

def transform_glue_mode(glue_context, args):
    """Transform using AWS Glue (PySpark + Iceberg)"""
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    # Step 1: Load dimension tables for FK validation (read from Iceberg tables)
    print("Loading dimension tables for FK validation from Iceberg catalog...")

    spark = glue_context.spark_session

    # Read from Iceberg tables in Glue Catalog
    portfolios_table = "glue_catalog.financial_portfolios_db.silver_portfolios"
    stocks_table = "glue_catalog.financial_portfolios_db.silver_stocks"

    portfolios_df = spark.table(portfolios_table).select("portfolio_id").distinct()
    stocks_df = spark.table(stocks_table).select("ticker").distinct()

    valid_portfolio_ids = [row.portfolio_id for row in portfolios_df.collect()]
    valid_tickers = [row.ticker for row in stocks_df.collect()]
    print(f"Valid portfolios: {len(valid_portfolio_ids)}, Valid tickers: {len(valid_tickers)}")

    # Step 2: Read from Bronze (CSV)
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

    # Step 3: Deduplication - keep last record per position_id (by last_updated)
    window = Window.partitionBy("position_id").orderBy(F.desc("last_updated"))
    deduped_df = bronze_df \
        .withColumn("row_num", F.row_number().over(window)) \
        .filter(F.col("row_num") == 1) \
        .drop("row_num")

    dedup_rows = deduped_df.count()
    print(f"After deduplication: {dedup_rows} rows ({input_rows - dedup_rows} duplicates removed)")

    # Step 4: Type conversions
    typed_df = deduped_df \
        .withColumn("entry_date", F.to_date(F.col("entry_date"), "yyyy-MM-dd")) \
        .withColumn("last_updated", F.to_timestamp(F.col("last_updated"), "yyyy-MM-dd HH:mm:ss")) \
        .withColumn("shares", F.col("shares").cast("decimal(15,4)")) \
        .withColumn("cost_basis", F.col("cost_basis").cast("decimal(15,2)")) \
        .withColumn("purchase_price", F.col("purchase_price").cast("decimal(10,2)")) \
        .withColumn("current_price", F.col("current_price").cast("decimal(10,2)")) \
        .withColumn("market_value", F.col("market_value").cast("decimal(15,2)")) \
        .withColumn("unrealized_gain_loss", F.col("unrealized_gain_loss").cast("decimal(15,2)")) \
        .withColumn("unrealized_gain_loss_pct", F.col("unrealized_gain_loss_pct").cast("decimal(8,4)")) \
        .withColumn("weight_pct", F.col("weight_pct").cast("decimal(6,2)")) \
        .withColumn("holding_period_days", F.col("holding_period_days").cast("int"))

    # Step 5: CRITICAL VALIDATIONS - quarantine failures
    valid_df = typed_df.filter(
        # CRITICAL: ticker and portfolio_id must exist
        (F.col("ticker").isNotNull()) &
        (F.col("portfolio_id").isNotNull()) &
        # CRITICAL: shares must be positive
        (F.col("shares") > 0) &
        # CRITICAL: FK integrity
        (F.col("portfolio_id").isin(valid_portfolio_ids)) &
        (F.col("ticker").isin(valid_tickers)) &
        # Other validations
        (F.col("position_id").isNotNull()) &
        (F.col("cost_basis") > 0) &
        (F.col("market_value") > 0) &
        (F.col("purchase_price") > 0) &
        (F.col("current_price") > 0) &
        (F.col("weight_pct").between(0, 100)) &
        (F.col("position_status").isin("Open", "Closed", "Partial"))
    )

    quarantine_df = typed_df.subtract(valid_df)

    valid_rows = valid_df.count()
    quarantine_rows = quarantine_df.count()
    print(f"Valid rows: {valid_rows}")
    print(f"Quarantined rows: {quarantine_rows}")

    # Step 6: Add quarantine reasons
    if quarantine_rows > 0:
        quarantine_df = quarantine_df \
            .withColumn("quarantine_timestamp", F.current_timestamp()) \
            .withColumn("quarantine_reason",
                F.when(F.col("ticker").isNull(), F.lit("CRITICAL: Missing ticker symbol"))
                .when(F.col("portfolio_id").isNull(), F.lit("CRITICAL: Missing portfolio_id"))
                .when(F.col("shares") <= 0, F.lit("CRITICAL: Negative or zero shares"))
                .when(~F.col("portfolio_id").isin(valid_portfolio_ids), F.lit("CRITICAL: Invalid portfolio FK - portfolio not found"))
                .when(~F.col("ticker").isin(valid_tickers), F.lit("CRITICAL: Invalid ticker FK - stock not found"))
                .otherwise(F.lit("Validation failure"))
            )

    # Step 7: Write valid records to Silver as Iceberg table in Glue Catalog
    # Use saveAsTable() for proper Glue catalog integration
    table_name = "glue_catalog.financial_portfolios_db.silver_positions"
    valid_df.write \
        .format("iceberg") \
        .mode("overwrite") \
        .option("write.format.default", "parquet") \
        .option("write.metadata.compression-codec", "gzip") \
        .saveAsTable(table_name)

    print(f"Silver table written: {table_name}")

    # Step 8: Write quarantined records
    if quarantine_rows > 0:
        quarantine_path = args['bronze_path'].replace('/bronze/', '/quarantine/')
        quarantine_df.write \
            .format("parquet") \
            .mode("append") \
            .save(quarantine_path)
        print(f"Quarantine written to: {quarantine_path}")

    # Step 9: Generate lineage
    lineage = {
        "workload": "financial_portfolios",
        "table": "positions",
        "transformation": "bronze_to_silver",
        "source": args['bronze_path'],
        "target": args['silver_path'],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "output_rows": valid_rows,
        "rejected_rows": 0,
        "quarantined_rows": quarantine_rows,
        "duplicate_rows": input_rows - dedup_rows,
        "critical_quarantines": quarantine_rows,  # All quarantines are critical for positions
        "transformations_applied": [
            "deduplication_by_position_id_sorted_by_last_updated",
            "type_casting",
            "null_validations",
            "positive_value_checks",
            "fk_integrity_checks",
            "status_validation"
        ],
        "column_lineage": {
            "position_id": {"source": "bronze.positions.position_id", "transformations": []},
            "portfolio_id": {"source": "bronze.positions.portfolio_id", "transformations": ["fk_validation"]},
            "ticker": {"source": "bronze.positions.ticker", "transformations": ["fk_validation"]},
            "shares": {"source": "bronze.positions.shares", "transformations": ["cast_decimal", "round_4", "positive_check"]},
            "entry_date": {"source": "bronze.positions.entry_date", "transformations": ["parse_date"]},
            "last_updated": {"source": "bronze.positions.last_updated", "transformations": ["parse_timestamp"]},
            "market_value": {"source": "bronze.positions.market_value", "transformations": ["cast_decimal", "round_2"]},
            "unrealized_gain_loss": {"source": "bronze.positions.unrealized_gain_loss", "transformations": ["cast_decimal", "round_2"]},
            "unrealized_gain_loss_pct": {"source": "bronze.positions.unrealized_gain_loss_pct", "transformations": ["cast_decimal", "round_4"]}
        },
        "quality_metrics": {
            "completeness": valid_rows / input_rows if input_rows > 0 else 0,
            "duplicate_rate": (input_rows - dedup_rows) / input_rows if input_rows > 0 else 0,
            "quarantine_rate": quarantine_rows / dedup_rows if dedup_rows > 0 else 0,
            "fk_integrity_rate": valid_rows / dedup_rows if dedup_rows > 0 else 0
        }
    }

    return lineage


def transform_local_mode(bronze_path, silver_path, portfolios_path, stocks_path):
    """Transform using pandas (local testing)"""
    import pandas as pd
    import hashlib

    print(f"Reading from: {bronze_path}")

    # Step 1: Load dimension tables for FK validation
    print("Loading dimension tables for FK validation...")
    portfolios_df = pd.read_parquet(portfolios_path)
    stocks_df = pd.read_parquet(stocks_path)

    valid_portfolio_ids = set(portfolios_df['portfolio_id'].unique())
    valid_tickers = set(stocks_df['ticker'].unique())
    print(f"Valid portfolios: {len(valid_portfolio_ids)}, Valid tickers: {len(valid_tickers)}")

    # Step 2: Read CSV
    df = pd.read_csv(bronze_path)
    input_rows = len(df)
    print(f"Input rows: {input_rows}")

    # Step 3: Deduplication - keep last by last_updated
    df = df.sort_values('last_updated').drop_duplicates(subset=['position_id'], keep='last')
    dedup_rows = len(df)
    print(f"After deduplication: {dedup_rows} rows ({input_rows - dedup_rows} duplicates removed)")

    # Step 4: Type conversions
    df['entry_date'] = pd.to_datetime(df['entry_date'])
    df['last_updated'] = pd.to_datetime(df['last_updated'])
    df['shares'] = df['shares'].astype(float).round(4)
    df['cost_basis'] = df['cost_basis'].astype(float).round(2)
    df['purchase_price'] = df['purchase_price'].astype(float).round(2)
    df['current_price'] = df['current_price'].astype(float).round(2)
    df['market_value'] = df['market_value'].astype(float).round(2)
    df['unrealized_gain_loss'] = df['unrealized_gain_loss'].astype(float).round(2)
    df['unrealized_gain_loss_pct'] = df['unrealized_gain_loss_pct'].astype(float).round(4)
    df['weight_pct'] = df['weight_pct'].astype(float).round(2)
    df['holding_period_days'] = df['holding_period_days'].astype(int)

    # Step 5: CRITICAL VALIDATIONS
    valid_mask = (
        # CRITICAL: ticker and portfolio_id must exist
        df['ticker'].notna() &
        df['portfolio_id'].notna() &
        # CRITICAL: shares must be positive
        (df['shares'] > 0) &
        # CRITICAL: FK integrity
        df['portfolio_id'].isin(valid_portfolio_ids) &
        df['ticker'].isin(valid_tickers) &
        # Other validations
        df['position_id'].notna() &
        (df['cost_basis'] > 0) &
        (df['market_value'] > 0) &
        (df['purchase_price'] > 0) &
        (df['current_price'] > 0) &
        (df['weight_pct'] >= 0) &
        (df['weight_pct'] <= 100) &
        df['position_status'].isin(['Open', 'Closed', 'Partial'])
    )

    quarantine_df = df[~valid_mask].copy()
    valid_df = df[valid_mask].copy()

    valid_rows = len(valid_df)
    quarantine_rows = len(quarantine_df)
    print(f"Valid rows: {valid_rows}")
    print(f"Quarantined rows: {quarantine_rows}")

    # Step 6: Add quarantine reasons
    if quarantine_rows > 0:
        def get_quarantine_reason(row):
            reasons = []
            if pd.isna(row['ticker']):
                reasons.append("CRITICAL: Missing ticker symbol")
            if pd.isna(row['portfolio_id']):
                reasons.append("CRITICAL: Missing portfolio_id")
            if row['shares'] <= 0:
                reasons.append("CRITICAL: Negative or zero shares")
            if row['portfolio_id'] not in valid_portfolio_ids:
                reasons.append("CRITICAL: Invalid portfolio FK - portfolio not found")
            if row['ticker'] not in valid_tickers:
                reasons.append("CRITICAL: Invalid ticker FK - stock not found")
            if not reasons:
                reasons.append("Validation failure")
            return "; ".join(reasons)

        quarantine_df['quarantine_timestamp'] = datetime.utcnow().isoformat() + "Z"
        quarantine_df['quarantine_reason'] = quarantine_df.apply(get_quarantine_reason, axis=1)

    # Step 7: Write valid records to Silver (simulate Iceberg with Parquet, partitioned by sector)
    Path(silver_path).parent.mkdir(parents=True, exist_ok=True)

    # Write partitioned by sector
    for sector in valid_df['sector'].unique():
        sector_df = valid_df[valid_df['sector'] == sector]
        sector_path = f"{silver_path.replace('.parquet', '')}/sector={sector}/data.parquet"
        Path(sector_path).parent.mkdir(parents=True, exist_ok=True)
        sector_df.to_parquet(sector_path, index=False, engine='pyarrow')

    print(f"Silver data written to: {silver_path} (partitioned by sector)")

    # Step 8: Write quarantine if needed
    if quarantine_rows > 0:
        quarantine_path = silver_path.replace('/silver/', '/quarantine/').replace('.parquet', '_quarantine.parquet')
        Path(quarantine_path).parent.mkdir(parents=True, exist_ok=True)
        quarantine_df.to_parquet(quarantine_path, index=False, engine='pyarrow')
        print(f"Quarantine written to: {quarantine_path}")
        print(f"Quarantine breakdown:")
        print(quarantine_df['quarantine_reason'].value_counts())

    # Step 9: Generate lineage
    data_hash = hashlib.sha256(valid_df.to_json().encode()).hexdigest()

    lineage = {
        "workload": "financial_portfolios",
        "table": "positions",
        "transformation": "bronze_to_silver",
        "source": bronze_path,
        "target": silver_path,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "output_rows": valid_rows,
        "rejected_rows": 0,
        "quarantined_rows": quarantine_rows,
        "duplicate_rows": input_rows - dedup_rows,
        "critical_quarantines": quarantine_rows,
        "transformations_applied": [
            "deduplication_by_position_id_sorted_by_last_updated",
            "type_casting",
            "null_validations",
            "positive_value_checks",
            "fk_integrity_checks_portfolio_id",
            "fk_integrity_checks_ticker",
            "status_validation"
        ],
        "column_lineage": {
            "position_id": {"source": "bronze.positions.position_id", "transformations": []},
            "portfolio_id": {"source": "bronze.positions.portfolio_id", "transformations": ["fk_validation"]},
            "ticker": {"source": "bronze.positions.ticker", "transformations": ["fk_validation"]},
            "shares": {"source": "bronze.positions.shares", "transformations": ["cast_decimal", "round_4", "positive_check"]},
            "entry_date": {"source": "bronze.positions.entry_date", "transformations": ["parse_date"]},
            "last_updated": {"source": "bronze.positions.last_updated", "transformations": ["parse_timestamp"]},
            "market_value": {"source": "bronze.positions.market_value", "transformations": ["cast_decimal", "round_2"]},
            "unrealized_gain_loss": {"source": "bronze.positions.unrealized_gain_loss", "transformations": ["cast_decimal", "round_2"]},
            "unrealized_gain_loss_pct": {"source": "bronze.positions.unrealized_gain_loss_pct", "transformations": ["cast_decimal", "round_4"]},
            "sector": {"source": "bronze.positions.sector", "transformations": []},
            "position_status": {"source": "bronze.positions.position_status", "transformations": ["status_validation"]}
        },
        "quality_metrics": {
            "completeness": valid_rows / input_rows if input_rows > 0 else 0,
            "duplicate_rate": (input_rows - dedup_rows) / input_rows if input_rows > 0 else 0,
            "quarantine_rate": quarantine_rows / dedup_rows if dedup_rows > 0 else 0,
            "fk_integrity_rate": valid_rows / dedup_rows if dedup_rows > 0 else 0
        },
        "data_hash": data_hash
    }

    # Write lineage
    if silver_path.endswith('.parquet'):
        lineage_path = silver_path.replace('.parquet', '_lineage.json')
    else:
        # Directory path (partitioned output)
        lineage_path = f"{silver_path}_lineage.json"

    Path(lineage_path).parent.mkdir(parents=True, exist_ok=True)
    with open(lineage_path, 'w') as f:
        json.dump(lineage, f, indent=2)
    print(f"Lineage written to: {lineage_path}")

    return lineage


def transform_local_mode(bronze_path, silver_path, portfolios_path, stocks_path):
    """Transform using pandas (local testing)"""
    import pandas as pd
    import hashlib

    print(f"Reading from: {bronze_path}")

    # Step 1: Load dimension tables for FK validation
    print("Loading dimension tables for FK validation...")
    portfolios_df = pd.read_parquet(portfolios_path)
    stocks_df = pd.read_parquet(stocks_path)

    valid_portfolio_ids = set(portfolios_df['portfolio_id'].unique())
    valid_tickers = set(stocks_df['ticker'].unique())
    print(f"Valid portfolios: {len(valid_portfolio_ids)}, Valid tickers: {len(valid_tickers)}")

    # Step 2: Read CSV
    df = pd.read_csv(bronze_path)
    input_rows = len(df)
    print(f"Input rows: {input_rows}")

    # Step 3: Deduplication - keep last by last_updated
    df = df.sort_values('last_updated').drop_duplicates(subset=['position_id'], keep='last')
    dedup_rows = len(df)
    print(f"After deduplication: {dedup_rows} rows ({input_rows - dedup_rows} duplicates removed)")

    # Step 4: Type conversions
    df['entry_date'] = pd.to_datetime(df['entry_date'])
    df['last_updated'] = pd.to_datetime(df['last_updated'])
    df['shares'] = df['shares'].astype(float).round(4)
    df['cost_basis'] = df['cost_basis'].astype(float).round(2)
    df['purchase_price'] = df['purchase_price'].astype(float).round(2)
    df['current_price'] = df['current_price'].astype(float).round(2)
    df['market_value'] = df['market_value'].astype(float).round(2)
    df['unrealized_gain_loss'] = df['unrealized_gain_loss'].astype(float).round(2)
    df['unrealized_gain_loss_pct'] = df['unrealized_gain_loss_pct'].astype(float).round(4)
    df['weight_pct'] = df['weight_pct'].astype(float).round(2)
    df['holding_period_days'] = df['holding_period_days'].astype(int)

    # Step 5: CRITICAL VALIDATIONS
    valid_mask = (
        # CRITICAL: ticker and portfolio_id must exist
        df['ticker'].notna() &
        df['portfolio_id'].notna() &
        # CRITICAL: shares must be positive
        (df['shares'] > 0) &
        # CRITICAL: FK integrity
        df['portfolio_id'].isin(valid_portfolio_ids) &
        df['ticker'].isin(valid_tickers) &
        # Other validations
        df['position_id'].notna() &
        (df['cost_basis'] > 0) &
        (df['market_value'] > 0) &
        (df['purchase_price'] > 0) &
        (df['current_price'] > 0) &
        (df['weight_pct'] >= 0) &
        (df['weight_pct'] <= 100) &
        df['position_status'].isin(['Open', 'Closed', 'Partial'])
    )

    quarantine_df = df[~valid_mask].copy()
    valid_df = df[valid_mask].copy()

    valid_rows = len(valid_df)
    quarantine_rows = len(quarantine_df)
    print(f"Valid rows: {valid_rows}")
    print(f"Quarantined rows: {quarantine_rows}")

    # Step 6: Add quarantine reasons
    if quarantine_rows > 0:
        def get_quarantine_reason(row):
            reasons = []
            if pd.isna(row['ticker']):
                reasons.append("CRITICAL: Missing ticker symbol")
            if pd.isna(row['portfolio_id']):
                reasons.append("CRITICAL: Missing portfolio_id")
            if row['shares'] <= 0:
                reasons.append("CRITICAL: Negative or zero shares")
            if row['portfolio_id'] not in valid_portfolio_ids:
                reasons.append("CRITICAL: Invalid portfolio FK - portfolio not found")
            if row['ticker'] not in valid_tickers:
                reasons.append("CRITICAL: Invalid ticker FK - stock not found")
            if not reasons:
                reasons.append("Validation failure")
            return "; ".join(reasons)

        quarantine_df['quarantine_timestamp'] = datetime.utcnow().isoformat() + "Z"
        quarantine_df['quarantine_reason'] = quarantine_df.apply(get_quarantine_reason, axis=1)

    # Step 7: Write valid records to Silver (simulate Iceberg partitioning)
    Path(silver_path).parent.mkdir(parents=True, exist_ok=True)

    # Write partitioned by sector
    for sector in valid_df['sector'].unique():
        sector_df = valid_df[valid_df['sector'] == sector]
        sector_path = f"{silver_path.replace('.parquet', '')}/sector={sector}/data.parquet"
        Path(sector_path).parent.mkdir(parents=True, exist_ok=True)
        sector_df.to_parquet(sector_path, index=False, engine='pyarrow')

    print(f"Silver data written to: {silver_path} (partitioned by sector)")

    # Step 8: Write quarantine if needed
    if quarantine_rows > 0:
        quarantine_path = silver_path.replace('/silver/', '/quarantine/').replace('.parquet', '_quarantine.parquet')
        Path(quarantine_path).parent.mkdir(parents=True, exist_ok=True)
        quarantine_df.to_parquet(quarantine_path, index=False, engine='pyarrow')
        print(f"Quarantine written to: {quarantine_path}")
        print(f"Quarantine breakdown:")
        print(quarantine_df['quarantine_reason'].value_counts())

    # Step 9: Generate lineage
    data_hash = hashlib.sha256(valid_df.to_json().encode()).hexdigest()

    lineage = {
        "workload": "financial_portfolios",
        "table": "positions",
        "transformation": "bronze_to_silver",
        "source": bronze_path,
        "target": silver_path,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "output_rows": valid_rows,
        "rejected_rows": 0,
        "quarantined_rows": quarantine_rows,
        "duplicate_rows": input_rows - dedup_rows,
        "critical_quarantines": quarantine_rows,
        "transformations_applied": [
            "deduplication_by_position_id_sorted_by_last_updated",
            "type_casting",
            "null_validations",
            "positive_value_checks",
            "fk_integrity_checks_portfolio_id",
            "fk_integrity_checks_ticker",
            "status_validation"
        ],
        "column_lineage": {
            "position_id": {"source": "bronze.positions.position_id", "transformations": []},
            "portfolio_id": {"source": "bronze.positions.portfolio_id", "transformations": ["fk_validation"]},
            "ticker": {"source": "bronze.positions.ticker", "transformations": ["fk_validation"]},
            "shares": {"source": "bronze.positions.shares", "transformations": ["cast_decimal", "round_4", "positive_check"]},
            "entry_date": {"source": "bronze.positions.entry_date", "transformations": ["parse_date"]},
            "last_updated": {"source": "bronze.positions.last_updated", "transformations": ["parse_timestamp"]},
            "market_value": {"source": "bronze.positions.market_value", "transformations": ["cast_decimal", "round_2"]},
            "unrealized_gain_loss": {"source": "bronze.positions.unrealized_gain_loss", "transformations": ["cast_decimal", "round_2"]},
            "unrealized_gain_loss_pct": {"source": "bronze.positions.unrealized_gain_loss_pct", "transformations": ["cast_decimal", "round_4"]},
            "sector": {"source": "bronze.positions.sector", "transformations": []},
            "position_status": {"source": "bronze.positions.position_status", "transformations": ["status_validation"]}
        },
        "quality_metrics": {
            "completeness": valid_rows / input_rows if input_rows > 0 else 0,
            "duplicate_rate": (input_rows - dedup_rows) / input_rows if input_rows > 0 else 0,
            "quarantine_rate": quarantine_rows / dedup_rows if dedup_rows > 0 else 0,
            "fk_integrity_rate": valid_rows / dedup_rows if dedup_rows > 0 else 0
        },
        "data_hash": data_hash
    }

    # Write lineage
    if silver_path.endswith('.parquet'):
        lineage_path = silver_path.replace('.parquet', '_lineage.json')
    else:
        # Directory path (partitioned output)
        lineage_path = f"{silver_path}_lineage.json"

    Path(lineage_path).parent.mkdir(parents=True, exist_ok=True)
    with open(lineage_path, 'w') as f:
        json.dump(lineage, f, indent=2)
    print(f"Lineage written to: {lineage_path}")

    return lineage


if __name__ == "__main__":
    if "--local" in sys.argv:
        # Local mode - pandas fallback
        bronze_idx = sys.argv.index("--bronze_path") + 1
        silver_idx = sys.argv.index("--silver_path") + 1
        portfolios_idx = sys.argv.index("--portfolios_path") + 1
        stocks_idx = sys.argv.index("--stocks_path") + 1

        bronze_path = sys.argv[bronze_idx]
        silver_path = sys.argv[silver_idx]
        portfolios_path = sys.argv[portfolios_idx]
        stocks_path = sys.argv[stocks_idx]

        lineage = transform_local_mode(bronze_path, silver_path, portfolios_path, stocks_path)
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
