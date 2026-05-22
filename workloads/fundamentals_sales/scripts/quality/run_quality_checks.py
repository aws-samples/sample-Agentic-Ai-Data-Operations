"""Quality checks for fundamentals_sales Silver.

Tool routing decision:
  - Intent: "run quality rules" -> TOOL_ROUTING.md Step 3: glue-data-quality
  - MCP server: glue-athena (REQUIRED)
  - Threshold: Silver >= 0.80, no critical failures.

Critical:
  * Completeness on entity_id, fiscal_period_id, fiscal_year, fiscal_period,
    metric, value_usd, currency
  * Uniqueness of (entity_id, fiscal_period_id, metric)
  * fiscal_period in (FY, Q1, Q2, Q3, Q4)
  * value_usd >= 0

Warning:
  * currency ISO 4217
  * FK: entity_id exists in entity_resolved.silver_entity_resolved
"""

import os
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from shared.utils.structured_logger import StructuredLogger  # noqa: E402

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)

args = getResolvedOptions(sys.argv, [
    "JOB_NAME",
    "database",
    "table",
    "zone",
    "threshold",
    "run_id",
])
job.init(args["JOB_NAME"], args)

log = StructuredLogger(
    agent="Quality Agent",
    workload="fundamentals_sales",
    run_id=args["run_id"],
)

threshold = float(args["threshold"])
df = spark.table(f"glue_catalog.{args['database']}.{args['table']}")
total_rows = df.count()

checks_passed = 0
checks_total = 0
critical_failures = []
warnings = []

# --- Critical ---------------------------------------------------------------

for col in ("entity_id", "fiscal_period_id", "fiscal_year", "fiscal_period",
            "metric", "value_usd", "currency"):
    checks_total += 1
    nulls = df.filter(F.col(col).isNull()).count()
    if nulls == 0:
        checks_passed += 1
    else:
        critical_failures.append(f"{col} has {nulls} null(s)")

checks_total += 1
unique = df.select("entity_id", "fiscal_period_id", "metric").distinct().count()
if unique == total_rows:
    checks_passed += 1
else:
    critical_failures.append(f"PK has {total_rows - unique} duplicate(s)")

checks_total += 1
bad_period = df.filter(~F.col("fiscal_period").isin("FY", "Q1", "Q2", "Q3", "Q4")).count()
if bad_period == 0:
    checks_passed += 1
else:
    critical_failures.append(f"fiscal_period out of allowed set: {bad_period} row(s)")

checks_total += 1
neg_value = df.filter(F.col("value_usd") < 0).count()
if neg_value == 0:
    checks_passed += 1
else:
    critical_failures.append(f"value_usd negative: {neg_value} row(s)")

# --- Warning ----------------------------------------------------------------

bad_currency = df.filter(
    F.col("currency").isNotNull() & ~F.col("currency").rlike(r"^[A-Z]{3}$")
).count()
if bad_currency > 0:
    warnings.append(f"currency not ISO 4217: {bad_currency} row(s)")

try:
    er = spark.table("glue_catalog.entity_resolved_db.silver_entity_resolved").select("entity_id")
    unmatched = df.alias("t").join(
        er.alias("e"), F.col("t.entity_id") == F.col("e.entity_id"), "left"
    ).filter(F.col("e.entity_id").isNull()).count()
    if unmatched > 0:
        warnings.append(f"entity_id not in entity_resolved: {unmatched} row(s)")
except Exception as exc:
    log.warn("FK check skipped — entity_resolved not available", error=str(exc))

# --- Score & gate -----------------------------------------------------------

score = checks_passed / checks_total if checks_total > 0 else 0.0

log.info(
    "Quality summary",
    zone=args["zone"],
    score=score,
    threshold=threshold,
    checks_passed=checks_passed,
    checks_total=checks_total,
    critical_failures=len(critical_failures),
    warnings=len(warnings),
)

for w in warnings:
    log.warn("Quality warning", detail=w)
for cf in critical_failures:
    log.error("Critical quality failure", detail=cf)

if score < threshold or critical_failures:
    log.error("Quality gate FAILED", score=score, threshold=threshold)
    sys.exit(1)

log.info("Quality gate PASSED", score=score, threshold=threshold)
job.commit()
