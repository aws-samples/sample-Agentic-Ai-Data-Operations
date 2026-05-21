# spec_hash: 443cf3198768bbc2d498f052e8c66983e535f1faa0a9e45a5eed928adf084c14
# template_id: quality_check
# template_hash: 0db9facab8f5f4808dbfbcd6c832bd034e5e56e9b2aa50e3708bbd26b212df7a
# schema_version: v1
# rendered_at: 2026-05-21T06:00:00Z
import sys
from datetime import datetime
from pathlib import Path

from pyspark.sql import functions as F
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.structured_logger import StructuredLogger

logger = StructuredLogger(
    agent="quality_check",
    workload="claims_v2",
    run_id="standalone",
)


def check_quality(spark, table_name, zone):
    logger.log("info", "quality_check_start", table=table_name, zone=zone)

    df = spark.table(table_name)
    total_rows = df.count()
    results = []

    # Completeness checks
    non_null_count = df.filter(F.col("claim_id").isNotNull()).count()
    score = non_null_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "comp_claim_id",
        "dimension": "completeness",
        "column": "claim_id",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })
    non_null_count = df.filter(F.col("member_id").isNotNull()).count()
    score = non_null_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "comp_member_id",
        "dimension": "completeness",
        "column": "member_id",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })
    non_null_count = df.filter(F.col("billed_amount").isNotNull()).count()
    score = non_null_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "comp_billed_amount",
        "dimension": "completeness",
        "column": "billed_amount",
        "score": score,
        "threshold": 0.99,
        "severity": "warning",
        "passed": score >= 0.99,
    })
    non_null_count = df.filter(F.col("service_date").isNotNull()).count()
    score = non_null_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "comp_service_date",
        "dimension": "completeness",
        "column": "service_date",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })

    # Uniqueness checks
    distinct_count = df.select("claim_id").distinct().count()
    score = distinct_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "uniq_claim_id",
        "dimension": "uniqueness",
        "column": "claim_id",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })

    # Validity checks
    valid_values = ["medical", "dental", "vision", "pharmacy"]
    valid_count = df.filter(F.col("claim_type").isin(valid_values)).count()
    score = valid_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "valid_claim_type",
        "dimension": "validity",
        "column": "claim_type",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })
    valid_values = ["paid", "denied", "pending", "appealed"]
    valid_count = df.filter(F.col("claim_status").isin(valid_values)).count()
    score = valid_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "valid_claim_status",
        "dimension": "validity",
        "column": "claim_status",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })
    valid_count = df.filter(
        (F.col("billed_amount") >= 0) &
        (F.col("billed_amount") <= 10000000)
    ).count()
    score = valid_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "valid_billed_positive",
        "dimension": "validity",
        "column": "billed_amount",
        "score": score,
        "threshold": 0.95,
        "severity": "warning",
        "passed": score >= 0.95,
    })

    # Compute overall score
    if results:
        overall_score = sum(r["score"] for r in results) / len(results)
    else:
        overall_score = 1.0

    critical_failures = sum(
        1 for r in results
        if not r["passed"] and r["severity"] == "critical"
    )

    # Determine gate threshold
    if zone == "silver":
        gate_threshold = 0.8
        max_critical = 0
    if zone == "gold":
        gate_threshold = 0.95
        max_critical = 0

    gate_passed = overall_score >= gate_threshold and critical_failures <= max_critical

    logger.log("info", "quality_check_complete",
        total_rows=total_rows, overall_score=overall_score,
        critical_failures=critical_failures, gate_passed=gate_passed,
        rules_checked=len(results))

    return {
        "workload": "claims_v2",
        "table": table_name,
        "zone": zone,
        "total_rows": total_rows,
        "overall_score": overall_score,
        "critical_failures": critical_failures,
        "gate_passed": gate_passed,
        "results": results,
    }


if __name__ == "__main__":
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "TABLE_NAME", "ZONE"])
    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    result = check_quality(spark, args["TABLE_NAME"], args["ZONE"])
    if not result["gate_passed"]:
        raise RuntimeError(
            f"Quality gate FAILED: score={result['overall_score']:.3f}, "
            f"critical_failures={result['critical_failures']}"
        )
