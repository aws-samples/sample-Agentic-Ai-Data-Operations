"""
Silver Quality Checks - US Mutual Funds & ETF Dataset
Validates Silver zone data against quality rules.

JOB 5: Depends on JOB 2, 3, 4 (all Silver clean jobs)
Input: glue_catalog.finsights_silver.* (all Silver tables)
Output: Quality metrics logged, exit 1 if quality gate fails
"""

from awsglue.context import GlueContext
from pyspark.context import SparkContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.sql import functions as F
import sys
import json
from datetime import datetime

# Initialize Glue context
args = getResolvedOptions(sys.argv, ["JOB_NAME"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)
logger = glueContext.get_logger()

logger.info("=== SILVER ZONE QUALITY CHECKS ===")


# ============================================================================
# Quality Check Functions
# ============================================================================

def check_completeness(df, column, threshold, severity):
    """Check NOT NULL completeness"""
    total = df.count()
    if total == 0:
        return {"column": column, "dimension": "completeness", "score": 1.0, "passed": True, "severity": severity}
    non_null = df.filter(F.col(column).isNotNull()).count()
    score = non_null / total
    passed = score >= threshold
    logger.info(f"Completeness {column}: {score:.3f} >= {threshold} → {'PASS' if passed else 'FAIL'} ({severity})")
    return {"column": column, "dimension": "completeness", "score": score, "passed": passed, "severity": severity}


def check_validity(df, column, valid_values, threshold, severity):
    """Check IN clause validity"""
    total = df.count()
    if total == 0:
        return {"column": column, "dimension": "validity", "score": 1.0, "passed": True, "severity": severity}
    valid = df.filter(F.col(column).isin(valid_values)).count()
    score = valid / total
    passed = score >= threshold
    logger.info(f"Validity {column} IN {valid_values}: {score:.3f} >= {threshold} → {'PASS' if passed else 'FAIL'} ({severity})")
    return {"column": column, "dimension": "validity", "score": score, "passed": passed, "severity": severity}


def check_uniqueness(df, column, threshold, severity):
    """Check DISTINCT uniqueness"""
    total = df.count()
    if total == 0:
        return {"column": column, "dimension": "uniqueness", "score": 1.0, "passed": True, "severity": severity}
    distinct = df.select(column).distinct().count()
    score = distinct / total
    passed = score >= threshold
    logger.info(f"Uniqueness {column}: {score:.3f} >= {threshold} → {'PASS' if passed else 'FAIL'} ({severity})")
    return {"column": column, "dimension": "uniqueness", "score": score, "passed": passed, "severity": severity}


def check_accuracy_range(df, column, min_val, max_val, threshold, severity):
    """Check BETWEEN range accuracy"""
    total = df.filter(F.col(column).isNotNull()).count()
    if total == 0:
        return {"column": column, "dimension": "accuracy", "score": 1.0, "passed": True, "severity": severity}
    in_range = df.filter((F.col(column) >= min_val) & (F.col(column) <= max_val)).count()
    score = in_range / total
    passed = score >= threshold
    logger.info(f"Accuracy {column} BETWEEN {min_val} AND {max_val}: {score:.3f} >= {threshold} → {'PASS' if passed else 'FAIL'} ({severity})")
    return {"column": column, "dimension": "accuracy", "score": score, "passed": passed, "severity": severity}


def check_accuracy_greater_than(df, column, min_val, threshold, severity):
    """Check GREATER THAN accuracy"""
    total = df.filter(F.col(column).isNotNull()).count()
    if total == 0:
        return {"column": column, "dimension": "accuracy", "score": 1.0, "passed": True, "severity": severity}
    valid = df.filter(F.col(column) > min_val).count()
    score = valid / total
    passed = score >= threshold
    logger.info(f"Accuracy {column} > {min_val}: {score:.3f} >= {threshold} → {'PASS' if passed else 'FAIL'} ({severity})")
    return {"column": column, "dimension": "accuracy", "score": score, "passed": passed, "severity": severity}


def check_referential_integrity(child_df, child_col, parent_df, parent_col, threshold, severity):
    """Check foreign key integrity"""
    total = child_df.count()
    if total == 0:
        return {"dimension": "referential_integrity", "score": 1.0, "passed": True, "severity": severity}
    orphans = child_df.join(parent_df, child_df[child_col] == parent_df[parent_col], "left_anti").count()
    score = (total - orphans) / total
    passed = score >= threshold
    logger.info(f"Referential Integrity {child_col} → {parent_col}: {score:.3f} >= {threshold} → {'PASS' if passed else 'FAIL'} ({severity})")
    return {"dimension": "referential_integrity", "score": score, "passed": passed, "severity": severity}


def check_consistency(df, condition_expr, threshold, severity, description):
    """Check logical consistency rule"""
    total = df.count()
    if total == 0:
        return {"dimension": "consistency", "score": 1.0, "passed": True, "severity": severity, "description": description}
    valid = df.filter(condition_expr).count()
    score = valid / total
    passed = score >= threshold
    logger.info(f"Consistency '{description}': {score:.3f} >= {threshold} → {'PASS' if passed else 'FAIL'} ({severity})")
    return {"dimension": "consistency", "score": score, "passed": passed, "severity": severity, "description": description}


# ============================================================================
# Load Silver Tables
# ============================================================================

logger.info("Loading Silver tables...")

df_funds = spark.table("glue_catalog.finsights_silver.funds_clean")
df_market = spark.table("glue_catalog.finsights_silver.market_data_clean")
df_nav = spark.table("glue_catalog.finsights_silver.nav_clean")

logger.info(f"  - funds_clean: {df_funds.count()} rows")
logger.info(f"  - market_data_clean: {df_market.count()} rows")
logger.info(f"  - nav_clean: {df_nav.count()} rows")

results = []

# ============================================================================
# Table 1: finsights_silver.funds_clean
# ============================================================================

logger.info("\n=== Checking finsights_silver.funds_clean ===")

# Completeness
results.append(check_completeness(df_funds, "fund_ticker", 1.0, "critical"))
results.append(check_completeness(df_funds, "fund_name", 0.95, "warning"))
results.append(check_completeness(df_funds, "fund_type", 1.0, "critical"))

# Validity
results.append(check_validity(df_funds, "fund_type", ["ETF", "Mutual Fund"], 1.0, "critical"))

# Uniqueness
results.append(check_uniqueness(df_funds, "fund_ticker", 1.0, "critical"))

# Inception date validity
logger.info("Checking inception_date validity (1985-01-01 to CURRENT_DATE)...")
total_dates = df_funds.filter(F.col("inception_date").isNotNull()).count()
if total_dates > 0:
    valid_dates = df_funds.filter(
        (F.col("inception_date") >= F.lit("1985-01-01")) &
        (F.col("inception_date") <= F.current_date())
    ).count()
    score = valid_dates / total_dates
    passed = score >= 0.98
    logger.info(f"Validity inception_date BETWEEN 1985-01-01 AND CURRENT_DATE: {score:.3f} >= 0.98 → {'PASS' if passed else 'FAIL'} (warning)")
    results.append({"column": "inception_date", "dimension": "validity", "score": score, "passed": passed, "severity": "warning"})
else:
    results.append({"column": "inception_date", "dimension": "validity", "score": 1.0, "passed": True, "severity": "warning"})

# ============================================================================
# Table 2: finsights_silver.market_data_clean
# ============================================================================

logger.info("\n=== Checking finsights_silver.market_data_clean ===")

# Completeness
results.append(check_completeness(df_market, "fund_ticker", 1.0, "critical"))
results.append(check_completeness(df_market, "expense_ratio_pct", 0.90, "warning"))

# Accuracy
results.append(check_accuracy_range(df_market, "expense_ratio_pct", 0.0, 3.0, 1.0, "critical"))
results.append(check_accuracy_range(df_market, "beta", 0.0, 3.0, 0.95, "warning"))
results.append(check_accuracy_range(df_market, "sharpe_ratio", -2.0, 5.0, 0.95, "warning"))
results.append(check_accuracy_range(df_market, "morningstar_rating", 1, 5, 1.0, "critical"))

# Validity
results.append(check_accuracy_range(df_market, "dividend_yield_pct", 0.0, 15.0, 0.98, "warning"))

# ============================================================================
# Table 3: finsights_silver.nav_clean
# ============================================================================

logger.info("\n=== Checking finsights_silver.nav_clean ===")

# Completeness
results.append(check_completeness(df_nav, "fund_ticker", 1.0, "critical"))
results.append(check_completeness(df_nav, "price_date", 1.0, "critical"))
results.append(check_completeness(df_nav, "nav", 1.0, "critical"))

# Accuracy
results.append(check_accuracy_greater_than(df_nav, "nav", 0, 1.0, "critical"))
results.append(check_accuracy_range(df_nav, "return_1yr_pct", -50, 100, 1.0, "warning"))
results.append(check_accuracy_range(df_nav, "return_5yr_pct", -50, 100, 1.0, "warning"))

# Consistency (If 5Y return exists, 1Y return should too)
consistency_condition = (F.col("return_5yr_pct").isNull()) | (F.col("return_1yr_pct").isNotNull())
results.append(check_consistency(df_nav, consistency_condition, 0.90, "warning", "If 5Y return exists, 1Y return should too"))

# Referential Integrity
results.append(check_referential_integrity(df_nav, "fund_ticker", df_funds, "fund_ticker", 1.0, "critical"))

# ============================================================================
# Calculate Overall Score and Determine Pass/Fail
# ============================================================================

logger.info("\n=== SILVER QUALITY SUMMARY ===")

total_checks = len(results)
passed_checks = sum(1 for r in results if r["passed"])
failed_checks = total_checks - passed_checks
overall_score = passed_checks / total_checks if total_checks > 0 else 0

# Count critical failures
critical_failures = sum(1 for r in results if not r["passed"] and r["severity"] == "critical")

logger.info(f"Total checks: {total_checks}")
logger.info(f"Passed: {passed_checks}")
logger.info(f"Failed: {failed_checks}")
logger.info(f"Overall score: {overall_score:.3f}")
logger.info(f"Critical failures: {critical_failures}")

# Write quality metrics to S3 for audit
quality_report = {
    "workload": "us_mutual_funds_etf",
    "zone": "silver",
    "timestamp": datetime.now().isoformat(),
    "overall_score": overall_score,
    "total_checks": total_checks,
    "passed_checks": passed_checks,
    "failed_checks": failed_checks,
    "critical_failures": critical_failures,
    "threshold": 0.80,
    "results": results
}

report_json = json.dumps(quality_report, indent=2)
logger.info(f"\nQuality Report:\n{report_json}")

# Write to S3 (if running on Glue)
try:
    report_path = f"s3://your-datalake-bucket/quality_reports/silver/{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    spark.createDataFrame([(report_json,)], ["report"]).write.mode("overwrite").text(report_path)
    logger.info(f"Quality report written to {report_path}")
except Exception as e:
    logger.warning(f"Could not write quality report to S3: {e}")

# ============================================================================
# Block promotion if quality gate fails
# ============================================================================

if overall_score < 0.80:
    logger.error(f"❌ QUALITY GATE FAILED: Score {overall_score:.3f} < 0.80")
    job.commit()
    sys.exit(1)

if critical_failures > 0:
    logger.error(f"❌ QUALITY GATE FAILED: {critical_failures} critical failures detected")
    job.commit()
    sys.exit(1)

logger.info("✅ SILVER QUALITY GATE PASSED")
job.commit()
