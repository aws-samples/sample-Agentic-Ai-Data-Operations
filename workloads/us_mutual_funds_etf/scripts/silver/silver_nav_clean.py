"""
Silver NAV Clean - US Mutual Funds & ETF Dataset
Reads raw_nav_prices from Bronze and applies cleaning rules.

JOB 4: Depends on JOB 1 (bronze_data_generation) and JOB 2 (silver_funds_clean)
Input: s3://your-datalake-bucket/bronze/raw_nav_prices/, glue_catalog.finsights_silver.funds_clean
Output: glue_catalog.finsights_silver.nav_clean (Iceberg, partitioned by year)
"""

from awsglue.context import GlueContext
from pyspark.context import SparkContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.sql import functions as F
from pyspark.sql.types import DateType
import sys

# Initialize Glue context
args = getResolvedOptions(sys.argv, ["JOB_NAME"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)
logger = glueContext.get_logger()

logger.info("[silver_nav_clean] STEP 1: Reading Bronze raw_nav_prices data")

# Read Bronze data
input_path = "s3://your-datalake-bucket/bronze/raw_nav_prices/"
df_raw = spark.read.parquet(input_path)
raw_count = df_raw.count()

logger.info(f"[silver_nav_clean] STEP 2: Loaded {raw_count} rows from Bronze")
logger.info("[silver_nav_clean] Sample raw data:")
df_raw.show(5, truncate=False)

# ============================================================================
# CLEANING STEP 1: Standardize price_date to DateType
# ============================================================================

logger.info("[silver_nav_clean] STEP 3: Standardizing price_date to DateType")

df_step1 = df_raw.withColumn(
    "price_date",
    F.coalesce(
        F.to_date(F.col("price_date"), "yyyy-MM-dd"),
        F.to_date(F.col("price_date"), "MM/dd/yyyy")
    )
)

logger.info("[silver_nav_clean] price_date converted to DateType (handled both formats)")

# ============================================================================
# CLEANING STEP 2: Drop rows where nav <= 0
# ============================================================================

logger.info("[silver_nav_clean] STEP 4: Dropping rows where nav <= 0")

invalid_nav_count = df_step1.filter((F.col("nav") <= 0) | F.col("nav").isNull()).count()
logger.info(f"[silver_nav_clean] Found {invalid_nav_count} rows with nav <= 0 or null")

df_step2 = df_step1.filter((F.col("nav") > 0) & F.col("nav").isNotNull())
step2_count = df_step2.count()

logger.info(f"[silver_nav_clean] After dropping invalid nav: {step2_count} rows")

# ============================================================================
# CLEANING STEP 3: Clamp return columns (values outside -50 to +100 → null)
# ============================================================================

logger.info("[silver_nav_clean] STEP 5: Clamping return columns (valid range: -50 to +100)")

return_columns = ["return_1mo_pct", "return_3mo_pct", "return_ytd_pct",
                  "return_1yr_pct", "return_3yr_pct", "return_5yr_pct"]

# Count outliers before clamping
outlier_counts = {}
for col in return_columns:
    count = df_step2.filter((F.col(col) < -50) | (F.col(col) > 100)).count()
    outlier_counts[col] = count
    logger.info(f"[silver_nav_clean] {col}: {count} outliers")

df_step3 = df_step2
for col in return_columns:
    df_step3 = df_step3.withColumn(
        col,
        F.when((F.col(col) >= -50) & (F.col(col) <= 100), F.col(col)).otherwise(None)
    )

logger.info(f"[silver_nav_clean] Clamped return columns, set {sum(outlier_counts.values())} outlier values to null")

# ============================================================================
# CLEANING STEP 4: Drop orphan records (fund_ticker not in funds_clean)
# ============================================================================

logger.info("[silver_nav_clean] STEP 6: Loading valid fund_tickers from finsights_silver.funds_clean")

df_valid_funds = spark.table("glue_catalog.finsights_silver.funds_clean").select("fund_ticker")
valid_fund_count = df_valid_funds.count()
logger.info(f"[silver_nav_clean] Found {valid_fund_count} valid funds in Silver")

logger.info("[silver_nav_clean] STEP 7: Dropping orphan records (fund_ticker not in funds_clean)")

before_drop_count = df_step3.count()
df_step4 = df_step3.join(df_valid_funds, "fund_ticker", "inner")
after_drop_count = df_step4.count()

orphan_count = before_drop_count - after_drop_count
logger.info(f"[silver_nav_clean] Removed {orphan_count} orphan records")

# ============================================================================
# CLEANING STEP 5: Sort by fund_ticker, price_date ASC
# ============================================================================

logger.info("[silver_nav_clean] STEP 8: Sorting by fund_ticker, price_date ASC")

df_clean = df_step4.orderBy("fund_ticker", "price_date")
final_count = df_clean.count()

logger.info(f"[silver_nav_clean] Final cleaned row count: {final_count}")

# ============================================================================
# Write to Iceberg (partitioned by year)
# ============================================================================

logger.info("[silver_nav_clean] STEP 9: Writing to Iceberg table glue_catalog.finsights_silver.nav_clean (partitioned by year)")

df_clean.writeTo("glue_catalog.finsights_silver.nav_clean") \
    .partitionedBy(F.years("price_date")) \
    .tableProperty("format-version", "2") \
    .createOrReplace()

logger.info("[silver_nav_clean] STEP 10: Write complete, verifying...")

# Verify write
df_verify = spark.table("glue_catalog.finsights_silver.nav_clean")
verify_count = df_verify.count()

logger.info(f"[silver_nav_clean] Verification: {verify_count} rows in Iceberg table")
logger.info("[silver_nav_clean] Schema:")
df_verify.printSchema()
logger.info("[silver_nav_clean] Sample cleaned data:")
df_verify.show(5, truncate=False)

# Show partition distribution
logger.info("[silver_nav_clean] Partition distribution:")
df_verify.groupBy(F.year("price_date").alias("year")).count().orderBy("year").show()

logger.info("[silver_nav_clean] STEP 11: Job complete")
logger.info(f"[silver_nav_clean] Summary:")
logger.info(f"  - Input rows: {raw_count}")
logger.info(f"  - Invalid nav removed: {invalid_nav_count}")
logger.info(f"  - Return outliers clamped: {sum(outlier_counts.values())}")
logger.info(f"  - Orphan records removed: {orphan_count}")
logger.info(f"  - Final rows: {verify_count}")

job.commit()
