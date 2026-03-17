"""
Gold Fact Fund Performance - US Mutual Funds & ETF Dataset
Creates fact table by joining Silver NAV data with all Gold dimensions.

JOB 8: Depends on JOB 4 (silver_nav_clean), JOB 5 (gold_dim_fund), JOB 6 (gold_dim_category), JOB 7 (gold_dim_date)
Input: Silver nav_clean, market_data_clean; Gold dim_fund, dim_category, dim_date
Output: glue_catalog.finsights_gold.fact_fund_performance (Iceberg, partitioned by year)
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

logger.info("[gold_fact_fund_performance] STEP 1: Reading Silver and Gold tables")

# Read Silver tables
df_nav = spark.table("glue_catalog.finsights_silver.nav_clean")
df_market = spark.table("glue_catalog.finsights_silver.market_data_clean")

# Read Gold dimensions
df_dim_fund = spark.table("glue_catalog.finsights_gold.dim_fund")
df_dim_category = spark.table("glue_catalog.finsights_gold.dim_category")
df_dim_date = spark.table("glue_catalog.finsights_gold.dim_date")

logger.info(f"[gold_fact_fund_performance] STEP 2: Loaded source tables")
logger.info(f"  - nav_clean: {df_nav.count()} rows")
logger.info(f"  - market_data_clean: {df_market.count()} rows")
logger.info(f"  - dim_fund: {df_dim_fund.count()} rows")
logger.info(f"  - dim_category: {df_dim_category.count()} rows")
logger.info(f"  - dim_date: {df_dim_date.count()} rows")

# ============================================================================
# Join NAV with dim_fund
# ============================================================================

logger.info("[gold_fact_fund_performance] STEP 3: Joining nav_clean with dim_fund")

df_fact = df_nav.alias("nav").join(
    df_dim_fund.alias("df"),
    "fund_ticker",
    "inner"
)

step3_count = df_fact.count()
logger.info(f"[gold_fact_fund_performance] After joining with dim_fund: {step3_count} rows")

# ============================================================================
# Join with dim_date
# ============================================================================

logger.info("[gold_fact_fund_performance] STEP 4: Joining with dim_date")

df_fact = df_fact.join(
    df_dim_date.alias("dd"),
    F.col("nav.price_date") == F.col("dd.as_of_date"),
    "inner"
)

step4_count = df_fact.count()
logger.info(f"[gold_fact_fund_performance] After joining with dim_date: {step4_count} rows")

# ============================================================================
# Join with dim_category
# ============================================================================

logger.info("[gold_fact_fund_performance] STEP 5: Joining with dim_category")

df_fact = df_fact.join(
    df_dim_category.alias("dc"),
    F.col("df.fund_category") == F.col("dc.fund_category"),
    "left"
)

step5_count = df_fact.count()
logger.info(f"[gold_fact_fund_performance] After joining with dim_category: {step5_count} rows")

# ============================================================================
# Join with market_data_clean for metrics
# ============================================================================

logger.info("[gold_fact_fund_performance] STEP 6: Joining with market_data_clean for metrics")

df_fact = df_fact.join(
    df_market.alias("m"),
    "fund_ticker",
    "left"
)

step6_count = df_fact.count()
logger.info(f"[gold_fact_fund_performance] After joining with market_data_clean: {step6_count} rows")

# ============================================================================
# Select fact columns (only FKs and measures)
# ============================================================================

logger.info("[gold_fact_fund_performance] STEP 7: Selecting fact table columns")

df_final = df_fact.select(
    F.col("nav.fund_ticker"),
    F.col("dc.category_key"),
    F.col("dd.date_key"),
    F.col("nav.price_date"),  # Keep for partitioning
    F.col("nav.nav"),
    F.col("nav.total_assets_millions"),
    F.col("m.expense_ratio_pct"),
    F.col("m.dividend_yield_pct"),
    F.col("m.beta"),
    F.col("m.sharpe_ratio"),
    F.col("m.morningstar_rating"),
    F.col("nav.return_1mo_pct"),
    F.col("nav.return_3mo_pct"),
    F.col("nav.return_ytd_pct"),
    F.col("nav.return_1yr_pct"),
    F.col("nav.return_3yr_pct"),
    F.col("nav.return_5yr_pct")
).withColumn("fact_id", F.monotonically_increasing_id() + 1)

final_count = df_final.count()
logger.info(f"[gold_fact_fund_performance] Final fact table rows: {final_count}")

# ============================================================================
# Write to Iceberg (partitioned by year)
# ============================================================================

logger.info("[gold_fact_fund_performance] STEP 8: Writing to Iceberg table glue_catalog.finsights_gold.fact_fund_performance (partitioned by year)")

df_final.writeTo("glue_catalog.finsights_gold.fact_fund_performance") \
    .partitionedBy(F.years("price_date")) \
    .tableProperty("format-version", "2") \
    .tableProperty("write.target-file-size-bytes", "134217728") \
    .createOrReplace()

logger.info("[gold_fact_fund_performance] STEP 9: Write complete, verifying...")

# Verify write
df_verify = spark.table("glue_catalog.finsights_gold.fact_fund_performance")
verify_count = df_verify.count()

logger.info(f"[gold_fact_fund_performance] Verification: {verify_count} rows in Iceberg table")
logger.info("[gold_fact_fund_performance] Schema:")
df_verify.printSchema()
logger.info("[gold_fact_fund_performance] Sample fact data:")
df_verify.show(5, truncate=False)

# Show partition distribution
logger.info("[gold_fact_fund_performance] Partition distribution:")
df_verify.groupBy(F.year("price_date").alias("year")).count().orderBy("year").show()

# Show row count by fund type (requires re-join with dim_fund)
logger.info("[gold_fact_fund_performance] Row count by fund (top 10):")
df_verify.groupBy("fund_ticker").count().orderBy(F.desc("count")).show(10)

# Show measure statistics
logger.info("[gold_fact_fund_performance] Measure statistics:")
df_verify.select(
    F.avg("nav").alias("avg_nav"),
    F.avg("total_assets_millions").alias("avg_aum"),
    F.avg("return_1yr_pct").alias("avg_1yr_return"),
    F.avg("sharpe_ratio").alias("avg_sharpe")
).show()

logger.info("[gold_fact_fund_performance] STEP 10: Job complete")
logger.info(f"[gold_fact_fund_performance] Summary:")
logger.info(f"  - Input NAV rows: {df_nav.count()}")
logger.info(f"  - After dim_fund join: {step3_count}")
logger.info(f"  - After dim_date join: {step4_count}")
logger.info(f"  - After dim_category join: {step5_count}")
logger.info(f"  - After market_data join: {step6_count}")
logger.info(f"  - Final fact rows: {verify_count}")

job.commit()
