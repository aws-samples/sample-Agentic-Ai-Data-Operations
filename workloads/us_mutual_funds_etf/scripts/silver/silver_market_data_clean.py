"""
Silver Market Data Clean - US Mutual Funds & ETF Dataset
Reads raw_market_data from Bronze and applies cleaning rules.

JOB 3: Depends on JOB 1 (bronze_data_generation)
Input: s3://your-datalake-bucket/bronze/raw_market_data/
Output: glue_catalog.finsights_silver.market_data_clean (Iceberg)
"""

from awsglue.context import GlueContext
from pyspark.context import SparkContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType
import sys

# Initialize Glue context
args = getResolvedOptions(sys.argv, ["JOB_NAME"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)
logger = glueContext.get_logger()

logger.info("[silver_market_data_clean] STEP 1: Reading Bronze raw_market_data")

# Read Bronze data
input_path = "s3://your-datalake-bucket/bronze/raw_market_data/"
df_raw = spark.read.parquet(input_path)
raw_count = df_raw.count()

logger.info(f"[silver_market_data_clean] STEP 2: Loaded {raw_count} rows from Bronze")
logger.info("[silver_market_data_clean] Sample raw data:")
df_raw.show(5, truncate=False)

# ============================================================================
# CLEANING STEP 1: Rename ticker → fund_ticker
# ============================================================================

logger.info("[silver_market_data_clean] STEP 3: Renaming 'ticker' column to 'fund_ticker'")

df_step1 = df_raw.withColumnRenamed("ticker", "fund_ticker")

# ============================================================================
# CLEANING STEP 2: Fix expense_ratio_pct (strip % and cast to DoubleType)
# ============================================================================

logger.info("[silver_market_data_clean] STEP 4: Fixing expense_ratio_pct (strip '%' and cast to DoubleType)")

# Count rows with string format
string_format_count = df_step1.filter(F.col("expense_ratio_pct").rlike("%$")).count()
logger.info(f"[silver_market_data_clean] Found {string_format_count} rows with '%' format in expense_ratio_pct")

df_step2 = df_step1.withColumn(
    "expense_ratio_pct",
    F.when(
        F.col("expense_ratio_pct").cast("string").rlike("%$"),
        F.regexp_replace(F.col("expense_ratio_pct").cast("string"), "%", "").cast(DoubleType())
    ).otherwise(F.col("expense_ratio_pct").cast(DoubleType()))
)

logger.info("[silver_market_data_clean] expense_ratio_pct cleaned and cast to DoubleType")

# ============================================================================
# CLEANING STEP 3: Clamp morningstar_rating (set to null if < 1 OR > 5)
# ============================================================================

logger.info("[silver_market_data_clean] STEP 5: Clamping morningstar_rating (valid range: 1-5)")

invalid_rating_count = df_step2.filter(
    (F.col("morningstar_rating") < 1) | (F.col("morningstar_rating") > 5)
).count()
logger.info(f"[silver_market_data_clean] Found {invalid_rating_count} rows with invalid morningstar_rating")

df_step3 = df_step2.withColumn(
    "morningstar_rating",
    F.when(
        (F.col("morningstar_rating") >= 1) & (F.col("morningstar_rating") <= 5),
        F.col("morningstar_rating")
    ).otherwise(None)
)

# ============================================================================
# CLEANING STEP 4: Impute nulls in beta and sharpe_ratio using median
# ============================================================================

logger.info("[silver_market_data_clean] STEP 6: Imputing null values in beta and sharpe_ratio with median")

# Calculate medians
beta_null_count = df_step3.filter(F.col("beta").isNull()).count()
sharpe_null_count = df_step3.filter(F.col("sharpe_ratio").isNull()).count()

logger.info(f"[silver_market_data_clean] Null counts before imputation:")
logger.info(f"  - beta: {beta_null_count} nulls")
logger.info(f"  - sharpe_ratio: {sharpe_null_count} nulls")

# Use approxQuantile to get median (0.5 quantile)
beta_median = df_step3.approxQuantile("beta", [0.5], 0.01)[0] if beta_null_count < df_step3.count() else 1.0
sharpe_median = df_step3.approxQuantile("sharpe_ratio", [0.5], 0.01)[0] if sharpe_null_count < df_step3.count() else 1.0

logger.info(f"[silver_market_data_clean] Calculated medians:")
logger.info(f"  - beta median: {beta_median}")
logger.info(f"  - sharpe_ratio median: {sharpe_median}")

df_step4 = df_step3.withColumn(
    "beta",
    F.when(F.col("beta").isNull(), F.lit(beta_median)).otherwise(F.col("beta"))
).withColumn(
    "sharpe_ratio",
    F.when(F.col("sharpe_ratio").isNull(), F.lit(sharpe_median)).otherwise(F.col("sharpe_ratio"))
)

# ============================================================================
# CLEANING STEP 5: Drop rows where fund_ticker is null
# ============================================================================

logger.info("[silver_market_data_clean] STEP 7: Dropping rows where fund_ticker is null")

before_drop_count = df_step4.count()
df_clean = df_step4.filter(F.col("fund_ticker").isNotNull())
final_count = df_clean.count()

logger.info(f"[silver_market_data_clean] After dropping null fund_ticker: {final_count} rows (removed {before_drop_count - final_count})")

# ============================================================================
# Write to Iceberg
# ============================================================================

logger.info("[silver_market_data_clean] STEP 8: Writing to Iceberg table glue_catalog.finsights_silver.market_data_clean")

df_clean.writeTo("glue_catalog.finsights_silver.market_data_clean") \
    .tableProperty("format-version", "2") \
    .createOrReplace()

logger.info("[silver_market_data_clean] STEP 9: Write complete, verifying...")

# Verify write
df_verify = spark.table("glue_catalog.finsights_silver.market_data_clean")
verify_count = df_verify.count()

logger.info(f"[silver_market_data_clean] Verification: {verify_count} rows in Iceberg table")
logger.info("[silver_market_data_clean] Schema:")
df_verify.printSchema()
logger.info("[silver_market_data_clean] Sample cleaned data:")
df_verify.show(5, truncate=False)

logger.info("[silver_market_data_clean] STEP 10: Job complete")
logger.info(f"[silver_market_data_clean] Summary:")
logger.info(f"  - Input rows: {raw_count}")
logger.info(f"  - String expense ratios fixed: {string_format_count}")
logger.info(f"  - Invalid ratings nullified: {invalid_rating_count}")
logger.info(f"  - Beta nulls imputed: {beta_null_count}")
logger.info(f"  - Sharpe ratio nulls imputed: {sharpe_null_count}")
logger.info(f"  - Null fund_ticker rows removed: {before_drop_count - final_count}")
logger.info(f"  - Final rows: {verify_count}")

job.commit()
