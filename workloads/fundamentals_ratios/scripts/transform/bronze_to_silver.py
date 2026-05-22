"""Silver transformation: drop 100%-null cols, type-cast, latest-wins dedup.

Tool routing decision:
  - Intent: "transform Bronze to Silver" -> TOOL_ROUTING.md Step 3: glue-etl-iceberg-silver
  - MCP server: glue-athena (REQUIRED)
  - Mandatory flag: --enable-data-lineage: true (invariant: lineage-always)
  - Output: Apache Iceberg on S3 Tables.
"""

import os
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType
from pyspark.sql.window import Window

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from shared.utils.structured_logger import StructuredLogger  # noqa: E402

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
])
job.init(args["JOB_NAME"], args)

log = StructuredLogger(
    agent="Transformation Agent",
    workload="fundamentals_ratios",
    run_id=args["run_id"],
)

df = glueContext.create_dynamic_frame.from_catalog(
    database=args["source_database"],
    table_name=args["source_table"],
).toDF()

initial_count = df.count()
log.info("Bronze read complete", rows=initial_count, table=args["source_table"])

# Drop 100%-null source columns per Phase 1 decision.
for col in ("roa", "debt_to_equity", "current_ratio", "load_timestamp"):
    if col in df.columns:
        df = df.drop(col)

df = (
    df.withColumn("fiscal_year", F.col("fiscal_year").cast(IntegerType()))
      .withColumn("pe_ratio", F.col("pe_ratio").cast(DoubleType()))
      .withColumn("pb_ratio", F.col("pb_ratio").cast(DoubleType()))
      .withColumn("ev_ebitda", F.col("ev_ebitda").cast(DoubleType()))
      .withColumn("roe", F.col("roe").cast(DoubleType()))
      .withColumn("ingestion_ts", F.current_timestamp())
)

quarantine_mask = (
    F.col("entity_id").isNull()
    | (F.col("entity_id") == "")
    | F.col("fiscal_period_id").isNull()
    | (F.col("fiscal_period_id") == "")
)
quarantined = df.filter(quarantine_mask)
clean = df.filter(~quarantine_mask)

window = Window.partitionBy("entity_id", "fiscal_period_id") \
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
        "s3://${var:data_lake_bucket}/quarantine/fundamentals_ratios/"
    )
    log.warn("Records quarantined", count=quarantine_count, reason="null PK column")

log.info(
    "Silver transform complete",
    input_rows=initial_count,
    silver_rows=final_count,
    quarantined=quarantine_count,
)
job.commit()
