"""
Bronze Data Generation - US Mutual Funds & ETF Dataset
Generates synthetic fund data with realistic quality issues for testing.

JOB 1: No dependencies
Outputs: raw_funds, raw_market_data, raw_nav_prices (Parquet in S3)
"""

from awsglue.context import GlueContext
from pyspark.context import SparkContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType
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

logger.info("[bronze_data_generation] STEP 1: Starting synthetic data generation")

# ============================================================================
# DATASET 1: raw_funds (130 rows with quality issues)
# ============================================================================

logger.info("[bronze_data_generation] STEP 2: Generating raw_funds dataset")

# Define realistic ticker prefixes and suffixes
ticker_prefixes = ["V", "F", "SPY", "QQQ", "IWM", "VTI", "VOO", "BND", "AGG", "VNQ",
                   "XLF", "XLE", "XLK", "VEA", "VWO", "EMB", "HYG", "LQD", "TLT", "IEF",
                   "GLD", "SLV", "USO", "XOP", "ARKK", "SCHD", "VYM", "VIG", "DVY", "SDY"]
ticker_suffixes = ["", "X", "AX", "IX", "LW", "V", "W", "Z", "A", "B"]

# Generate base tickers (120 unique)
base_tickers = []
for i, prefix in enumerate(ticker_prefixes):
    for j, suffix in enumerate(ticker_suffixes[:4]):  # Use first 4 suffixes
        ticker = prefix + suffix
        base_tickers.append(ticker)
        if len(base_tickers) >= 120:
            break
    if len(base_tickers) >= 120:
        break

# Add 10 duplicates (same ticker repeated)
duplicate_tickers = base_tickers[:10]
all_tickers = base_tickers + duplicate_tickers  # 130 total

# Add 3 invalid tickers
all_tickers[120] = "???"
all_tickers[121] = "N/A"
all_tickers[122] = ""

# Generate fund data
funds_data = []
fund_names = [
    "Vanguard S&P 500 ETF", "Fidelity Total Market Index Fund", "BlackRock iShares Core ETF",
    "Invesco QQQ Trust", "SPDR S&P 500 ETF Trust", "Vanguard Total Stock Market ETF",
    "Vanguard 500 Index Fund", "iShares Core U.S. Aggregate Bond ETF", "Vanguard Total Bond Market ETF",
    "Vanguard Real Estate ETF", "Financial Select Sector SPDR Fund", "Energy Select Sector SPDR Fund",
    "Technology Select Sector SPDR Fund", "Vanguard FTSE Developed Markets ETF", "Vanguard FTSE Emerging Markets ETF"
]
management_companies = ["Vanguard", "Fidelity", "BlackRock", "Invesco", "T. Rowe Price",
                        "Schwab", "PIMCO", "Dimensional"]
categories = ["Large Cap Equity", "Total Market Equity", "Bond", "Real Estate",
              "Sector Equity", "International Equity", "Small Cap Equity"]
geo_focus = ["US", "Global", "Europe", "Asia Pacific", "Emerging Markets"]
sector_focus = ["Diversified", "Technology", "Healthcare", "Financial", "Energy",
                "Consumer", "Industrial", "Real Estate"]
fund_types = ["ETF", "etf", "E.T.F", "Mutual Fund", "mutual fund"]

for i, ticker in enumerate(all_tickers):
    # Generate mixed date formats (half YYYY-MM-DD, half MM/DD/YYYY)
    if i % 2 == 0:
        inception_date = f"20{10 + (i % 15):02d}-{1 + (i % 12):02d}-{1 + (i % 28):02d}"
    else:
        inception_date = f"{1 + (i % 12):02d}/{1 + (i % 28):02d}/20{10 + (i % 15):02d}"

    # Introduce quality issues
    fund_name = fund_names[i % len(fund_names)] if i % 26 != 0 else None  # 5 nulls
    fund_type = fund_types[i % len(fund_types)]

    funds_data.append((
        ticker,
        fund_name,
        fund_type,
        management_companies[i % len(management_companies)],
        inception_date,
        categories[i % len(categories)],
        geo_focus[i % len(geo_focus)],
        sector_focus[i % len(sector_focus)]
    ))

# Create DataFrame
funds_schema = StructType([
    StructField("fund_ticker", StringType(), True),
    StructField("fund_name", StringType(), True),
    StructField("fund_type", StringType(), True),
    StructField("management_company", StringType(), True),
    StructField("inception_date", StringType(), True),
    StructField("category", StringType(), True),
    StructField("geographic_focus", StringType(), True),
    StructField("sector_focus", StringType(), True)
])

df_funds = spark.createDataFrame(funds_data, funds_schema)

# Write to S3 as Parquet
output_path_funds = "s3://your-datalake-bucket/bronze/raw_funds/"
df_funds.write.mode("overwrite").parquet(output_path_funds)

logger.info(f"[bronze_data_generation] STEP 3: Written {df_funds.count()} rows to {output_path_funds}")
logger.info(f"[bronze_data_generation] Sample raw_funds data:")
df_funds.show(3, truncate=False)

# ============================================================================
# DATASET 2: raw_market_data (130 rows with quality issues)
# ============================================================================

logger.info("[bronze_data_generation] STEP 4: Generating raw_market_data dataset")

asset_classes = ["Equity", "Fixed Income", "Real Estate", "Commodities", "Mixed"]
benchmarks = ["S&P 500", "Russell 2000", "MSCI World", "Bloomberg Barclays Aggregate",
              "FTSE NAREIT", "MSCI Emerging Markets"]
morningstar_cats = ["Large Blend", "Large Growth", "Large Value", "Mid Blend", "Small Blend",
                   "Intermediate Bond", "Short-Term Bond", "High Yield Bond", "Real Estate"]

market_data = []
for i in range(130):
    ticker = base_tickers[i % 120]  # Use valid tickers only

    # Generate quality issues
    # 5 rows with expense_ratio as string "X.XX%" format
    if i < 5:
        expense_ratio = f"{0.05 + (i * 0.15):.2f}%"
    else:
        expense_ratio = 0.05 + (i % 50) * 0.01  # 0.05 to 0.54

    # 4 rows with invalid morningstar_rating
    if i == 0:
        rating = 0
    elif i == 1:
        rating = 6
    elif i == 2:
        rating = -1
    elif i == 3:
        rating = 99
    else:
        rating = 1 + (i % 5)  # 1-5

    # 6 nulls scattered across beta and sharpe_ratio
    beta = None if i % 22 == 0 else round(0.7 + (i % 10) * 0.15, 2)
    sharpe = None if i % 18 == 0 else round(0.5 + (i % 15) * 0.2, 2)

    market_data.append((
        ticker,  # Column named "ticker" not "fund_ticker" (key mismatch issue)
        asset_classes[i % len(asset_classes)],
        benchmarks[i % len(benchmarks)],
        morningstar_cats[i % len(morningstar_cats)],
        expense_ratio,
        round(1.0 + (i % 20) * 0.3, 2),  # dividend_yield_pct
        beta,
        sharpe,
        rating
    ))

market_schema = StructType([
    StructField("ticker", StringType(), True),  # Intentional mismatch
    StructField("asset_class", StringType(), True),
    StructField("benchmark_index", StringType(), True),
    StructField("morningstar_category", StringType(), True),
    StructField("expense_ratio_pct", StringType(), True),  # Mixed types
    StructField("dividend_yield_pct", DoubleType(), True),
    StructField("beta", DoubleType(), True),
    StructField("sharpe_ratio", DoubleType(), True),
    StructField("morningstar_rating", IntegerType(), True)
])

df_market = spark.createDataFrame(market_data, market_schema)

output_path_market = "s3://your-datalake-bucket/bronze/raw_market_data/"
df_market.write.mode("overwrite").parquet(output_path_market)

logger.info(f"[bronze_data_generation] STEP 5: Written {df_market.count()} rows to {output_path_market}")
logger.info(f"[bronze_data_generation] Sample raw_market_data data:")
df_market.show(3, truncate=False)

# ============================================================================
# DATASET 3: raw_nav_prices (150 rows with quality issues)
# ============================================================================

logger.info("[bronze_data_generation] STEP 6: Generating raw_nav_prices dataset")

# Generate data for 25 funds × ~6 monthly snapshots each
nav_data = []
selected_funds = base_tickers[:25]  # Use first 25 valid funds

# Add 3 orphan tickers (not in raw_funds)
orphan_tickers = ["ORPHAN1", "ORPHAN2", "ORPHAN3"]

nav_row_count = 0
for fund_idx, ticker in enumerate(selected_funds):
    # Each fund gets 6 monthly snapshots
    for month_offset in range(6):
        # Generate mixed date formats
        year = 2025
        month = 1 + month_offset
        day = 15

        if nav_row_count % 2 == 0:
            price_date = f"{year}-{month:02d}-{day:02d}"
        else:
            price_date = f"{month:02d}/{day:02d}/{year}"

        # Generate quality issues
        # 5 rows with nav <= 0
        if nav_row_count < 5:
            nav = -10.0 if nav_row_count == 0 else 0.0
        else:
            nav = 50.0 + fund_idx * 10 + month_offset * 2

        # 8 rows with returns outside -50 to +100 range
        if nav_row_count < 8:
            return_1yr = 9999.0 if nav_row_count % 2 == 0 else -500.0
        else:
            return_1yr = -5.0 + (fund_idx * 2.5) % 50

        nav_data.append((
            ticker,
            price_date,
            round(nav, 2),
            round(100.0 + fund_idx * 50 + month_offset * 10, 2),  # total_assets_millions
            round(-2.0 + (fund_idx % 10) * 1.5, 2),  # return_1mo_pct
            round(-3.0 + (fund_idx % 15) * 2.0, 2),  # return_3mo_pct
            round(-5.0 + (fund_idx % 20) * 2.5, 2),  # return_ytd_pct
            return_1yr,
            round(-8.0 + (fund_idx % 25) * 3.0, 2),  # return_3yr_pct
            round(-10.0 + (fund_idx % 30) * 3.5, 2)  # return_5yr_pct
        ))
        nav_row_count += 1

# Add 3 orphan rows
for orphan in orphan_tickers:
    nav_data.append((
        orphan,
        "2025-06-15",
        100.0,
        500.0,
        2.5,
        5.0,
        8.0,
        12.0,
        15.0,
        20.0
    ))

nav_schema = StructType([
    StructField("fund_ticker", StringType(), True),
    StructField("price_date", StringType(), True),
    StructField("nav", DoubleType(), True),
    StructField("total_assets_millions", DoubleType(), True),
    StructField("return_1mo_pct", DoubleType(), True),
    StructField("return_3mo_pct", DoubleType(), True),
    StructField("return_ytd_pct", DoubleType(), True),
    StructField("return_1yr_pct", DoubleType(), True),
    StructField("return_3yr_pct", DoubleType(), True),
    StructField("return_5yr_pct", DoubleType(), True)
])

df_nav = spark.createDataFrame(nav_data, nav_schema)

output_path_nav = "s3://your-datalake-bucket/bronze/raw_nav_prices/"
df_nav.write.mode("overwrite").parquet(output_path_nav)

logger.info(f"[bronze_data_generation] STEP 7: Written {df_nav.count()} rows to {output_path_nav}")
logger.info(f"[bronze_data_generation] Sample raw_nav_prices data:")
df_nav.show(3, truncate=False)

logger.info("[bronze_data_generation] STEP 8: Data generation complete")
logger.info(f"[bronze_data_generation] Summary:")
logger.info(f"  - raw_funds: {df_funds.count()} rows")
logger.info(f"  - raw_market_data: {df_market.count()} rows")
logger.info(f"  - raw_nav_prices: {df_nav.count()} rows")

job.commit()
