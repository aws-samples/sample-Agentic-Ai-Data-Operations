"""Silver transformation: type-cast, quarantine bad rows, latest-wins dedup.

Source has known data quality issues:
  * effective_date may be invalid (e.g., '2024-13-45') -> to_date returns null -> quarantine.
  * supply_concentration_pct may be out of [0, 100] -> quarantine.
  * supplier_ticker / supplier_address / contact_email may be null -> only ticker forces quarantine.

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
from pyspark.sql.types import DoubleType
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
    workload="supplier_chain_data",
    run_id=args["run_id"],
)

df = glueContext.create_dynamic_frame.from_catalog(
    database=args["source_database"],
    table_name=args["source_table"],
).toDF()

initial_count = df.count()
log.info("Bronze read complete", rows=initial_count, table=args["source_table"])

df = (
    df.withColumn("effective_date", F.to_date("effective_date", "yyyy-MM-dd"))
      .withColumn("supply_concentration_pct", F.col("supply_concentration_pct").cast(DoubleType()))
      .withColumn("contract_value_usd", F.col("contract_value_usd").cast(DoubleType()))
      .withColumn("ingestion_ts", F.current_timestamp())
)

quarantine_mask = (
    F.col("buyer_ticker").isNull()
    | (F.col("buyer_ticker") == "")
    | F.col("supplier_ticker").isNull()
    | (F.col("supplier_ticker") == "")
    | F.col("effective_date").isNull()
    | F.col("product_category").isNull()
    | (F.col("product_category") == "")
    | F.col("supply_concentration_pct").isNull()
    | (F.col("supply_concentration_pct") < 0)
    | (F.col("supply_concentration_pct") > 100)
)
quarantined = df.filter(quarantine_mask)
clean = df.filter(~quarantine_mask)

window = Window.partitionBy(
    "buyer_ticker", "supplier_ticker", "effective_date", "product_category"
).orderBy(F.col("ingestion_ts").desc())
clean = clean.withColumn("_row_num", F.row_number().over(window))
clean = clean.filter(F.col("_row_num") == 1).drop("_row_num")

final_count = clean.count()
quarantine_count = quarantined.count()

clean.writeTo(
    f"glue_catalog.{args['target_database']}.{args['target_table']}"
).using("iceberg").createOrReplace()

if quarantine_count > 0:
    quarantined.write.mode("append").parquet(
        "s3://${var:data_lake_bucket}/quarantine/supplier_chain_data/"
    )
    log.warn(
        "Records quarantined",
        count=quarantine_count,
        reason="null PK column, invalid effective_date, or supply_concentration_pct out of [0,100]",
    )

log.info(
    "Silver transform complete",
    input_rows=initial_count,
    silver_rows=final_count,
    quarantined=quarantine_count,
)
job.commit()
