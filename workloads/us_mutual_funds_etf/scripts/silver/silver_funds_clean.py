"""
Silver Funds Clean - US Mutual Funds & ETF Dataset
Reads raw_funds from Bronze and applies cleaning rules.

JOB 2: Depends on JOB 1 (bronze_data_generation)
Input: s3://your-datalake-bucket/bronze/raw_funds/
Output: glue_catalog.finsights_silver.funds_clean (Iceberg)
"""

from awsglue.context import GlueContext
from pyspark.context import SparkContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.sql import functions as F
from pyspark.sql.types import DateType
from pyspark.sql.window import Window
import sys

# Initialize Glue context
args = getResolvedOptions(sys.argv, ["JOB_NAME"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)
logger = glueContext.get_logger()

logger.info("[silver_funds_clean] STEP 1: Reading Bronze raw_funds data")

# Read Bronze data
input_path = "s3://your-datalake-bucket/bronze/raw_funds/"
df_raw = spark.read.parquet(input_path)
raw_count = df_raw.count()

logger.info(f"[silver_funds_clean] STEP 2: Loaded {raw_count} rows from Bronze")
logger.info("[silver_funds_clean] Sample raw data:")
df_raw.show(5, truncate=False)

# ============================================================================
# CLEANING STEP 1: Drop invalid tickers
# ============================================================================

logger.info("[silver_funds_clean] STEP 3: Dropping invalid tickers (NULL, '???', 'N/A', '')")

df_step1 = df_raw.filter(
    (F.col("fund_ticker").isNotNull()) &
    (F.col("fund_ticker") != "???") &
    (F.col("fund_ticker") != "N/A") &
    (F.col("fund_ticker") != "")
)

step1_count = df_step1.count()
logger.info(f"[silver_funds_clean] After dropping invalid tickers: {step1_count} rows (removed {raw_count - step1_count})")

# ============================================================================
# CLEANING STEP 2: Deduplicate on fund_ticker
# ============================================================================

logger.info("[silver_funds_clean] STEP 4: Deduplicating on fund_ticker (keep first occurrence)")

window_spec = Window.partitionBy("fund_ticker").orderBy(F.lit(1))
df_step2 = df_step1.withColumn("row_num", F.row_number().over(window_spec)) \
    .filter(F.col("row_num") == 1) \
    .drop("row_num")

step2_count = df_step2.count()
logger.info(f"[silver_funds_clean] After deduplication: {step2_count} rows (removed {step1_count - step2_count} duplicates)")

# ============================================================================
# CLEANING STEP 3: Standardize fund_type
# ============================================================================

logger.info("[silver_funds_clean] STEP 5: Standardizing fund_type values")

df_step3 = df_step2.withColumn(
    "fund_type",
    F.when(F.upper(F.regexp_replace(F.col("fund_type"), "[^A-Za-z]", "")) == "ETF", "ETF")
     .when(F.upper(F.col("fund_type")).contains("MUTUAL"), "Mutual Fund")
     .otherwise(F.col("fund_type"))
)

logger.info("[silver_funds_clean] fund_type standardized (ETF variants → 'ETF', mutual fund variants → 'Mutual Fund')")

# ============================================================================
# CLEANING STEP 4: Standardize inception_date to DateType
# ============================================================================

logger.info("[silver_funds_clean] STEP 6: Standardizing inception_date to DateType")

# Handle both formats: YYYY-MM-DD and MM/DD/YYYY
df_step4 = df_step3.withColumn(
    "inception_date",
    F.coalesce(
        F.to_date(F.col("inception_date"), "yyyy-MM-dd"),
        F.to_date(F.col("inception_date"), "MM/dd/yyyy")
    )
)

logger.info("[silver_funds_clean] inception_date converted to DateType (handled both YYYY-MM-DD and MM/DD/YYYY)")

# ============================================================================
# CLEANING STEP 5: Fill null fund_name
# ============================================================================

logger.info("[silver_funds_clean] STEP 7: Filling null fund_name with 'Unknown Fund'")

null_name_count = df_step4.filter(F.col("fund_name").isNull()).count()
logger.info(f"[silver_funds_clean] Found {null_name_count} rows with null fund_name")

df_step5 = df_step4.withColumn(
    "fund_name",
    F.when(F.col("fund_name").isNull(), "Unknown Fund").otherwise(F.col("fund_name"))
)

# ============================================================================
# CLEANING STEP 6: Rename category → fund_category
# ============================================================================

logger.info("[silver_funds_clean] STEP 8: Renaming 'category' column to 'fund_category'")

df_clean = df_step5.withColumnRenamed("category", "fund_category")

final_count = df_clean.count()
logger.info(f"[silver_funds_clean] Final cleaned row count: {final_count}")

# ============================================================================
# Write to Iceberg
# ============================================================================

logger.info("[silver_funds_clean] STEP 9: Writing to Iceberg table glue_catalog.finsights_silver.funds_clean")

df_clean.writeTo("glue_catalog.finsights_silver.funds_clean") \
    .tableProperty("format-version", "2") \
    .createOrReplace()

logger.info("[silver_funds_clean] STEP 10: Write complete, verifying...")

# Verify write
df_verify = spark.table("glue_catalog.finsights_silver.funds_clean")
verify_count = df_verify.count()

logger.info(f"[silver_funds_clean] Verification: {verify_count} rows in Iceberg table")
logger.info("[silver_funds_clean] Schema:")
df_verify.printSchema()
logger.info("[silver_funds_clean] Sample cleaned data:")
df_verify.show(5, truncate=False)

logger.info("[silver_funds_clean] STEP 11: Job complete")
logger.info(f"[silver_funds_clean] Summary:")
logger.info(f"  - Input rows: {raw_count}")
logger.info(f"  - Invalid tickers removed: {raw_count - step1_count}")
logger.info(f"  - Duplicates removed: {step1_count - step2_count}")
logger.info(f"  - Null fund_name filled: {null_name_count}")
logger.info(f"  - Final rows: {verify_count}")

job.commit()
