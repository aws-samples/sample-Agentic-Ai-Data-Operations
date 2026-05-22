"""Silver transformation: validate, latest-wins dedup for entity classifications.

Tool routing decision:
  - Intent: "transform Bronze to Silver" -> TOOL_ROUTING.md Step 3: glue-etl-iceberg-silver
  - MCP server: glue-athena (REQUIRED)
  - Mandatory flag: --enable-data-lineage: true (invariant: lineage-always)
  - Output: Apache Iceberg on S3 Tables.
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window

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
    "source_database",
    "source_table",
    "target_database",
    "target_table",
    "run_id",
    "data_lake_bucket",
])
job.init(args["JOB_NAME"], args)

log = StructuredLogger(
    agent="Transformation Agent",
    workload="reference",
    run_id=args["run_id"],
)

df = glueContext.create_dynamic_frame.from_catalog(
    database=args["source_database"],
    table_name=args["source_table"],
).toDF()

initial_count = df.count()
log.info("Bronze read complete", rows=initial_count, table=args["source_table"])

df = df.withColumn("ingestion_ts", F.current_timestamp())

quarantine_mask = (
    F.col("entity_id").isNull()
    | (F.col("entity_id") == "")
    | F.col("classification_system").isNull()
    | (F.col("classification_system") == "")
)
quarantined = df.filter(quarantine_mask)
clean = df.filter(~quarantine_mask)

window = Window.partitionBy("entity_id", "classification_system") \
               .orderBy(F.col("ingestion_ts").desc())
clean = clean.withColumn("_row_num", F.row_number().over(window))
clean = clean.filter(F.col("_row_num") == 1).drop("_row_num")

final_count = clean.count()
quarantine_count = quarantined.count()

clean.writeTo(
    f"glue_catalog.{args['target_database']}.{args['target_table']}"
).using("iceberg").createOrReplace()

if quarantine_count > 0:
    quarantined.write.mode("append").parquet(
        f"s3://{args['data_lake_bucket']}/quarantine/reference/"
    )
    log.warn("Records quarantined", count=quarantine_count, reason="null PK column")

log.info(
    "Silver transform complete",
    input_rows=initial_count,
    silver_rows=final_count,
    quarantined=quarantine_count,
)
job.commit()
