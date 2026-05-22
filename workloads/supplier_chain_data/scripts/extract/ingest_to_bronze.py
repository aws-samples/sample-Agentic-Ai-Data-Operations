"""Bronze ingestion: copy raw supplier_data CSV from source to Bronze zone.

Tool routing decision:
  - Source is S3 -> TOOL_ROUTING.md Step 4: "S3 source -> s3-copy-sync"
  - MCP server: core (WARN)
  - Bronze is immutable: write to ingestion_date partition.
"""

import sys
from datetime import datetime

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

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
    "source_bucket",
    "source_prefix",
    "target_bucket",
    "target_prefix",
    "run_id",
])
job.init(args["JOB_NAME"], args)

log = StructuredLogger(
    agent="Extract Agent",
    workload="supplier_chain_data",
    run_id=args["run_id"],
)

source_path = f"s3://{args['source_bucket']}/{args['source_prefix']}"
ingestion_date = datetime.utcnow().strftime("%Y-%m-%d")
target_path = (
    f"s3://{args['target_bucket']}/{args['target_prefix']}"
    f"/ingestion_date={ingestion_date}/"
)

log.info("Bronze ingest starting", source=source_path, target=target_path)
df = spark.read.option("header", "true").option("inferSchema", "true").csv(source_path)
row_count = df.count()
df.write.mode("append").parquet(target_path)
log.info("Bronze ingest complete", rows=row_count, partition=ingestion_date)
job.commit()
