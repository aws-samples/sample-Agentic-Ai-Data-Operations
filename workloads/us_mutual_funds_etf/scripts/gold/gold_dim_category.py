"""
Gold Dim Category - US Mutual Funds & ETF Dataset
Creates category dimension with surrogate keys.

JOB 6: Depends on JOB 2 (silver_funds_clean) and JOB 3 (silver_market_data_clean)
Input: glue_catalog.finsights_silver.funds_clean, glue_catalog.finsights_silver.market_data_clean
Output: glue_catalog.finsights_gold.dim_category (Iceberg)
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

logger.info("[gold_dim_category] STEP 1: Reading Silver tables")

# Read Silver tables
df_funds = spark.table("glue_catalog.finsights_silver.funds_clean")
df_market = spark.table("glue_catalog.finsights_silver.market_data_clean")

funds_count = df_funds.count()
market_count = df_market.count()

logger.info(f"[gold_dim_category] STEP 2: Loaded data from Silver")
logger.info(f"  - funds_clean: {funds_count} rows")
logger.info(f"  - market_data_clean: {market_count} rows")

# ============================================================================
# Join funds with market data
# ============================================================================

logger.info("[gold_dim_category] STEP 3: Joining funds_clean with market_data_clean on fund_ticker")

df_joined = df_funds.join(df_market, "fund_ticker", "inner")

# ============================================================================
# Extract distinct category combinations
# ============================================================================

logger.info("[gold_dim_category] STEP 4: Extracting distinct category combinations")

df_categories = df_joined.select(
    "fund_category",
    "asset_class",
    "morningstar_category",
    "benchmark_index",
    "geographic_focus"
).distinct()

categories_count = df_categories.count()
logger.info(f"[gold_dim_category] Found {categories_count} distinct category combinations")

# ============================================================================
# Calculate typical expense range per fund_category
# ============================================================================

logger.info("[gold_dim_category] STEP 5: Calculating typical expense ratio ranges per fund_category")

df_expense_agg = df_joined.groupBy("fund_category").agg(
    F.min("expense_ratio_pct").alias("typical_expense_min"),
    F.max("expense_ratio_pct").alias("typical_expense_max")
)

expense_agg_count = df_expense_agg.count()
logger.info(f"[gold_dim_category] Calculated expense ranges for {expense_agg_count} fund categories")

# ============================================================================
# Join categories with expense aggregations
# ============================================================================

logger.info("[gold_dim_category] STEP 6: Joining categories with expense aggregations")

df_dim = df_categories.join(df_expense_agg, "fund_category", "left")

# ============================================================================
# Add surrogate key
# ============================================================================

logger.info("[gold_dim_category] STEP 7: Adding surrogate key (category_key)")

df_dim = df_dim.withColumn("category_key", F.monotonically_increasing_id() + 1)

final_count = df_dim.count()
logger.info(f"[gold_dim_category] Final dimension rows: {final_count}")

# ============================================================================
# Write to Iceberg
# ============================================================================

logger.info("[gold_dim_category] STEP 8: Writing to Iceberg table glue_catalog.finsights_gold.dim_category")

df_dim.writeTo("glue_catalog.finsights_gold.dim_category") \
    .tableProperty("format-version", "2") \
    .createOrReplace()

logger.info("[gold_dim_category] STEP 9: Write complete, verifying...")

# Verify write
df_verify = spark.table("glue_catalog.finsights_gold.dim_category")
verify_count = df_verify.count()

logger.info(f"[gold_dim_category] Verification: {verify_count} rows in Iceberg table")
logger.info("[gold_dim_category] Schema:")
df_verify.printSchema()
logger.info("[gold_dim_category] Sample dim_category data:")
df_verify.show(5, truncate=False)

# Show distribution by asset_class
logger.info("[gold_dim_category] Distribution by asset_class:")
df_verify.groupBy("asset_class").count().show()

# Show expense ratio ranges
logger.info("[gold_dim_category] Sample expense ratio ranges:")
df_verify.select("fund_category", "typical_expense_min", "typical_expense_max") \
    .orderBy("typical_expense_min") \
    .show(10)

logger.info("[gold_dim_category] STEP 10: Job complete")
logger.info(f"[gold_dim_category] Summary:")
logger.info(f"  - Distinct category combinations: {categories_count}")
logger.info(f"  - Expense ranges calculated for {expense_agg_count} categories")
logger.info(f"  - Final dimension rows: {verify_count}")

job.commit()
