"""Silver transformation: drop sedol, explode aliases, cast types, latest-wins dedup.

Tool routing decision:
  - Intent: "transform Bronze to Silver" -> TOOL_ROUTING.md Step 3: glue-etl-iceberg-silver
  - MCP server: glue-athena (REQUIRED)
  - Mandatory flag: --enable-data-lineage: true (invariant: lineage-always)
  - Output: Apache Iceberg on S3 Tables (Silver is ALWAYS Iceberg)
  - Reads from Glue Catalog (lineage tracking)
  - Writes to Glue Catalog via .saveAsTable() / .writeTo() Iceberg syntax

Idempotency: full-overwrite via createOrReplace. Re-running on the same Bronze
input produces an identical Silver table.
"""

import os
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType
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
    workload="entity_resolved",
    run_id=args["run_id"],
)

df = glueContext.create_dynamic_frame.from_catalog(
    database=args["source_database"],
    table_name=args["source_table"],
).toDF()

initial_count = df.count()
log.info("Bronze read complete", rows=initial_count, table=args["source_table"])

# Drop 100%-null sedol per Phase 1 decision.
if "sedol" in df.columns:
    df = df.drop("sedol")

# Pipe-delimited aliases -> array<string>. Use literal '|' (escaped for regex).
df = df.withColumn("aliases", F.split(F.col("aliases"), r"\|"))

# Type cast fiscal_year_end_month string -> int. Out-of-range or non-numeric values
# become NULL, then the quality gate's critical rule will fail the run.
df = df.withColumn(
    "fiscal_year_end_month",
    F.col("fiscal_year_end_month").cast(IntegerType()),
)

# Stamp ingestion timestamp BEFORE dedup so latest-wins ordering is deterministic
# within a single run.
df = df.withColumn("ingestion_ts", F.current_timestamp())

# Quarantine rows that violate hard validation rules before dedup.
quarantine_mask = (
    F.col("entity_id").isNull()
    | (F.col("entity_id") == "")
    | F.col("entity_name").isNull()
    | F.col("country").isNull()
)
quarantined = df.filter(quarantine_mask)
clean = df.filter(~quarantine_mask)

# Latest-wins dedup keyed on entity_id (Phase 1 user decision).
window = Window.partitionBy("entity_id").orderBy(F.col("ingestion_ts").desc())
clean = clean.withColumn("_row_num", F.row_number().over(window))
clean = clean.filter(F.col("_row_num") == 1).drop("_row_num")

final_count = clean.count()
quarantine_count = quarantined.count()

# Iceberg write — full overwrite each run (small reference table).
clean.writeTo(
    f"glue_catalog.{args['target_database']}.{args['target_table']}"
).using("iceberg").createOrReplace()

if quarantine_count > 0:
    quarantined.write.mode("append").parquet(
        "s3://${var:data_lake_bucket}/quarantine/entity_resolved/"
    )
    log.warn("Records quarantined", count=quarantine_count, reason="null entity_id/entity_name/country")

log.info(
    "Silver transform complete",
    input_rows=initial_count,
    silver_rows=final_count,
    quarantined=quarantine_count,
)

job.commit()
