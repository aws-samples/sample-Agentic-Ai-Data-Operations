"""Quality checks: Run DQDL rules against Silver/Gold tables.

Tool routing decision:
  - Intent: "run quality rules" → TOOL_ROUTING.md Step 3: glue-data-quality
  - MCP server: glue-athena (REQUIRED)
  - Thresholds: Silver >= 0.80, Gold >= 0.95 (invariant: quality-gates)
  - Critical failures block promotion regardless of overall score
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

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
])
job.init(args["JOB_NAME"], args)

threshold = float(args["threshold"])
df = spark.table(f"glue_catalog.{args['database']}.{args['table']}")

total_rows = df.count()
checks_passed = 0
checks_total = 0
critical_failures = []

# Completeness: employee_id
checks_total += 1
null_employee_ids = df.filter(F.col("employee_id").isNull()).count()
if null_employee_ids == 0:
    checks_passed += 1
else:
    critical_failures.append(f"employee_id has {null_employee_ids} nulls")

# Uniqueness: employee_id + attendance_date
checks_total += 1
dedup_count = df.select("employee_id", "attendance_date").distinct().count()
if dedup_count == total_rows:
    checks_passed += 1
else:
    critical_failures.append(
        f"Duplicate rows: {total_rows - dedup_count} duplicates found"
    )

# Validity: hours_worked between 0 and 24
checks_total += 1
invalid_hours = df.filter(
    (F.col("hours_worked") < 0) | (F.col("hours_worked") > 24)
).count()
if invalid_hours == 0:
    checks_passed += 1
else:
    critical_failures.append(f"hours_worked out of range: {invalid_hours} rows")

# Validity: status in allowed values
checks_total += 1
valid_statuses = ["present", "absent", "half-day", "sick-leave", "vacation", "remote"]
invalid_status = df.filter(~F.col("status").isin(valid_statuses)).count()
if invalid_status == 0:
    checks_passed += 1
else:
    critical_failures.append(f"Invalid status values: {invalid_status} rows")

# Consistency: present employees have hours > 0
checks_total += 1
inconsistent = df.filter(
    (F.col("status") == "present") & (F.col("hours_worked") == 0)
).count()
if inconsistent == 0:
    checks_passed += 1
else:
    critical_failures.append(
        f"Present employees with 0 hours: {inconsistent} rows"
    )

score = checks_passed / checks_total if checks_total > 0 else 0.0

print(f"Quality score ({args['zone']}): {score:.2%} ({checks_passed}/{checks_total} passed)")
print(f"Threshold: {threshold:.2%}")
print(f"Critical failures: {len(critical_failures)}")

if critical_failures:
    for f_msg in critical_failures:
        print(f"  CRITICAL: {f_msg}")

if score < threshold or critical_failures:
    print("QUALITY GATE: FAILED — blocking zone promotion")
    sys.exit(1)
else:
    print("QUALITY GATE: PASSED")

job.commit()
