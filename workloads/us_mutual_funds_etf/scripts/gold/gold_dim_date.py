"""
Gold Dim Date - US Mutual Funds & ETF Dataset
Creates date dimension from distinct price_date values in nav_clean.

JOB 7: Depends on JOB 4 (silver_nav_clean)
Input: glue_catalog.finsights_silver.nav_clean
Output: glue_catalog.finsights_gold.dim_date (Iceberg)
"""

from awsglue.context import GlueContext
from pyspark.context import SparkContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.sql import functions as F
import sys

# Initialize Glue context
args = getResolvedOptions(sys.argv, ["JOB_NAME"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)
logger = glueContext.get_logger()

logger.info("[gold_dim_date] STEP 1: Reading Silver nav_clean table")

# Read Silver NAV data
df_nav = spark.table("glue_catalog.finsights_silver.nav_clean")
nav_count = df_nav.count()

logger.info(f"[gold_dim_date] STEP 2: Loaded {nav_count} rows from nav_clean")

# ============================================================================
# Extract distinct dates
# ============================================================================

logger.info("[gold_dim_date] STEP 3: Extracting distinct price_date values")

df_dates = df_nav.select("price_date").distinct()
distinct_dates = df_dates.count()

logger.info(f"[gold_dim_date] Found {distinct_dates} distinct dates")

# ============================================================================
# Build date dimension attributes
# ============================================================================

logger.info("[gold_dim_date] STEP 4: Building date dimension attributes")

df_dim = df_dates.withColumnRenamed("price_date", "as_of_date") \
    .withColumn("month", F.month("as_of_date")) \
    .withColumn("month_name", F.date_format("as_of_date", "MMMM")) \
    .withColumn("quarter", F.quarter("as_of_date")) \
    .withColumn("year", F.year("as_of_date")) \
    .withColumn("date_key", F.monotonically_increasing_id() + 1) \
    .orderBy("as_of_date")

final_count = df_dim.count()
logger.info(f"[gold_dim_date] Built {final_count} date dimension rows")

# ============================================================================
# Write to Iceberg
# ============================================================================

logger.info("[gold_dim_date] STEP 5: Writing to Iceberg table glue_catalog.finsights_gold.dim_date")

df_dim.writeTo("glue_catalog.finsights_gold.dim_date") \
    .tableProperty("format-version", "2") \
    .createOrReplace()

logger.info("[gold_dim_date] STEP 6: Write complete, verifying...")

# Verify write
df_verify = spark.table("glue_catalog.finsights_gold.dim_date")
verify_count = df_verify.count()

logger.info(f"[gold_dim_date] Verification: {verify_count} rows in Iceberg table")
logger.info("[gold_dim_date] Schema:")
df_verify.printSchema()
logger.info("[gold_dim_date] Sample dim_date data:")
df_verify.show(10, truncate=False)

# Show distribution by year
logger.info("[gold_dim_date] Distribution by year:")
df_verify.groupBy("year").count().orderBy("year").show()

# Show distribution by quarter
logger.info("[gold_dim_date] Distribution by quarter:")
df_verify.groupBy("year", "quarter").count().orderBy("year", "quarter").show()

# Show date range
min_date = df_verify.agg(F.min("as_of_date")).collect()[0][0]
max_date = df_verify.agg(F.max("as_of_date")).collect()[0][0]
logger.info(f"[gold_dim_date] Date range: {min_date} to {max_date}")

logger.info("[gold_dim_date] STEP 7: Job complete")
logger.info(f"[gold_dim_date] Summary:")
logger.info(f"  - Source NAV rows: {nav_count}")
logger.info(f"  - Distinct dates: {distinct_dates}")
logger.info(f"  - Final dimension rows: {verify_count}")
logger.info(f"  - Date range: {min_date} to {max_date}")

job.commit()
