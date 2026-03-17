"""
Gold Quality Checks - US Mutual Funds & ETF Dataset
Validates Gold zone data against quality rules.

JOB 9: Depends on JOB 6, 7, 8 (all Gold dim/fact jobs)
Input: glue_catalog.finsights_gold.* (all Gold tables)
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

logger.info("=== GOLD ZONE QUALITY CHECKS ===")


# ============================================================================
# Quality Check Functions (reused from Silver)
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
    # Handle nullable foreign keys
    child_non_null = child_df.filter(F.col(child_col).isNotNull())
    total_non_null = child_non_null.count()
    if total_non_null == 0:
        return {"dimension": "referential_integrity", "score": 1.0, "passed": True, "severity": severity}
    orphans = child_non_null.join(parent_df, child_non_null[child_col] == parent_df[parent_col], "left_anti").count()
    score = (total_non_null - orphans) / total_non_null
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
# Load Gold Tables
# ============================================================================

logger.info("Loading Gold tables...")

df_dim_fund = spark.table("glue_catalog.finsights_gold.dim_fund")
df_dim_category = spark.table("glue_catalog.finsights_gold.dim_category")
df_dim_date = spark.table("glue_catalog.finsights_gold.dim_date")
df_fact = spark.table("glue_catalog.finsights_gold.fact_fund_performance")

logger.info(f"  - dim_fund: {df_dim_fund.count()} rows")
logger.info(f"  - dim_category: {df_dim_category.count()} rows")
logger.info(f"  - dim_date: {df_dim_date.count()} rows")
logger.info(f"  - fact_fund_performance: {df_fact.count()} rows")

results = []

# ============================================================================
# Table 1: finsights_gold.dim_fund
# ============================================================================

logger.info("\n=== Checking finsights_gold.dim_fund ===")

# Completeness
results.append(check_completeness(df_dim_fund, "fund_ticker", 1.0, "critical"))
results.append(check_completeness(df_dim_fund, "fund_name", 1.0, "critical"))
results.append(check_completeness(df_dim_fund, "asset_class", 1.0, "critical"))

# Uniqueness
results.append(check_uniqueness(df_dim_fund, "fund_ticker", 1.0, "critical"))

# ============================================================================
# Table 2: finsights_gold.dim_category
# ============================================================================

logger.info("\n=== Checking finsights_gold.dim_category ===")

# Completeness
results.append(check_completeness(df_dim_category, "category_key", 1.0, "critical"))
results.append(check_completeness(df_dim_category, "fund_category", 1.0, "critical"))

# Uniqueness
results.append(check_uniqueness(df_dim_category, "category_key", 1.0, "critical"))

# Accuracy (min <= max expense)
logger.info("Checking typical_expense_min <= typical_expense_max...")
valid_expense = df_dim_category.filter(
    (F.col("typical_expense_min").isNull()) |
    (F.col("typical_expense_max").isNull()) |
    (F.col("typical_expense_min") <= F.col("typical_expense_max"))
).count()
total_cat = df_dim_category.count()
score = valid_expense / total_cat if total_cat > 0 else 1.0
passed = score >= 1.0
logger.info(f"Accuracy typical_expense_min <= typical_expense_max: {score:.3f} >= 1.0 → {'PASS' if passed else 'FAIL'} (critical)")
results.append({"dimension": "accuracy", "score": score, "passed": passed, "severity": "critical", "description": "Min expense must not exceed max"})

# ============================================================================
# Table 3: finsights_gold.dim_date
# ============================================================================

logger.info("\n=== Checking finsights_gold.dim_date ===")

# Completeness
results.append(check_completeness(df_dim_date, "date_key", 1.0, "critical"))
results.append(check_completeness(df_dim_date, "as_of_date", 1.0, "critical"))

# Uniqueness
results.append(check_uniqueness(df_dim_date, "date_key", 1.0, "critical"))
results.append(check_uniqueness(df_dim_date, "as_of_date", 1.0, "critical"))

# Validity
results.append(check_accuracy_range(df_dim_date, "month", 1, 12, 1.0, "critical"))
results.append(check_accuracy_range(df_dim_date, "quarter", 1, 4, 1.0, "critical"))

# ============================================================================
# Table 4: finsights_gold.fact_fund_performance
# ============================================================================

logger.info("\n=== Checking finsights_gold.fact_fund_performance ===")

# Completeness
results.append(check_completeness(df_fact, "fact_id", 1.0, "critical"))
results.append(check_completeness(df_fact, "fund_ticker", 1.0, "critical"))
results.append(check_completeness(df_fact, "date_key", 1.0, "critical"))

# Uniqueness
results.append(check_uniqueness(df_fact, "fact_id", 1.0, "critical"))

# Referential Integrity
results.append(check_referential_integrity(df_fact, "fund_ticker", df_dim_fund, "fund_ticker", 1.0, "critical"))
results.append(check_referential_integrity(df_fact, "category_key", df_dim_category, "category_key", 0.95, "warning"))
results.append(check_referential_integrity(df_fact, "date_key", df_dim_date, "date_key", 1.0, "critical"))

# Accuracy
results.append(check_accuracy_greater_than(df_fact, "nav", 0, 1.0, "critical"))
results.append(check_accuracy_greater_than(df_fact, "total_assets_millions", 0, 0.95, "warning"))
results.append(check_accuracy_range(df_fact, "expense_ratio_pct", 0.0, 3.0, 0.95, "warning"))

# ============================================================================
# Calculate Overall Score and Determine Pass/Fail
# ============================================================================

logger.info("\n=== GOLD QUALITY SUMMARY ===")

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
    "zone": "gold",
    "timestamp": datetime.now().isoformat(),
    "overall_score": overall_score,
    "total_checks": total_checks,
    "passed_checks": passed_checks,
    "failed_checks": failed_checks,
    "critical_failures": critical_failures,
    "threshold": 0.95,
    "results": results
}

report_json = json.dumps(quality_report, indent=2)
logger.info(f"\nQuality Report:\n{report_json}")

# Write to S3 (if running on Glue)
try:
    report_path = f"s3://your-datalake-bucket/quality_reports/gold/{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    spark.createDataFrame([(report_json,)], ["report"]).write.mode("overwrite").text(report_path)
    logger.info(f"Quality report written to {report_path}")
except Exception as e:
    logger.warning(f"Could not write quality report to S3: {e}")

# ============================================================================
# Block promotion if quality gate fails
# ============================================================================

if overall_score < 0.95:
    logger.error(f"❌ QUALITY GATE FAILED: Score {overall_score:.3f} < 0.95")
    job.commit()
    sys.exit(1)

if critical_failures > 0:
    logger.error(f"❌ QUALITY GATE FAILED: {critical_failures} critical failures detected")
    job.commit()
    sys.exit(1)

logger.info("✅ GOLD QUALITY GATE PASSED")
job.commit()
