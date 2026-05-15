"""Bronze ingestion: Copy raw attendance CSV from source to Bronze zone.

Tool routing decision:
  - Source is S3 → TOOL_ROUTING.md Step 4: "S3 source → s3-copy-sync"
  - MCP server: core (WARN, slow startup) — prefer MCP; fall back to CLI if timeout
  - Bronze is immutable: S3 Object Lock in Governance mode
"""

import sys
from datetime import datetime

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

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
])
job.init(args["JOB_NAME"], args)

source_path = f"s3://{args['source_bucket']}/{args['source_prefix']}"
ingestion_date = datetime.utcnow().strftime("%Y-%m-%d")
target_path = (
    f"s3://{args['target_bucket']}/{args['target_prefix']}"
    f"/ingestion_date={ingestion_date}/"
)

df = spark.read.option("header", "true").option("inferSchema", "true").csv(source_path)

df.write.mode("append").parquet(target_path)

print(f"Bronze ingestion complete: {df.count()} rows → {target_path}")

job.commit()
