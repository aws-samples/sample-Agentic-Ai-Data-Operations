"""
Gold Dim Fund - US Mutual Funds & ETF Dataset
Creates fund dimension by joining Silver funds_clean and market_data_clean.

JOB 5: Depends on JOB 2 (silver_funds_clean) and JOB 3 (silver_market_data_clean)
Input: glue_catalog.finsights_silver.funds_clean, glue_catalog.finsights_silver.market_data_clean
Output: glue_catalog.finsights_gold.dim_fund (Iceberg)
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

logger.info("[gold_dim_fund] STEP 1: Reading Silver tables")

# Read Silver tables
df_funds = spark.table("glue_catalog.finsights_silver.funds_clean")
df_market = spark.table("glue_catalog.finsights_silver.market_data_clean")

funds_count = df_funds.count()
market_count = df_market.count()

logger.info(f"[gold_dim_fund] STEP 2: Loaded data from Silver")
logger.info(f"  - funds_clean: {funds_count} rows")
logger.info(f"  - market_data_clean: {market_count} rows")

# ============================================================================
# Join funds with market data
# ============================================================================

logger.info("[gold_dim_fund] STEP 3: Joining funds_clean with market_data_clean on fund_ticker")

df_joined = df_funds.join(df_market, "fund_ticker", "inner")
joined_count = df_joined.count()

logger.info(f"[gold_dim_fund] After join: {joined_count} rows")

# ============================================================================
# Select columns for dim_fund
# ============================================================================

logger.info("[gold_dim_fund] STEP 4: Selecting columns for dim_fund")

df_dim = df_joined.select(
    "fund_ticker",
    "fund_name",
    "fund_type",
    "management_company",
    "inception_date",
    "fund_category",
    "geographic_focus",
    "sector_focus",
    "asset_class",
    "benchmark_index",
    "morningstar_category"
).dropDuplicates(["fund_ticker"])

final_count = df_dim.count()
logger.info(f"[gold_dim_fund] After deduplication: {final_count} rows")

# ============================================================================
# Write to Iceberg
# ============================================================================

logger.info("[gold_dim_fund] STEP 5: Writing to Iceberg table glue_catalog.finsights_gold.dim_fund")

df_dim.writeTo("glue_catalog.finsights_gold.dim_fund") \
    .tableProperty("format-version", "2") \
    .createOrReplace()

logger.info("[gold_dim_fund] STEP 6: Write complete, verifying...")

# Verify write
df_verify = spark.table("glue_catalog.finsights_gold.dim_fund")
verify_count = df_verify.count()

logger.info(f"[gold_dim_fund] Verification: {verify_count} rows in Iceberg table")
logger.info("[gold_dim_fund] Schema:")
df_verify.printSchema()
logger.info("[gold_dim_fund] Sample dim_fund data:")
df_verify.show(5, truncate=False)

# Show distribution by fund_type
logger.info("[gold_dim_fund] Distribution by fund_type:")
df_verify.groupBy("fund_type").count().show()

# Show distribution by management_company
logger.info("[gold_dim_fund] Top 5 management companies:")
df_verify.groupBy("management_company").count().orderBy(F.desc("count")).show(5)

logger.info("[gold_dim_fund] STEP 7: Job complete")
logger.info(f"[gold_dim_fund] Summary:")
logger.info(f"  - Input funds: {funds_count}")
logger.info(f"  - Input market data: {market_count}")
logger.info(f"  - Joined rows: {joined_count}")
logger.info(f"  - Final dimension rows: {verify_count}")

job.commit()
