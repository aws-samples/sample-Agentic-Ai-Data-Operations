# spec_hash: 1ba019f45bf4d074fa80ba9f997c59d25c7ced83b79629d423b290ac31ef2332
# template_id: bronze_ingestion
# template_hash: bf741bc31d513ca85bca5317ca70e0f384ff44287f84e9d7c2d40f96d6196eca
# schema_version: v1
# rendered_at: 2026-05-21T06:00:00Z
import sys
from datetime import datetime
from pathlib import Path

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.structured_logger import StructuredLogger

logger = StructuredLogger(
    agent="bronze_ingestion",
    workload="claims_v2",
    run_id="standalone",
)




def ingest(glue_context, args):
    spark = glue_context.spark_session
    source_path = "s3://prod-data-lake/raw/healthcare/claims/"
    landing_zone = "s3://data-lake/claims_v2/bronze/"

    # A bare or relative path resolves against the Glue executor's own filesystem, not the
    # repository the spec was written in, so the read fails with an opaque "Path does not
    # exist". Named here instead, because this cost a whole build: source_path was the bare
    # filename "sample_claims.csv" and nothing said why Spark could not find it.
    # This script runs on AWS Glue — it imports GlueContext and constructs one below, and
    # .claude/rules/03-python-airflow.md requires it. So the only source a worker can actually
    # reach is S3.
    #
    # The earlier version of this guard rejected a bare path and then invited the next defect
    # in its own message: "or file:///abs/path for a deliberate local run". There is no local
    # run. A live HIPAA workload took that invitation and shipped
    # file:///Users/<name>/.../sample_claims.csv in three files — unreachable from a Glue
    # worker, and carrying a home directory into source. The guard caught the shape it was
    # written for and waved through the one it suggested.
    if not source_path.startswith(("s3://", "s3a://")):
        raise ValueError(
            f"source_path {source_path!r} is not an S3 URI. This script runs on a Glue worker, "
            f"which cannot reach a relative path (it resolves against its own container, not "
            f"your repository) and cannot reach file:// (that is your workstation's disk, and "
            f"a path under a home directory also leaks a username into the spec). Stage the "
            f"data in S3 and use s3:// or s3a://."
        )

    logger.log("info", "ingestion_start", source=source_path, format="csv")

    df = spark.read.format("csv") \
        .option("header", "True") \
        .option("delimiter", ",") \
        .option("inferSchema", "false") \
        .load(source_path)

    input_rows = df.count()

    df.write.format("parquet") \
        .mode("append") \
        .save(landing_zone)

    logger.log("info", "ingestion_complete", input_rows=input_rows, target=landing_zone)

    return {
        "workload": "claims_v2",
        "operation": "bronze_ingestion",
        "source": source_path,
        "target": landing_zone,
        "rows_ingested": input_rows,
    }


if __name__ == "__main__":
    args = getResolvedOptions(sys.argv, ["JOB_NAME"])
    sc = SparkContext()
    glue_context = GlueContext(sc)
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)
    result = ingest(glue_context, args)
    job.commit()
