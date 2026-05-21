# spec_hash: 1ba019f45bf4d074fa80ba9f997c59d25c7ced83b79629d423b290ac31ef2332
# template_id: bronze_ingestion
# template_hash: 6fe16c5b7900c3f546aa941cb585690e2ee1f45bdf8abbc7d52022237494af61
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
    source_path = args.get("source_path", "s3://prod-data-lake/raw/healthcare/claims/")
    landing_zone = args.get("landing_zone", "s3://data-lake/claims_v2/bronze/")

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
