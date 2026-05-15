"""Silver transformation: Clean, deduplicate, validate attendance data.

Tool routing decision:
  - Intent: "transform Bronze to Silver" → TOOL_ROUTING.md Step 3: glue-etl-iceberg-silver
  - MCP server: glue-athena (REQUIRED)
  - Mandatory flag: --enable-data-lineage: true (invariant: lineage-always)
  - Output: Apache Iceberg on S3 Tables (Silver is ALWAYS Iceberg)
  - Reads from Glue Catalog (invariant: lineage tracking requires catalog reads)
  - Writes to Glue Catalog (invariant: lineage tracking requires catalog writes)
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, TimestampType
from pyspark.sql.window import Window

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)

args = getResolvedOptions(sys.argv, [
    "JOB_NAME",
    "source_database",
    "source_table",
    "target_database",
    "target_table",
])
job.init(args["JOB_NAME"], args)

df = glueContext.create_dynamic_frame.from_catalog(
    database=args["source_database"],
    table_name=args["source_table"],
).toDF()

initial_count = df.count()

df = df.withColumn("check_in", F.col("check_in").cast(TimestampType()))
df = df.withColumn("check_out", F.col("check_out").cast(TimestampType()))
df = df.withColumn("hours_worked", F.col("hours_worked").cast(DoubleType()))

df = df.withColumn("attendance_date", F.to_date(F.col("check_in")))
df = df.withColumn(
    "is_remote",
    F.when(F.col("location") == "REMOTE", True).otherwise(False),
)
df = df.withColumn("ingestion_ts", F.current_timestamp())

valid_statuses = ["present", "absent", "half-day", "sick-leave", "vacation", "remote"]
quarantine_mask = (
    F.col("employee_id").isNull()
    | (F.col("hours_worked") < 0)
    | (F.col("hours_worked") > 24)
    | (~F.col("status").isin(valid_statuses))
    | (
        (F.col("status") == "present")
        & ((F.col("check_in").isNull()) | (F.col("check_out").isNull()))
    )
    | ((F.col("status") == "present") & (F.col("check_out") < F.col("check_in")))
)

quarantined = df.filter(quarantine_mask)
clean = df.filter(~quarantine_mask)

window = Window.partitionBy("employee_id", "attendance_date").orderBy(
    F.col("check_in").desc()
)
clean = clean.withColumn("_row_num", F.row_number().over(window))
clean = clean.filter(F.col("_row_num") == 1).drop("_row_num")

final_count = clean.count()
quarantine_count = quarantined.count()

clean.writeTo(
    f"glue_catalog.{args['target_database']}.{args['target_table']}"
).using("iceberg").createOrReplace()

if quarantine_count > 0:
    quarantined.write.mode("append").parquet(
        f"s3://${{var:data_lake_bucket}}/quarantine/employee_attendance/"
    )

print(f"Silver transform complete: {initial_count} input → {final_count} clean + {quarantine_count} quarantined")

job.commit()
