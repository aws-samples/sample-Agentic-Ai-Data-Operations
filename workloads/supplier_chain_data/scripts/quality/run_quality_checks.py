"""Quality checks for supplier_chain_data Silver.

Tool routing decision:
  - Intent: "run quality rules" -> TOOL_ROUTING.md Step 3: glue-data-quality
  - MCP server: glue-athena (REQUIRED)
  - Threshold: Silver >= 0.80, no critical failures.

Critical:
  * Completeness on buyer_ticker, supplier_ticker, effective_date,
    product_category, relationship_type
  * Uniqueness of (buyer_ticker, supplier_ticker, effective_date, product_category)
  * supply_concentration_pct in [0, 100]
  * contract_value_usd >= 0

Warning:
  * contact_email matches simple email regex (when not null)
  * FK: buyer_ticker exists in entity_resolved.silver_entity_resolved.ticker

PII columns (contact_email, supplier_address) are masked in logs.
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

# StructuredLogger is provided to Glue jobs via --extra-py-files=shared.zip
# (which puts shared/ on PYTHONPATH at runtime). For local imports, the
# repo root is on sys.path via the test harness / orchestrator.
from shared.utils.structured_logger import StructuredLogger

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
    workload="supplier_chain_data",
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

for col in ("buyer_ticker", "supplier_ticker", "effective_date",
            "product_category", "relationship_type"):
    checks_total += 1
    nulls = df.filter(F.col(col).isNull() | (F.col(col) == "")).count()
    if nulls == 0:
        checks_passed += 1
    else:
        critical_failures.append(f"{col} has {nulls} null/blank(s)")

checks_total += 1
unique = df.select(
    "buyer_ticker", "supplier_ticker", "effective_date", "product_category"
).distinct().count()
if unique == total_rows:
    checks_passed += 1
else:
    critical_failures.append(f"PK has {total_rows - unique} duplicate(s)")

checks_total += 1
bad_concentration = df.filter(
    (F.col("supply_concentration_pct") < 0)
    | (F.col("supply_concentration_pct") > 100)
).count()
if bad_concentration == 0:
    checks_passed += 1
else:
    critical_failures.append(
        f"supply_concentration_pct out of [0,100]: {bad_concentration} row(s)"
    )

checks_total += 1
neg_value = df.filter(F.col("contract_value_usd") < 0).count()
if neg_value == 0:
    checks_passed += 1
else:
    critical_failures.append(f"contract_value_usd < 0: {neg_value} row(s)")

# --- Warning ----------------------------------------------------------------

bad_email = df.filter(
    F.col("contact_email").isNotNull()
    & ~F.col("contact_email").rlike(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
).count()
if bad_email > 0:
    warnings.append(f"contact_email format invalid: {bad_email} row(s)")

try:
    er = spark.table("glue_catalog.entity_resolved_db.silver_entity_resolved").select("ticker").distinct()
    unmatched = df.alias("t").join(
        er.alias("e"), F.col("t.buyer_ticker") == F.col("e.ticker"), "left"
    ).filter(F.col("e.ticker").isNull()).count()
    if unmatched > 0:
        warnings.append(f"buyer_ticker not in entity_resolved.ticker: {unmatched} row(s)")
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
