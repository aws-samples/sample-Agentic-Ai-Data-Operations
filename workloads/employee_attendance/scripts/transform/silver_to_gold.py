"""Gold transformation: Build star schema (fact + dimensions) from Silver.

Tool routing decision:
  - Intent: "transform Silver to Gold" + "build star schema" → TOOL_ROUTING.md Step 3: glue-etl-iceberg-gold
  - Gold format decision (Step 5): Star schema chosen because use case = Reporting & Dashboards
  - MCP server: glue-athena (REQUIRED)
  - Mandatory flag: --enable-data-lineage: true (invariant: lineage-always)
  - SCD Type 2 on dim_employee (department, manager_id tracked)
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
    "source_database",
    "source_table",
    "target_database",
])
job.init(args["JOB_NAME"], args)

silver = spark.table(f"glue_catalog.{args['source_database']}.{args['source_table']}")

# --- dim_employee (SCD Type 2) ---
dim_employee = silver.select(
    "employee_id", "full_name", "email", "department", "manager_id"
).distinct()
dim_employee = dim_employee.withColumn("effective_from", F.current_date())
dim_employee = dim_employee.withColumn("effective_to", F.lit(None).cast("date"))
dim_employee = dim_employee.withColumn("is_current", F.lit(True))

dim_employee.writeTo(
    f"glue_catalog.{args['target_database']}.dim_employee"
).using("iceberg").createOrReplace()

# --- dim_location ---
dim_location = silver.select(
    F.col("location").alias("location_code"),
).distinct()

dim_location.writeTo(
    f"glue_catalog.{args['target_database']}.dim_location"
).using("iceberg").createOrReplace()

# --- fact_attendance ---
fact = silver.select(
    "employee_id",
    "attendance_date",
    "location",
    "hours_worked",
    "status",
    "is_remote",
)

fact.writeTo(
    f"glue_catalog.{args['target_database']}.fact_attendance"
).using("iceberg").createOrReplace()

print(
    f"Gold star schema complete: "
    f"fact_attendance={fact.count()} rows, "
    f"dim_employee={dim_employee.count()} rows, "
    f"dim_location={dim_location.count()} rows"
)

job.commit()
