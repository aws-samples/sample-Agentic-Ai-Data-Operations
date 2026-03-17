"""
Integration Tests for US Mutual Funds & ETF Transformation Pipeline
Tests full Bronze→Silver→Gold flow with sample data.
"""

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType, DateType
from pyspark.sql.window import Window
from datetime import date
import tempfile
import shutil


@pytest.fixture(scope="module")
def spark():
    """Create a Spark session with Iceberg configuration."""
    spark = SparkSession.builder \
        .appName("test_us_mutual_funds_etf_integration") \
        .master("local[2]") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
        .config("spark.sql.catalog.local_catalog", "org.apache.iceberg.spark.SparkCatalog") \
        .config("spark.sql.catalog.local_catalog.type", "hadoop") \
        .config("spark.sql.catalog.local_catalog.warehouse", tempfile.mkdtemp()) \
        .getOrCreate()
    yield spark
    spark.stop()


@pytest.fixture(scope="module")
def sample_bronze_funds(spark):
    """Create sample Bronze funds data with quality issues."""
    data = [
        # Valid records
        ("VTI", "Vanguard Total Stock Market ETF", "ETF", "Vanguard", "2025-01-15", "Large Cap Equity", "US", "Diversified"),
        ("VOO", "Vanguard S&P 500 ETF", "etf", "Vanguard", "01/15/2024", "Large Cap Equity", "US", "Diversified"),
        ("SPY", "SPDR S&P 500 ETF Trust", "E.T.F", "BlackRock", "2023-06-01", "Large Cap Equity", "US", "Diversified"),
        # Duplicate ticker
        ("VTI", "Duplicate Fund", "ETF", "Fidelity", "2025-02-01", "Large Cap Equity", "US", "Diversified"),
        # Null fund_name
        ("BND", None, "Mutual Fund", "Vanguard", "2024-01-01", "Bond", "US", "Diversified"),
        # Invalid tickers
        ("???", "Invalid Fund 1", "ETF", "Unknown", "2025-01-01", "Unknown", "US", "Diversified"),
        ("N/A", "Invalid Fund 2", "ETF", "Unknown", "2025-01-01", "Unknown", "US", "Diversified"),
        ("", "Invalid Fund 3", "ETF", "Unknown", "2025-01-01", "Unknown", "US", "Diversified"),
        # Valid additional funds
        ("QQQ", "Invesco QQQ Trust", "mutual fund", "Invesco", "12/01/2023", "Technology", "US", "Technology"),
        ("AGG", "iShares Core Aggregate Bond ETF", "ETF", "BlackRock", "2024-06-15", "Bond", "US", "Diversified")
    ]
    schema = StructType([
        StructField("fund_ticker", StringType(), True),
        StructField("fund_name", StringType(), True),
        StructField("fund_type", StringType(), True),
        StructField("management_company", StringType(), True),
        StructField("inception_date", StringType(), True),
        StructField("category", StringType(), True),
        StructField("geographic_focus", StringType(), True),
        StructField("sector_focus", StringType(), True)
    ])
    return spark.createDataFrame(data, schema)


@pytest.fixture(scope="module")
def sample_bronze_market(spark):
    """Create sample Bronze market data with quality issues."""
    data = [
        ("VTI", "Equity", "S&P 500", "Large Blend", "0.03%", 1.5, 1.0, 1.2, 5),  # String expense
        ("VOO", "Equity", "S&P 500", "Large Blend", 0.03, 1.5, 1.0, 1.1, 5),
        ("SPY", "Equity", "S&P 500", "Large Blend", 0.09, 1.6, 0.98, 1.0, 4),
        ("BND", "Fixed Income", "Bloomberg Barclays Aggregate", "Intermediate Bond", 0.03, 2.0, None, 0.5, 4),  # Null beta
        ("QQQ", "Equity", "NASDAQ 100", "Technology", 0.20, 1.0, 1.5, None, 6),  # Invalid rating, null sharpe
        ("AGG", "Fixed Income", "Bloomberg Barclays Aggregate", "Intermediate Bond", 0.04, 2.1, 0.5, 0.6, 0)  # Invalid rating
    ]
    schema = StructType([
        StructField("ticker", StringType(), True),  # Column name mismatch
        StructField("asset_class", StringType(), True),
        StructField("benchmark_index", StringType(), True),
        StructField("morningstar_category", StringType(), True),
        StructField("expense_ratio_pct", StringType(), True),
        StructField("dividend_yield_pct", DoubleType(), True),
        StructField("beta", DoubleType(), True),
        StructField("sharpe_ratio", DoubleType(), True),
        StructField("morningstar_rating", IntegerType(), True)
    ])
    return spark.createDataFrame(data, schema)


@pytest.fixture(scope="module")
def sample_bronze_nav(spark):
    """Create sample Bronze NAV data with quality issues."""
    data = [
        # Valid records
        ("VTI", "2025-01-15", 250.0, 1500.0, 2.5, 5.0, 8.0, 12.0, 15.0, 20.0),
        ("VTI", "02/15/2025", 252.0, 1510.0, 2.0, 4.5, 7.5, 11.5, 14.5, 19.5),
        ("VOO", "2025-01-15", 450.0, 2000.0, 2.4, 4.9, 7.9, 11.9, 14.9, 19.9),
        ("SPY", "2025-01-15", 475.0, 3000.0, 2.6, 5.1, 8.1, 12.1, 15.1, 20.1),
        # Invalid NAV (negative)
        ("BND", "2025-01-15", -10.0, 500.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
        # Invalid NAV (zero)
        ("QQQ", "2025-01-15", 0.0, 800.0, 3.0, 6.0, 9.0, 15.0, 18.0, 25.0),
        # Outlier returns
        ("AGG", "2025-01-15", 110.0, 900.0, 9999.0, -500.0, 150.0, 12.0, 15.0, 20.0),
        # Orphan record (ticker not in funds)
        ("ORPHAN1", "2025-01-15", 100.0, 200.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
        # Valid additional records
        ("VOO", "02/15/2025", 452.0, 2010.0, 2.3, 4.8, 7.8, 11.8, 14.8, 19.8),
        ("SPY", "02/15/2025", 477.0, 3010.0, 2.5, 5.0, 8.0, 12.0, 15.0, 20.0)
    ]
    schema = StructType([
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
    return spark.createDataFrame(data, schema)


# ============================================================================
# Test Bronze → Silver: Funds Clean
# ============================================================================

class TestBronzeToSilverFunds:
    """Test Bronze to Silver transformation for funds data."""

    def test_row_count_after_cleaning(self, spark, sample_bronze_funds):
        """Test that invalid and duplicate rows are removed."""
        # Apply cleaning logic
        df_clean = sample_bronze_funds.filter(
            (F.col("fund_ticker").isNotNull()) &
            (F.col("fund_ticker") != "???") &
            (F.col("fund_ticker") != "N/A") &
            (F.col("fund_ticker") != "")
        )

        window_spec = Window.partitionBy("fund_ticker").orderBy(F.lit(1))
        df_clean = df_clean.withColumn("row_num", F.row_number().over(window_spec)) \
            .filter(F.col("row_num") == 1) \
            .drop("row_num")

        result = df_clean.count()
        # Should have 6 unique valid tickers: VTI, VOO, SPY, BND, QQQ, AGG
        assert result == 6, f"Expected 6 rows after cleaning, got {result}"

    def test_fund_type_standardization(self, spark, sample_bronze_funds):
        """Test that fund_type values are standardized."""
        df_clean = sample_bronze_funds.withColumn(
            "fund_type",
            F.when(F.upper(F.regexp_replace(F.col("fund_type"), "[^A-Za-z]", "")) == "ETF", "ETF")
             .when(F.upper(F.col("fund_type")).contains("MUTUAL"), "Mutual Fund")
             .otherwise(F.col("fund_type"))
        )

        etf_count = df_clean.filter(F.col("fund_type") == "ETF").count()
        mf_count = df_clean.filter(F.col("fund_type") == "Mutual Fund").count()

        # ETF variants: ETF, etf, E.T.F appear in data
        assert etf_count >= 3, "ETF variants should be standardized"
        assert mf_count >= 1, "Mutual Fund variants should be standardized"

    def test_null_fund_name_filled(self, spark, sample_bronze_funds):
        """Test that null fund_name is filled with 'Unknown Fund'."""
        df_clean = sample_bronze_funds.withColumn(
            "fund_name",
            F.when(F.col("fund_name").isNull(), "Unknown Fund").otherwise(F.col("fund_name"))
        )

        null_count = df_clean.filter(F.col("fund_name").isNull()).count()
        assert null_count == 0, "No null fund_name values should remain"

        unknown_count = df_clean.filter(F.col("fund_name") == "Unknown Fund").count()
        assert unknown_count == 1, "BND fund should have 'Unknown Fund' name"

    def test_date_parsing(self, spark, sample_bronze_funds):
        """Test that mixed date formats are parsed correctly."""
        df_clean = sample_bronze_funds.withColumn(
            "inception_date",
            F.coalesce(
                F.to_date(F.col("inception_date"), "yyyy-MM-dd"),
                F.to_date(F.col("inception_date"), "MM/dd/yyyy")
            )
        )

        null_count = df_clean.filter(F.col("inception_date").isNull()).count()
        assert null_count == 0, "All dates should parse successfully"


# ============================================================================
# Test Bronze → Silver: Market Data Clean
# ============================================================================

class TestBronzeToSilverMarket:
    """Test Bronze to Silver transformation for market data."""

    def test_column_rename(self, spark, sample_bronze_market):
        """Test that ticker column is renamed to fund_ticker."""
        df_clean = sample_bronze_market.withColumnRenamed("ticker", "fund_ticker")

        assert "fund_ticker" in df_clean.columns, "Column should be renamed to fund_ticker"
        assert "ticker" not in df_clean.columns, "Original ticker column should not exist"

    def test_expense_ratio_cleaning(self, spark, sample_bronze_market):
        """Test that expense_ratio_pct is cleaned and cast to double."""
        df_clean = sample_bronze_market.withColumn(
            "expense_ratio_pct",
            F.when(
                F.col("expense_ratio_pct").cast("string").rlike("%$"),
                F.regexp_replace(F.col("expense_ratio_pct").cast("string"), "%", "").cast(DoubleType())
            ).otherwise(F.col("expense_ratio_pct").cast(DoubleType()))
        )

        # Check all are numeric
        null_count = df_clean.filter(F.col("expense_ratio_pct").isNull()).count()
        assert null_count == 0, "All expense ratios should be numeric"

        # Check specific value
        vti_expense = df_clean.filter(F.col("ticker") == "VTI").select("expense_ratio_pct").collect()[0][0]
        assert vti_expense == 0.03, "VTI expense ratio should be 0.03"

    def test_morningstar_rating_clamping(self, spark, sample_bronze_market):
        """Test that invalid morningstar ratings are set to null."""
        df_clean = sample_bronze_market.withColumn(
            "morningstar_rating",
            F.when(
                (F.col("morningstar_rating") >= 1) & (F.col("morningstar_rating") <= 5),
                F.col("morningstar_rating")
            ).otherwise(None)
        )

        # QQQ has rating 6, AGG has rating 0 - both should be null
        invalid_count = df_clean.filter(
            (F.col("ticker") == "QQQ") | (F.col("ticker") == "AGG")
        ).filter(F.col("morningstar_rating").isNull()).count()

        assert invalid_count == 2, "Invalid ratings should be set to null"

    def test_null_imputation(self, spark, sample_bronze_market):
        """Test that null beta and sharpe_ratio are imputed."""
        # Calculate medians
        beta_median = sample_bronze_market.approxQuantile("beta", [0.5], 0.01)[0]
        sharpe_median = sample_bronze_market.approxQuantile("sharpe_ratio", [0.5], 0.01)[0]

        df_clean = sample_bronze_market.withColumn(
            "beta",
            F.when(F.col("beta").isNull(), F.lit(beta_median)).otherwise(F.col("beta"))
        ).withColumn(
            "sharpe_ratio",
            F.when(F.col("sharpe_ratio").isNull(), F.lit(sharpe_median)).otherwise(F.col("sharpe_ratio"))
        )

        null_beta_count = df_clean.filter(F.col("beta").isNull()).count()
        null_sharpe_count = df_clean.filter(F.col("sharpe_ratio").isNull()).count()

        assert null_beta_count == 0, "All beta nulls should be imputed"
        assert null_sharpe_count == 0, "All sharpe_ratio nulls should be imputed"


# ============================================================================
# Test Bronze → Silver: NAV Clean
# ============================================================================

class TestBronzeToSilverNAV:
    """Test Bronze to Silver transformation for NAV data."""

    def test_invalid_nav_filtering(self, spark, sample_bronze_nav):
        """Test that negative and zero NAV values are filtered."""
        df_clean = sample_bronze_nav.filter((F.col("nav") > 0) & F.col("nav").isNotNull())

        # BND has -10.0, QQQ has 0.0 - should be filtered
        result = df_clean.count()
        assert result <= 8, "Invalid NAV rows should be filtered"

    def test_return_outlier_clamping(self, spark, sample_bronze_nav):
        """Test that return outliers are set to null."""
        return_columns = ["return_1mo_pct", "return_3mo_pct", "return_ytd_pct",
                         "return_1yr_pct", "return_3yr_pct", "return_5yr_pct"]

        df_clean = sample_bronze_nav
        for col in return_columns:
            df_clean = df_clean.withColumn(
                col,
                F.when((F.col(col) >= -50) & (F.col(col) <= 100), F.col(col)).otherwise(None)
            )

        # AGG has 9999, -500, 150 as outliers
        agg_nulls = df_clean.filter(F.col("fund_ticker") == "AGG").select(
            F.col("return_1mo_pct").isNull().alias("1mo_null"),
            F.col("return_3mo_pct").isNull().alias("3mo_null"),
            F.col("return_ytd_pct").isNull().alias("ytd_null")
        ).collect()[0]

        assert agg_nulls[0] == True, "AGG return_1mo_pct should be null (outlier 9999)"
        assert agg_nulls[1] == True, "AGG return_3mo_pct should be null (outlier -500)"
        assert agg_nulls[2] == True, "AGG return_ytd_pct should be null (outlier 150)"

    def test_orphan_record_filtering(self, spark, sample_bronze_nav, sample_bronze_funds):
        """Test that orphan records are filtered."""
        # Get valid fund tickers
        valid_funds = sample_bronze_funds.filter(
            (F.col("fund_ticker").isNotNull()) &
            (F.col("fund_ticker") != "???") &
            (F.col("fund_ticker") != "N/A") &
            (F.col("fund_ticker") != "")
        ).select("fund_ticker").distinct()

        # Filter NAV
        df_clean = sample_bronze_nav.join(valid_funds, "fund_ticker", "inner")

        # Check ORPHAN1 is removed
        orphan_count = df_clean.filter(F.col("fund_ticker") == "ORPHAN1").count()
        assert orphan_count == 0, "Orphan records should be filtered"

    def test_date_parsing_in_nav(self, spark, sample_bronze_nav):
        """Test that mixed date formats in NAV are parsed."""
        df_clean = sample_bronze_nav.withColumn(
            "price_date",
            F.coalesce(
                F.to_date(F.col("price_date"), "yyyy-MM-dd"),
                F.to_date(F.col("price_date"), "MM/dd/yyyy")
            )
        )

        null_count = df_clean.filter(F.col("price_date").isNull()).count()
        assert null_count == 0, "All dates should parse successfully"


# ============================================================================
# Test Silver → Gold: Dimensions
# ============================================================================

class TestSilverToGoldDimensions:
    """Test Silver to Gold transformations for dimension tables."""

    def test_dim_fund_creation(self, spark, sample_bronze_funds, sample_bronze_market):
        """Test creation of dim_fund from joined Silver tables."""
        # Clean funds
        df_funds = sample_bronze_funds.filter(
            (F.col("fund_ticker").isNotNull()) &
            (F.col("fund_ticker") != "???") &
            (F.col("fund_ticker") != "N/A") &
            (F.col("fund_ticker") != "")
        )
        window_spec = Window.partitionBy("fund_ticker").orderBy(F.lit(1))
        df_funds = df_funds.withColumn("row_num", F.row_number().over(window_spec)) \
            .filter(F.col("row_num") == 1) \
            .drop("row_num")

        # Clean market
        df_market = sample_bronze_market.withColumnRenamed("ticker", "fund_ticker")

        # Join
        df_dim = df_funds.join(df_market, "fund_ticker", "inner").dropDuplicates(["fund_ticker"])

        result = df_dim.count()
        assert result == 6, f"dim_fund should have 6 rows, got {result}"

    def test_dim_category_creation(self, spark, sample_bronze_funds, sample_bronze_market):
        """Test creation of dim_category with surrogate keys."""
        # Clean and join
        df_funds = sample_bronze_funds.filter(F.col("fund_ticker").isNotNull())
        df_market = sample_bronze_market.withColumnRenamed("ticker", "fund_ticker")
        df_joined = df_funds.join(df_market, "fund_ticker", "inner")

        # Extract categories
        df_categories = df_joined.select(
            "category", "asset_class", "morningstar_category",
            "benchmark_index", "geographic_focus"
        ).distinct()

        # Add surrogate key
        df_dim = df_categories.withColumn("category_key", F.monotonically_increasing_id() + 1)

        result = df_dim.count()
        assert result > 0, "dim_category should have at least one row"

        # Check surrogate keys are unique
        distinct_keys = df_dim.select("category_key").distinct().count()
        assert result == distinct_keys, "All category_key values should be unique"

    def test_dim_date_creation(self, spark, sample_bronze_nav):
        """Test creation of dim_date from NAV dates."""
        # Parse dates
        df_nav = sample_bronze_nav.withColumn(
            "price_date",
            F.coalesce(
                F.to_date(F.col("price_date"), "yyyy-MM-dd"),
                F.to_date(F.col("price_date"), "MM/dd/yyyy")
            )
        )

        # Create date dimension
        df_dim = df_nav.select("price_date").distinct() \
            .withColumnRenamed("price_date", "as_of_date") \
            .withColumn("month", F.month("as_of_date")) \
            .withColumn("month_name", F.date_format("as_of_date", "MMMM")) \
            .withColumn("quarter", F.quarter("as_of_date")) \
            .withColumn("year", F.year("as_of_date")) \
            .withColumn("date_key", F.monotonically_increasing_id() + 1)

        result = df_dim.count()
        assert result > 0, "dim_date should have at least one row"

        # Check date attributes are populated
        null_month = df_dim.filter(F.col("month").isNull()).count()
        null_year = df_dim.filter(F.col("year").isNull()).count()
        assert null_month == 0, "All dates should have month"
        assert null_year == 0, "All dates should have year"


# ============================================================================
# Test Silver → Gold: Fact Table
# ============================================================================

class TestSilverToGoldFact:
    """Test Silver to Gold transformation for fact table."""

    def test_fact_table_row_count(self, spark, sample_bronze_nav, sample_bronze_funds):
        """Test that fact table has expected row count after joins."""
        # Clean NAV
        df_nav = sample_bronze_nav.withColumn(
            "price_date",
            F.coalesce(
                F.to_date(F.col("price_date"), "yyyy-MM-dd"),
                F.to_date(F.col("price_date"), "MM/dd/yyyy")
            )
        ).filter((F.col("nav") > 0) & F.col("nav").isNotNull())

        # Get valid funds
        df_funds = sample_bronze_funds.filter(
            (F.col("fund_ticker").isNotNull()) &
            (F.col("fund_ticker") != "???") &
            (F.col("fund_ticker") != "N/A") &
            (F.col("fund_ticker") != "")
        ).select("fund_ticker").distinct()

        # Join to filter orphans
        df_fact = df_nav.join(df_funds, "fund_ticker", "inner")

        result = df_fact.count()
        # Should have valid NAV records (excluding BND -10, QQQ 0, AGG, ORPHAN1)
        assert result >= 4, f"Fact table should have at least 4 rows, got {result}"

    def test_fact_table_measures(self, spark, sample_bronze_nav):
        """Test that fact table contains all required measures."""
        df_nav = sample_bronze_nav.filter(F.col("nav") > 0)

        required_measures = ["nav", "total_assets_millions", "return_1mo_pct",
                            "return_3mo_pct", "return_ytd_pct", "return_1yr_pct"]

        for measure in required_measures:
            assert measure in df_nav.columns, f"Measure {measure} should be in fact table"


# ============================================================================
# Test Data Quality Improvements
# ============================================================================

class TestDataQualityImprovements:
    """Test that data quality improves through the pipeline."""

    def test_completeness_improvement(self, spark, sample_bronze_funds):
        """Test that completeness improves from Bronze to Silver."""
        # Bronze completeness
        bronze_null_count = sample_bronze_funds.filter(F.col("fund_name").isNull()).count()

        # Silver completeness (after filling nulls)
        df_silver = sample_bronze_funds.withColumn(
            "fund_name",
            F.when(F.col("fund_name").isNull(), "Unknown Fund").otherwise(F.col("fund_name"))
        )
        silver_null_count = df_silver.filter(F.col("fund_name").isNull()).count()

        assert silver_null_count < bronze_null_count, "Null count should decrease in Silver"

    def test_validity_improvement(self, spark, sample_bronze_market):
        """Test that validity improves from Bronze to Silver."""
        # Bronze invalid ratings
        bronze_invalid = sample_bronze_market.filter(
            (F.col("morningstar_rating") < 1) | (F.col("morningstar_rating") > 5)
        ).count()

        # Silver invalid ratings (should be nullified)
        df_silver = sample_bronze_market.withColumn(
            "morningstar_rating",
            F.when(
                (F.col("morningstar_rating") >= 1) & (F.col("morningstar_rating") <= 5),
                F.col("morningstar_rating")
            ).otherwise(None)
        )
        silver_invalid = df_silver.filter(
            (F.col("morningstar_rating") < 1) | (F.col("morningstar_rating") > 5)
        ).count()

        assert silver_invalid == 0, "No invalid ratings should exist in Silver"
        assert bronze_invalid > 0, "Bronze should have had invalid ratings"

    def test_uniqueness_improvement(self, spark, sample_bronze_funds):
        """Test that uniqueness improves from Bronze to Silver."""
        # Bronze duplicates
        bronze_count = sample_bronze_funds.count()
        bronze_distinct = sample_bronze_funds.select("fund_ticker").distinct().count()

        # Silver after deduplication
        window_spec = Window.partitionBy("fund_ticker").orderBy(F.lit(1))
        df_silver = sample_bronze_funds.withColumn("row_num", F.row_number().over(window_spec)) \
            .filter(F.col("row_num") == 1) \
            .drop("row_num")
        silver_count = df_silver.count()
        silver_distinct = df_silver.select("fund_ticker").distinct().count()

        assert silver_count == silver_distinct, "Silver should have no duplicates"
        assert bronze_count > bronze_distinct, "Bronze should have had duplicates"


# ============================================================================
# Test Iceberg Table Properties
# ============================================================================

class TestIcebergTableProperties:
    """Test Iceberg-specific properties and capabilities."""

    def test_iceberg_format_version(self, spark):
        """Test that Iceberg tables use format version 2."""
        # This is a placeholder - actual Iceberg table testing requires Iceberg catalog
        # In integration environment, you would verify table properties
        assert True, "Iceberg format version check placeholder"

    def test_partitioning(self, spark, sample_bronze_nav):
        """Test that partitioning columns are present."""
        df_nav = sample_bronze_nav.withColumn(
            "price_date",
            F.coalesce(
                F.to_date(F.col("price_date"), "yyyy-MM-dd"),
                F.to_date(F.col("price_date"), "MM/dd/yyyy")
            )
        )

        # Add year for partitioning
        df_nav = df_nav.withColumn("year", F.year("price_date"))

        # Check year column exists
        assert "year" in df_nav.columns, "Year column should exist for partitioning"

        # Check year values are valid
        null_year_count = df_nav.filter(F.col("year").isNull()).count()
        assert null_year_count == 0, "All rows should have valid year for partitioning"
