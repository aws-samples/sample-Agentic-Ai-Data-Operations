# spec_hash: d2d13e37a361bcf549f7365578ce6184339ff937c5cf75bbf952ec75debb75a1
# template_id: quality_check
# template_hash: 594489fc03a353b4f53ef543f8e9c44f6333d79232929f34d1327b7e926787b4
# schema_version: v1
# rendered_at: 2026-10-22T18:18:44Z
import os
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
    workload="customer_orders",
    run_id="local",
)


def _configure_logger(args):
    """Use Airflow's ADOP_RUN_ID while keeping direct local calls testable."""
    logger.context["run_id"] = (
        args.get("ADOP_RUN_ID") or os.environ.get("ADOP_RUN_ID") or "local"
    )


def check_quality(spark, table_name, zone, args=None):
    _configure_logger(args or {})
    logger.log("info", "quality_check_start", table=table_name, zone=zone)

    df = spark.table(table_name)
    total_rows = df.count()
    results = []

    # Completeness checks
    non_null_count = df.filter(F.col("order_id").isNotNull()).count()
    score = non_null_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "completeness_order_id",
        "dimension": "completeness",
        "column": "order_id",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })
    if zone == "silver":
        non_null_count = df.filter(F.col("customer_id").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_customer_id",
            "dimension": "completeness",
            "column": "customer_id",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        non_null_count = df.filter(F.col("order_date").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_order_date",
            "dimension": "completeness",
            "column": "order_date",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        non_null_count = df.filter(F.col("product_id").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_product_id",
            "dimension": "completeness",
            "column": "product_id",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        non_null_count = df.filter(F.col("quantity").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_quantity",
            "dimension": "completeness",
            "column": "quantity",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        non_null_count = df.filter(F.col("unit_price").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_unit_price",
            "dimension": "completeness",
            "column": "unit_price",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        non_null_count = df.filter(F.col("discount_pct").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_discount_pct",
            "dimension": "completeness",
            "column": "discount_pct",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        non_null_count = df.filter(F.col("payment_method").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_payment_method",
            "dimension": "completeness",
            "column": "payment_method",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    non_null_count = df.filter(F.col("order_status").isNotNull()).count()
    score = non_null_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "completeness_order_status",
        "dimension": "completeness",
        "column": "order_status",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })
    if zone == "silver":
        non_null_count = df.filter(F.col("customer_email").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_customer_email_optional",
            "dimension": "completeness",
            "column": "customer_email",
            "score": score,
            "threshold": 0.0,
            "severity": "warning",
            "passed": score >= 0.0,
        })
    if zone == "silver":
        non_null_count = df.filter(F.col("customer_phone").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_customer_phone_optional",
            "dimension": "completeness",
            "column": "customer_phone",
            "score": score,
            "threshold": 0.0,
            "severity": "warning",
            "passed": score >= 0.0,
        })
    if zone == "silver":
        non_null_count = df.filter(F.col("customer_name").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_customer_name_optional",
            "dimension": "completeness",
            "column": "customer_name",
            "score": score,
            "threshold": 0.0,
            "severity": "warning",
            "passed": score >= 0.0,
        })
    if zone == "silver":
        non_null_count = df.filter(F.col("shipping_address").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_shipping_address_optional",
            "dimension": "completeness",
            "column": "shipping_address",
            "score": score,
            "threshold": 0.0,
            "severity": "warning",
            "passed": score >= 0.0,
        })
    if zone == "silver":
        non_null_count = df.filter(F.col("city").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_city_optional",
            "dimension": "completeness",
            "column": "city",
            "score": score,
            "threshold": 0.0,
            "severity": "warning",
            "passed": score >= 0.0,
        })
    if zone == "silver":
        non_null_count = df.filter(F.col("state").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_state_optional",
            "dimension": "completeness",
            "column": "state",
            "score": score,
            "threshold": 0.0,
            "severity": "warning",
            "passed": score >= 0.0,
        })
    if zone == "silver":
        non_null_count = df.filter(F.col("zip_code").isNotNull()).count()
        score = non_null_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "completeness_zip_code_optional",
            "dimension": "completeness",
            "column": "zip_code",
            "score": score,
            "threshold": 0.0,
            "severity": "warning",
            "passed": score >= 0.0,
        })

    # Uniqueness checks
    distinct_count = df.select("order_id").distinct().count()
    score = distinct_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "uniqueness_order_id",
        "dimension": "uniqueness",
        "column": "order_id",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })

    # Validity checks
    if zone == "silver":
        valid_count = df.filter(F.col("order_date").rlike("^[0-9]{4}-[0-9]{2}-[0-9]{2}$")).count()
        score = valid_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "validity_order_date_format",
            "dimension": "validity",
            "column": "order_date",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
        # are the valid ones. This is what accuracy and consistency rules need — a comparison
        # across columns, or a condition, rather than a single-column check.
        valid_count = df.filter(F.expr("to_date(order_date, \u0027yyyy-MM-dd\u0027) IS NOT NULL AND to_date(order_date, \u0027yyyy-MM-dd\u0027) \u003c= to_date(\u00272026-10-22\u0027)")).count()
        score = valid_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "validity_order_date_not_future",
            "dimension": "validity",
            "column": "order_date",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
        # are the valid ones. This is what accuracy and consistency rules need — a comparison
        # across columns, or a condition, rather than a single-column check.
        valid_count = df.filter(F.expr("quantity IS NOT NULL AND quantity = CAST(quantity AS INT)")).count()
        score = valid_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "validity_quantity_integer",
            "dimension": "validity",
            "column": "quantity",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
        # are the valid ones. This is what accuracy and consistency rules need — a comparison
        # across columns, or a condition, rather than a single-column check.
        valid_count = df.filter(F.expr("unit_price IS NOT NULL AND unit_price = CAST(unit_price AS DECIMAL(10,2))")).count()
        score = valid_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "validity_unit_price_decimal",
            "dimension": "validity",
            "column": "unit_price",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
        # are the valid ones. This is what accuracy and consistency rules need — a comparison
        # across columns, or a condition, rather than a single-column check.
        valid_count = df.filter(F.expr("discount_pct IS NOT NULL AND discount_pct = CAST(discount_pct AS DECIMAL(5,2))")).count()
        score = valid_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "validity_discount_pct_decimal",
            "dimension": "validity",
            "column": "discount_pct",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
    # are the valid ones. This is what accuracy and consistency rules need — a comparison
    # across columns, or a condition, rather than a single-column check.
    valid_count = df.filter(F.expr("revenue IS NOT NULL AND revenue = CAST(revenue AS DECIMAL(12,2))")).count()
    score = valid_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "validity_revenue_decimal",
        "dimension": "validity",
        "column": "revenue",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })
    if zone == "silver":
        # source-aware custom_sql: evaluate the target predicate only for source rows where the
        # source predicate is true. A zero-row source population passes; every source-present key
        # without a matching target row is a failure.
        source_present_df = (
            spark.table("glue_catalog.customer_orders_db.bronze_customer_orders")
            .filter(F.expr("credit_card_number IS NOT NULL"))
            .select(
                "order_id"        )
            .distinct()
        )
        target_present_df = (
            df.filter(F.expr("credit_card_token IS NOT NULL"))
            .select(
                "order_id"        )
            .distinct()
        )
        source_present_count = source_present_df.count()
        tokenization_failures = source_present_df.join(
            target_present_df,
            on=[
                "order_id"        ],
            how="left_anti",
        ).count()
        valid_count = source_present_count - tokenization_failures
        score = valid_count / source_present_count if source_present_count > 0 else 1.0
        results.append({
            "rule_id": "validity_credit_card_token_present",
            "dimension": "validity",
            "column": "credit_card_token",
            "score": score,
            "threshold": 1.0,
            "severity": "critical",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
        # are the valid ones. This is what accuracy and consistency rules need — a comparison
        # across columns, or a condition, rather than a single-column check.
        valid_count = df.filter(F.expr("quantity \u003e= 1")).count()
        score = valid_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "validity_quantity_minimum",
            "dimension": "validity",
            "column": "quantity",
            "score": score,
            "threshold": 1.0,
            "severity": "warning",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        valid_count = df.filter(
            (F.col("discount_pct") >= 0) &
            (F.col("discount_pct") <= 1)
        ).count()
        score = valid_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "validity_discount_pct_range",
            "dimension": "validity",
            "column": "discount_pct",
            "score": score,
            "threshold": 1.0,
            "severity": "warning",
            "passed": score >= 1.0,
        })

    # Consistency checks
    if zone == "silver":
        # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
        # are the valid ones. This is what accuracy and consistency rules need — a comparison
        # across columns, or a condition, rather than a single-column check.
        valid_count = df.filter(F.expr("ship_date IS NULL OR (to_date(order_date, \u0027yyyy-MM-dd\u0027) IS NOT NULL AND to_date(ship_date, \u0027yyyy-MM-dd\u0027) IS NOT NULL AND to_date(order_date, \u0027yyyy-MM-dd\u0027) \u003c= to_date(ship_date, \u0027yyyy-MM-dd\u0027))")).count()
        score = valid_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "consistency_order_ship_dates",
            "dimension": "consistency",
            "column": "order_date",
            "score": score,
            "threshold": 1.0,
            "severity": "warning",
            "passed": score >= 1.0,
        })
    if zone == "silver":
        # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
        # are the valid ones. This is what accuracy and consistency rules need — a comparison
        # across columns, or a condition, rather than a single-column check.
        valid_count = df.filter(F.expr("ship_date IS NOT NULL OR order_status IN (\u0027processing\u0027, \u0027cancelled\u0027)")).count()
        score = valid_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "consistency_ship_date_status",
            "dimension": "consistency",
            "column": "ship_date",
            "score": score,
            "threshold": 1.0,
            "severity": "warning",
            "passed": score >= 1.0,
        })

    # Accuracy checks
    if zone == "silver":
        # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
        # are the valid ones. This is what accuracy and consistency rules need — a comparison
        # across columns, or a condition, rather than a single-column check.
        valid_count = df.filter(F.expr("revenue = ROUND(quantity * unit_price * (1 - discount_pct), 2)")).count()
        score = valid_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "accuracy_revenue_formula",
            "dimension": "accuracy",
            "column": "revenue",
            "score": score,
            "threshold": 1.0,
            "severity": "warning",
            "passed": score >= 1.0,
        })
    if zone == "gold":
        # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
        # are the valid ones. This is what accuracy and consistency rules need — a comparison
        # across columns, or a condition, rather than a single-column check.
        valid_count = df.filter(F.expr("revenue = ROUND(revenue, 2)")).count()
        score = valid_count / total_rows if total_rows > 0 else 0.0
        results.append({
            "rule_id": "accuracy_revenue_formula_gold",
            "dimension": "accuracy",
            "column": "revenue",
            "score": score,
            "threshold": 1.0,
            "severity": "warning",
            "passed": score >= 1.0,
        })

    # Compliance checks — GDPR
    #
    # These were never rendered before. The spec carried them, they validated, and
    # quality_check.py.j2 had no loop over compliance_rules.rules — so a rule the human
    # designated CRITICAL and blocking could not contribute to critical_failures below,
    # because that count only sees rules that were rendered. The masking gate attested a
    # control nothing executed.
    #
    # They score into `results` on the same footing as every other dimension, so a failing
    # compliance rule raises critical_failures and blocks the gate.
    # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
    # are the valid ones. This is what accuracy and consistency rules need — a comparison
    # across columns, or a condition, rather than a single-column check.
    valid_count = df.filter(F.expr("is_deleted = true OR consent_given IS NOT NULL")).count()
    score = valid_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "gdpr_consent_not_null_for_active",
        "dimension": "compliance",
        "column": "consent_given",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })
    # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
    # are the valid ones. This is what accuracy and consistency rules need — a comparison
    # across columns, or a condition, rather than a single-column check.
    valid_count = df.filter(F.expr("is_deleted = true OR consent_timestamp IS NOT NULL")).count()
    score = valid_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "gdpr_consent_timestamp_for_active",
        "dimension": "compliance",
        "column": "consent_timestamp",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })
    # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
    # are the valid ones. This is what accuracy and consistency rules need — a comparison
    # across columns, or a condition, rather than a single-column check.
    valid_count = df.filter(F.expr("is_deleted IS NOT NULL")).count()
    score = valid_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "gdpr_is_deleted_flag",
        "dimension": "compliance",
        "column": "is_deleted",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })
    # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
    # are the valid ones. This is what accuracy and consistency rules need — a comparison
    # across columns, or a condition, rather than a single-column check.
    valid_count = df.filter(F.expr("data_subject_id IS NOT NULL AND data_subject_id = customer_id")).count()
    score = valid_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "gdpr_data_subject_id",
        "dimension": "compliance",
        "column": "data_subject_id",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })
    # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
    # are the valid ones. This is what accuracy and consistency rules need — a comparison
    # across columns, or a condition, rather than a single-column check.
    valid_count = df.filter(F.expr("is_deleted = false OR deletion_requested_at IS NOT NULL")).count()
    score = valid_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "gdpr_deletion_request_semantics",
        "dimension": "compliance",
        "column": "deletion_requested_at",
        "score": score,
        "threshold": 1.0,
        "severity": "critical",
        "passed": score >= 1.0,
    })
    # custom_sql: the predicate is a Spark SQL expression from the spec. Rows satisfying it
    # are the valid ones. This is what accuracy and consistency rules need — a comparison
    # across columns, or a condition, rather than a single-column check.
    valid_count = df.filter(F.expr("true")).count()
    score = valid_count / total_rows if total_rows > 0 else 0.0
    results.append({
        "rule_id": "gdpr_retention_configuration_warning",
        "dimension": "compliance",
        "column": "order_id",
        "score": score,
        "threshold": 1.0,
        "severity": "warning",
        "passed": score >= 1.0,
    })

    # Compute overall score
    #
    # An empty result set used to score 1.0 and sail through the gate. That is the whole
    # defect this file keeps demonstrating: nothing to check is not the same as nothing
    # wrong. It matters more now that rules carry a `zone` — tag every rule "silver" and the
    # Gold gate would have had zero rules and passed with a perfect score, which is a worse
    # outcome than the AnalysisException it used to raise.
    if not results:
        raise RuntimeError(
            f"No quality rules applied to zone '{zone}' of {table_name}. A zone with no "
            f"rules cannot be scored, and reporting a pass for it would attest checks that "
            f"never ran. Tag rules for this zone in quality_spec (rules[].zone), or remove "
            f"the gate for it."
        )
    overall_score = sum(r["score"] for r in results) / len(results)

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
    failed_rules = [
        {
            "rule_id": rule["rule_id"],
            "severity": rule["severity"],
            "score": rule["score"],
            "threshold": rule["threshold"],
        }
        for rule in results
        if not rule["passed"]
    ]

    logger.log("info", "quality_check_complete",
        total_rows=total_rows, overall_score=overall_score,
        critical_failures=critical_failures, gate_passed=gate_passed,
        rules_checked=len(results), failed_rules=failed_rules)

    return {
        "workload": "customer_orders",
        "table": table_name,
        "zone": zone,
        "total_rows": total_rows,
        "overall_score": overall_score,
        "critical_failures": critical_failures,
        "gate_passed": gate_passed,
        "results": results,
    }


if __name__ == "__main__":
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "ADOP_RUN_ID", "TABLE_NAME", "ZONE"])
    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    result = check_quality(spark, args["TABLE_NAME"], args["ZONE"], args)
    if not result["gate_passed"]:
        raise RuntimeError(
            f"Quality gate FAILED: score={result['overall_score']:.3f}, "
            f"critical_failures={result['critical_failures']}"
        )
