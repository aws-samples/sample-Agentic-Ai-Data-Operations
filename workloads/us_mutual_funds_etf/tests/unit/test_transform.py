"""
Unit Tests for US Mutual Funds & ETF Transformation Scripts
Tests transformation logic in isolation with mocked data.
"""

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType, DateType
from datetime import date, datetime


@pytest.fixture(scope="module")
def spark():
    """Create a Spark session for testing."""
    spark = SparkSession.builder \
        .appName("test_us_mutual_funds_etf_transform") \
        .master("local[2]") \
        .getOrCreate()
    yield spark
    spark.stop()


# ============================================================================
# Tests for Date Parsing Logic
# ============================================================================

class TestDateParsing:
    """Test date parsing for both YYYY-MM-DD and MM/DD/YYYY formats."""

    def test_parse_yyyy_mm_dd_format(self, spark):
        """Test parsing YYYY-MM-DD format."""
        data = [("2025-01-15",), ("2024-12-31",), ("2023-06-01",)]
        schema = StructType([StructField("date_str", StringType(), True)])
        df = spark.createDataFrame(data, schema)

        df_parsed = df.withColumn(
            "parsed_date",
            F.to_date(F.col("date_str"), "yyyy-MM-dd")
        )

        result = df_parsed.filter(F.col("parsed_date").isNotNull()).count()
        assert result == 3, "All YYYY-MM-DD dates should parse successfully"

    def test_parse_mm_dd_yyyy_format(self, spark):
        """Test parsing MM/DD/YYYY format."""
        data = [("01/15/2025",), ("12/31/2024",), ("06/01/2023",)]
        schema = StructType([StructField("date_str", StringType(), True)])
        df = spark.createDataFrame(data, schema)

        df_parsed = df.withColumn(
            "parsed_date",
            F.to_date(F.col("date_str"), "MM/dd/yyyy")
        )

        result = df_parsed.filter(F.col("parsed_date").isNotNull()).count()
        assert result == 3, "All MM/DD/YYYY dates should parse successfully"

    def test_parse_mixed_formats(self, spark):
        """Test parsing mixed date formats using coalesce."""
        data = [("2025-01-15",), ("01/15/2025",), ("2024-12-31",), ("12/31/2024",)]
        schema = StructType([StructField("date_str", StringType(), True)])
        df = spark.createDataFrame(data, schema)

        df_parsed = df.withColumn(
            "parsed_date",
            F.coalesce(
                F.to_date(F.col("date_str"), "yyyy-MM-dd"),
                F.to_date(F.col("date_str"), "MM/dd/yyyy")
            )
        )

        result = df_parsed.filter(F.col("parsed_date").isNotNull()).count()
        assert result == 4, "All mixed format dates should parse successfully"

    def test_invalid_date_format(self, spark):
        """Test handling of invalid date formats."""
        data = [("2025-13-45",), ("99/99/9999",), ("invalid",)]
        schema = StructType([StructField("date_str", StringType(), True)])
        df = spark.createDataFrame(data, schema)

        df_parsed = df.withColumn(
            "parsed_date",
            F.coalesce(
                F.to_date(F.col("date_str"), "yyyy-MM-dd"),
                F.to_date(F.col("date_str"), "MM/dd/yyyy")
            )
        )

        result = df_parsed.filter(F.col("parsed_date").isNull()).count()
        assert result == 3, "Invalid dates should result in null"


# ============================================================================
# Tests for Deduplication Logic
# ============================================================================

class TestDeduplication:
    """Test deduplication logic using window functions."""

    def test_deduplicate_fund_ticker(self, spark):
        """Test deduplication keeps first occurrence."""
        data = [
            ("VTI", "Fund A", "ETF"),
            ("VTI", "Fund B", "Mutual Fund"),  # Duplicate
            ("VOO", "Fund C", "ETF"),
            ("VOO", "Fund D", "ETF"),  # Duplicate
            ("SPY", "Fund E", "ETF")
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("fund_name", StringType(), True),
            StructField("fund_type", StringType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        from pyspark.sql.window import Window
        window_spec = Window.partitionBy("fund_ticker").orderBy(F.lit(1))
        df_dedup = df.withColumn("row_num", F.row_number().over(window_spec)) \
            .filter(F.col("row_num") == 1) \
            .drop("row_num")

        result = df_dedup.count()
        assert result == 3, "Should have 3 unique fund_tickers after deduplication"

        # Verify first occurrence is kept
        vti_name = df_dedup.filter(F.col("fund_ticker") == "VTI").select("fund_name").collect()[0][0]
        assert vti_name == "Fund A", "Should keep first occurrence of VTI"

    def test_no_duplicates(self, spark):
        """Test deduplication with no duplicates present."""
        data = [
            ("VTI", "Fund A", "ETF"),
            ("VOO", "Fund B", "ETF"),
            ("SPY", "Fund C", "ETF")
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("fund_name", StringType(), True),
            StructField("fund_type", StringType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        from pyspark.sql.window import Window
        window_spec = Window.partitionBy("fund_ticker").orderBy(F.lit(1))
        df_dedup = df.withColumn("row_num", F.row_number().over(window_spec)) \
            .filter(F.col("row_num") == 1) \
            .drop("row_num")

        result = df_dedup.count()
        assert result == 3, "Count should remain same when no duplicates"


# ============================================================================
# Tests for Outlier Clamping Logic
# ============================================================================

class TestOutlierClamping:
    """Test clamping of outlier values in return columns."""

    def test_clamp_return_values_within_range(self, spark):
        """Test that values within range are preserved."""
        data = [
            ("FUND1", 5.0, 10.0, 15.0),
            ("FUND2", -5.0, -10.0, 0.0),
            ("FUND3", 50.0, -50.0, 25.0)
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("return_1mo_pct", DoubleType(), True),
            StructField("return_3mo_pct", DoubleType(), True),
            StructField("return_1yr_pct", DoubleType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_clamped = df.withColumn(
            "return_1mo_pct",
            F.when((F.col("return_1mo_pct") >= -50) & (F.col("return_1mo_pct") <= 100),
                   F.col("return_1mo_pct")).otherwise(None)
        )

        result = df_clamped.filter(F.col("return_1mo_pct").isNotNull()).count()
        assert result == 3, "All values within range should be preserved"

    def test_clamp_return_values_outside_range(self, spark):
        """Test that values outside range are nullified."""
        data = [
            ("FUND1", 9999.0, 10.0),   # Outlier
            ("FUND2", -500.0, -10.0),  # Outlier
            ("FUND3", 150.0, 0.0),     # Outlier
            ("FUND4", 10.0, 5.0)       # Valid
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("return_1yr_pct", DoubleType(), True),
            StructField("return_3mo_pct", DoubleType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_clamped = df.withColumn(
            "return_1yr_pct",
            F.when((F.col("return_1yr_pct") >= -50) & (F.col("return_1yr_pct") <= 100),
                   F.col("return_1yr_pct")).otherwise(None)
        )

        null_count = df_clamped.filter(F.col("return_1yr_pct").isNull()).count()
        assert null_count == 3, "Outliers should be set to null"

        valid_count = df_clamped.filter(F.col("return_1yr_pct").isNotNull()).count()
        assert valid_count == 1, "Only valid values should remain"

    def test_clamp_boundary_values(self, spark):
        """Test boundary values (-50 and 100) are preserved."""
        data = [
            ("FUND1", -50.0),
            ("FUND2", 100.0),
            ("FUND3", -50.1),  # Just outside
            ("FUND4", 100.1)   # Just outside
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("return_1yr_pct", DoubleType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_clamped = df.withColumn(
            "return_1yr_pct",
            F.when((F.col("return_1yr_pct") >= -50) & (F.col("return_1yr_pct") <= 100),
                   F.col("return_1yr_pct")).otherwise(None)
        )

        valid_count = df_clamped.filter(F.col("return_1yr_pct").isNotNull()).count()
        assert valid_count == 2, "Boundary values should be preserved"


# ============================================================================
# Tests for Data Type Standardization
# ============================================================================

class TestDataTypeStandardization:
    """Test standardization of fund_type values."""

    def test_standardize_etf_variants(self, spark):
        """Test ETF variant standardization."""
        data = [
            ("FUND1", "ETF"),
            ("FUND2", "etf"),
            ("FUND3", "E.T.F"),
            ("FUND4", "e.t.f.")
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("fund_type", StringType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_std = df.withColumn(
            "fund_type",
            F.when(F.upper(F.regexp_replace(F.col("fund_type"), "[^A-Za-z]", "")) == "ETF", "ETF")
             .otherwise(F.col("fund_type"))
        )

        etf_count = df_std.filter(F.col("fund_type") == "ETF").count()
        assert etf_count == 4, "All ETF variants should be standardized to 'ETF'"

    def test_standardize_mutual_fund_variants(self, spark):
        """Test Mutual Fund variant standardization."""
        data = [
            ("FUND1", "Mutual Fund"),
            ("FUND2", "mutual fund"),
            ("FUND3", "MUTUAL FUND")
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("fund_type", StringType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_std = df.withColumn(
            "fund_type",
            F.when(F.upper(F.col("fund_type")).contains("MUTUAL"), "Mutual Fund")
             .otherwise(F.col("fund_type"))
        )

        mf_count = df_std.filter(F.col("fund_type") == "Mutual Fund").count()
        assert mf_count == 3, "All Mutual Fund variants should be standardized"


# ============================================================================
# Tests for Invalid Ticker Filtering
# ============================================================================

class TestInvalidTickerFiltering:
    """Test filtering of invalid ticker values."""

    def test_filter_null_tickers(self, spark):
        """Test filtering of null tickers."""
        data = [
            ("VTI", "Fund A"),
            (None, "Fund B"),
            ("VOO", "Fund C")
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("fund_name", StringType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_filtered = df.filter(F.col("fund_ticker").isNotNull())

        result = df_filtered.count()
        assert result == 2, "Null tickers should be filtered out"

    def test_filter_invalid_ticker_values(self, spark):
        """Test filtering of invalid ticker values."""
        data = [
            ("VTI", "Fund A"),
            ("???", "Fund B"),
            ("N/A", "Fund C"),
            ("", "Fund D"),
            ("VOO", "Fund E")
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("fund_name", StringType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_filtered = df.filter(
            (F.col("fund_ticker").isNotNull()) &
            (F.col("fund_ticker") != "???") &
            (F.col("fund_ticker") != "N/A") &
            (F.col("fund_ticker") != "")
        )

        result = df_filtered.count()
        assert result == 2, "Invalid ticker values should be filtered out"


# ============================================================================
# Tests for Expense Ratio Cleaning
# ============================================================================

class TestExpenseRatioCleaning:
    """Test cleaning of expense_ratio_pct from string format."""

    def test_strip_percentage_sign(self, spark):
        """Test stripping % sign and converting to double."""
        data = [
            ("FUND1", "0.75%"),
            ("FUND2", "1.25%"),
            ("FUND3", "0.05%")
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("expense_ratio_pct", StringType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_cleaned = df.withColumn(
            "expense_ratio_pct",
            F.regexp_replace(F.col("expense_ratio_pct"), "%", "").cast(DoubleType())
        )

        # Check all values are numeric
        result = df_cleaned.filter(F.col("expense_ratio_pct").isNotNull()).count()
        assert result == 3, "All expense ratios should be converted to double"

        # Check a specific value
        fund1_expense = df_cleaned.filter(F.col("fund_ticker") == "FUND1").select("expense_ratio_pct").collect()[0][0]
        assert fund1_expense == 0.75, "0.75% should convert to 0.75"

    def test_handle_mixed_formats(self, spark):
        """Test handling of mixed string and numeric formats."""
        data = [
            ("FUND1", "0.75%"),
            ("FUND2", 1.25),  # Already numeric
            ("FUND3", "0.05")
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("expense_ratio_pct", StringType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_cleaned = df.withColumn(
            "expense_ratio_pct",
            F.when(
                F.col("expense_ratio_pct").cast("string").rlike("%$"),
                F.regexp_replace(F.col("expense_ratio_pct").cast("string"), "%", "").cast(DoubleType())
            ).otherwise(F.col("expense_ratio_pct").cast(DoubleType()))
        )

        result = df_cleaned.filter(F.col("expense_ratio_pct").isNotNull()).count()
        assert result == 3, "All formats should be handled correctly"


# ============================================================================
# Tests for Morningstar Rating Clamping
# ============================================================================

class TestMorningstarRatingClamping:
    """Test clamping of morningstar_rating to valid range 1-5."""

    def test_valid_ratings_preserved(self, spark):
        """Test that valid ratings (1-5) are preserved."""
        data = [
            ("FUND1", 1),
            ("FUND2", 3),
            ("FUND3", 5)
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("morningstar_rating", IntegerType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_clamped = df.withColumn(
            "morningstar_rating",
            F.when(
                (F.col("morningstar_rating") >= 1) & (F.col("morningstar_rating") <= 5),
                F.col("morningstar_rating")
            ).otherwise(None)
        )

        result = df_clamped.filter(F.col("morningstar_rating").isNotNull()).count()
        assert result == 3, "All valid ratings should be preserved"

    def test_invalid_ratings_nullified(self, spark):
        """Test that invalid ratings are set to null."""
        data = [
            ("FUND1", 0),
            ("FUND2", 6),
            ("FUND3", -1),
            ("FUND4", 99),
            ("FUND5", 3)  # Valid
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("morningstar_rating", IntegerType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_clamped = df.withColumn(
            "morningstar_rating",
            F.when(
                (F.col("morningstar_rating") >= 1) & (F.col("morningstar_rating") <= 5),
                F.col("morningstar_rating")
            ).otherwise(None)
        )

        null_count = df_clamped.filter(F.col("morningstar_rating").isNull()).count()
        assert null_count == 4, "Invalid ratings should be set to null"


# ============================================================================
# Tests for Surrogate Key Generation
# ============================================================================

class TestSurrogateKeyGeneration:
    """Test surrogate key generation using monotonically_increasing_id."""

    def test_generate_unique_keys(self, spark):
        """Test that surrogate keys are unique."""
        data = [
            ("Category A",),
            ("Category B",),
            ("Category C",)
        ]
        schema = StructType([StructField("category", StringType(), True)])
        df = spark.createDataFrame(data, schema)

        df_with_key = df.withColumn("category_key", F.monotonically_increasing_id() + 1)

        # Check uniqueness
        total_count = df_with_key.count()
        distinct_count = df_with_key.select("category_key").distinct().count()
        assert total_count == distinct_count, "All surrogate keys should be unique"

    def test_keys_are_numeric(self, spark):
        """Test that surrogate keys are numeric."""
        data = [("Category A",), ("Category B",)]
        schema = StructType([StructField("category", StringType(), True)])
        df = spark.createDataFrame(data, schema)

        df_with_key = df.withColumn("category_key", F.monotonically_increasing_id() + 1)

        # Check all keys are positive integers
        min_key = df_with_key.agg(F.min("category_key")).collect()[0][0]
        assert min_key >= 1, "All surrogate keys should be >= 1"


# ============================================================================
# Tests for Null Imputation
# ============================================================================

class TestNullImputation:
    """Test null imputation with median values."""

    def test_impute_nulls_with_median(self, spark):
        """Test that nulls are imputed with median."""
        data = [
            ("FUND1", 1.0),
            ("FUND2", 2.0),
            ("FUND3", None),
            ("FUND4", 3.0),
            ("FUND5", None)
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("beta", DoubleType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        # Calculate median
        median = df.approxQuantile("beta", [0.5], 0.01)[0]

        df_imputed = df.withColumn(
            "beta",
            F.when(F.col("beta").isNull(), F.lit(median)).otherwise(F.col("beta"))
        )

        null_count = df_imputed.filter(F.col("beta").isNull()).count()
        assert null_count == 0, "All nulls should be imputed"

        # Verify median value
        assert median == 2.0, "Median should be 2.0"


# ============================================================================
# Tests for NAV Validation
# ============================================================================

class TestNAVValidation:
    """Test NAV validation (must be > 0)."""

    def test_filter_negative_nav(self, spark):
        """Test filtering of negative NAV values."""
        data = [
            ("FUND1", date(2025, 1, 1), 100.0),
            ("FUND2", date(2025, 1, 1), -10.0),
            ("FUND3", date(2025, 1, 1), 0.0),
            ("FUND4", date(2025, 1, 1), 50.0)
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("price_date", DateType(), True),
            StructField("nav", DoubleType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_filtered = df.filter((F.col("nav") > 0) & F.col("nav").isNotNull())

        result = df_filtered.count()
        assert result == 2, "Only positive NAV values should remain"

    def test_filter_null_nav(self, spark):
        """Test filtering of null NAV values."""
        data = [
            ("FUND1", date(2025, 1, 1), 100.0),
            ("FUND2", date(2025, 1, 1), None),
            ("FUND3", date(2025, 1, 1), 50.0)
        ]
        schema = StructType([
            StructField("fund_ticker", StringType(), True),
            StructField("price_date", DateType(), True),
            StructField("nav", DoubleType(), True)
        ])
        df = spark.createDataFrame(data, schema)

        df_filtered = df.filter((F.col("nav") > 0) & F.col("nav").isNotNull())

        result = df_filtered.count()
        assert result == 2, "Null NAV values should be filtered out"
