"""Quality checks for entity_resolved Silver.

Tool routing decision:
  - Intent: "run quality rules" -> TOOL_ROUTING.md Step 3: glue-data-quality
  - MCP server: glue-athena (REQUIRED)
  - Threshold: Silver >= 0.80, no critical failures (invariant: quality-gates).

Critical rules (block promotion):
  * entity_id: 100% complete, unique
  * entity_name, country: 100% complete
  * fiscal_year_end_month in [1, 12]
  * country matches ISO 3166-1 alpha-2 pattern (^[A-Z]{2}$)

Warning rules (logged, do not block):
  * isin matches ^[A-Z0-9]{12}$
  * cusip completeness > 0.50
"""

import os
import re
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
    workload="entity_resolved",
    run_id=args["run_id"],
)

threshold = float(args["threshold"])
df = spark.table(f"glue_catalog.{args['database']}.{args['table']}")
total_rows = df.count()

checks_passed = 0
checks_total = 0
critical_failures = []
warnings = []

# --- Critical rules ----------------------------------------------------------

# Completeness: entity_id, entity_name, country
for col in ("entity_id", "entity_name", "country"):
    checks_total += 1
    nulls = df.filter(F.col(col).isNull() | (F.col(col) == "")).count()
    if nulls == 0:
        checks_passed += 1
    else:
        critical_failures.append(f"{col} has {nulls} nulls/blanks")

# Uniqueness: entity_id
checks_total += 1
unique_count = df.select("entity_id").distinct().count()
if unique_count == total_rows:
    checks_passed += 1
else:
    critical_failures.append(
        f"entity_id has {total_rows - unique_count} duplicate(s)"
    )

# Validity: fiscal_year_end_month in [1, 12]
checks_total += 1
invalid_month = df.filter(
    F.col("fiscal_year_end_month").isNull()
    | (F.col("fiscal_year_end_month") < 1)
    | (F.col("fiscal_year_end_month") > 12)
).count()
if invalid_month == 0:
    checks_passed += 1
else:
    critical_failures.append(
        f"fiscal_year_end_month out of [1,12]: {invalid_month} row(s)"
    )

# Validity: country matches ISO 3166-1 alpha-2 (^[A-Z]{2}$)
checks_total += 1
invalid_country = df.filter(~F.col("country").rlike(r"^[A-Z]{2}$")).count()
if invalid_country == 0:
    checks_passed += 1
else:
    critical_failures.append(
        f"country not ISO 3166-1 alpha-2: {invalid_country} row(s)"
    )

# --- Warning rules -----------------------------------------------------------

# Validity: isin matches ^[A-Z0-9]{12}$  (warning — some entities lack ISIN)
isin_invalid = df.filter(
    F.col("isin").isNotNull() & ~F.col("isin").rlike(r"^[A-Z0-9]{12}$")
).count()
if isin_invalid > 0:
    warnings.append(f"isin format invalid: {isin_invalid} row(s)")

# Completeness: cusip > 0.50  (warning)
cusip_present = df.filter(F.col("cusip").isNotNull() & (F.col("cusip") != "")).count()
cusip_completeness = cusip_present / total_rows if total_rows else 0.0
if cusip_completeness < 0.50:
    warnings.append(
        f"cusip completeness {cusip_completeness:.2%} below 0.50 warning threshold"
    )

# --- Score & gate ------------------------------------------------------------

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
    log.error("Quality gate FAILED — blocking promotion", score=score, threshold=threshold)
    sys.exit(1)

log.info("Quality gate PASSED", score=score, threshold=threshold)
job.commit()
