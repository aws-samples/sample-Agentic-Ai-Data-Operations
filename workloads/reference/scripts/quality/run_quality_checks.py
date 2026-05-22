"""Quality checks for reference Silver.

Tool routing decision:
  - Intent: "run quality rules" -> TOOL_ROUTING.md Step 3: glue-data-quality
  - MCP server: glue-athena (REQUIRED)
  - Threshold: Silver >= 0.80, no critical failures.

Critical:
  * Completeness on all PK + sector/industry code+name columns
  * Uniqueness of (entity_id, classification_system)
  * GICS-style numeric codes match ^[0-9]{2,8}$

Warning:
  * GICS hierarchy (industry_group_code prefixed by sector_code, etc.)
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
    workload="reference",
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

required_cols = (
    "entity_id", "classification_system",
    "sector_code", "sector_name",
    "industry_group_code", "industry_group_name",
    "industry_code", "industry_name",
)
for col in required_cols:
    checks_total += 1
    nulls = df.filter(F.col(col).isNull() | (F.col(col) == "")).count()
    if nulls == 0:
        checks_passed += 1
    else:
        critical_failures.append(f"{col} has {nulls} null/blank(s)")

checks_total += 1
unique = df.select("entity_id", "classification_system").distinct().count()
if unique == total_rows:
    checks_passed += 1
else:
    critical_failures.append(f"PK has {total_rows - unique} duplicate(s)")

# Numeric pattern on each code column.
for col in ("sector_code", "industry_group_code", "industry_code"):
    checks_total += 1
    bad = df.filter(~F.col(col).rlike(r"^[0-9]{2,8}$")).count()
    if bad == 0:
        checks_passed += 1
    else:
        critical_failures.append(f"{col} not numeric ^[0-9]{{2,8}}$: {bad} row(s)")

# --- Warning ----------------------------------------------------------------

# GICS hierarchy: industry_group_code starts with sector_code, industry_code starts with industry_group_code.
hier_violation = df.filter(
    (F.col("classification_system") == "GICS")
    & (
        ~F.col("industry_group_code").startswith(F.col("sector_code"))
        | ~F.col("industry_code").startswith(F.col("industry_group_code"))
    )
).count()
if hier_violation > 0:
    warnings.append(f"GICS hierarchy violated: {hier_violation} row(s)")

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
