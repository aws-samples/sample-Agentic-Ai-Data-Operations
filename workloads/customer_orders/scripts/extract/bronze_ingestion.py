# spec_hash: 5a21ed46e316a70382e9981292ad9f5dcdba1775a3310b116fcdccbaaf8788c7
# template_id: bronze_ingestion
# template_hash: 42d1e36ed8a013289c6fc574ac7043df2c08d45d9062f937f218f5c7bde9a858
# schema_version: v2
# rendered_at: 2026-10-22T18:18:44Z
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.pii_detection_and_tagging import detect_pii_by_column_name
from shared.utils.structured_logger import StructuredLogger

logger = StructuredLogger(
    agent="bronze_ingestion",
    workload="customer_orders",
    run_id="local",
)


def _configure_logger(args):
    """Use Airflow's ADOP_RUN_ID while keeping direct local calls testable."""
    logger.context["run_id"] = (
        args.get("ADOP_RUN_ID") or os.environ.get("ADOP_RUN_ID") or "local"
    )




def _resolve(value, args, slot):
    """Substitute ${NAME} job arguments, and refuse to proceed if any survive."""
    for name in ("CUSTOMER_ORDERS_SOURCE_URI", "DATA_LAKE_BUCKET", ):
        value = value.replace("${" + name + "}", args[name])
    if "${" in value:
        raise ValueError(
            f"{slot} still holds an unresolved placeholder after substitution: {value!r}. "
            f"Pass it as a Glue job argument -- writing it literally would create a path "
            f"named after the placeholder rather than the bucket."
        )
    return value


# S3 bucket naming rules: 3-63 chars, lowercase letters, digits, dots and hyphens, starting
# and ending with a letter or digit.
_S3_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


def _require_s3_uri(uri, slot):
    """Refuse anything but a well-formed S3 URI once job arguments are substituted.

    A prefix check alone accepts "s3://\nfile:///etc/passwd" or "s3://../x": the value
    comes from a Glue job argument, so its shape is only known at runtime.
    """
    if any(ch in uri for ch in "\r\n\t\0"):
        raise ValueError(f"{slot} contains control characters; refusing to read or write it.")
    parsed = urlparse(uri)
    if parsed.scheme not in ("s3", "s3a") or not _S3_BUCKET.match(parsed.netloc):
        raise ValueError(f"{slot} must be s3://<valid-bucket>/<key>, got {uri!r}.")
    if ".." in parsed.path.split("/"):
        raise ValueError(f"{slot} contains a '..' path segment: {uri!r}.")
    return uri


def ingest(glue_context, args):
    _configure_logger(args)
    spark = glue_context.spark_session
    source_path = _resolve("${CUSTOMER_ORDERS_SOURCE_URI}", args, "source_path")
    landing_zone = _resolve("s3://${DATA_LAKE_BUCKET}/bronze/customer_orders/", args, "landing_zone")

    # A bare or relative path resolves against the Glue executor's own filesystem, not the
    # repository the spec was written in, so the read fails with an opaque "Path does not
    # exist". Named here instead, because this cost a whole build: source_path was the bare
    # filename "sample_claims.csv" and nothing said why Spark could not find it.
    # This script runs on AWS Glue — it imports GlueContext and constructs one below, and
    # The pipeline-conventions Codex skill requires it. So the only source a worker can actually
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
    _require_s3_uri(source_path, "source_path")
    _require_s3_uri(landing_zone, "landing_zone")

    logger.log("info", "ingestion_start", source=source_path, format="csv")

    df = spark.read.format("csv") \
        .option("header", "True") \
        .option("delimiter", ",") \
        .option("inferSchema", "false") \
        .load(source_path)

    input_rows = df.count()
    pii_inventory = {
        column: detect_pii_by_column_name(column)
        for column in df.columns
        if detect_pii_by_column_name(column)
    }
    logger.log("info", "pii_inventory_detected", columns=pii_inventory)

    # Bronze is raw and immutable at the row level: no order_id deduplication, filtering, or
    # updates are performed. The source path is the declared logical-run identity for this
    # full-load source. A retry of that same logical run replaces only its partition, while a
    # different source path appends a new immutable partition.
    if "_adop_source_run_id" in df.columns:
        raise ValueError(
            "The reserved Bronze metadata column '_adop_source_run_id' is present in the "
            "source schema; refusing to overwrite source data."
        )
    df = df.withColumn(
        "_adop_source_run_id",
        F.sha2(F.lit(source_path), 256),
    )
    table_name = "glue_catalog.customer_orders_db.bronze_customer_orders"
    logger.log(
        "info",
        "bronze_catalog_target",
        table=table_name,
        declared_landing_zone=landing_zone,
        idempotency_key="source_path",
    )
    if spark.catalog.tableExists(table_name):
        df.writeTo(table_name).using("iceberg").overwritePartitions()
    else:
        (
            df.writeTo(table_name)
            .using("iceberg")
            .partitionedBy(F.col("_adop_source_run_id"))
            .create()
        )
    target = table_name

    logger.log("info", "ingestion_complete", input_rows=input_rows, target=target)

    return {
        "workload": "customer_orders",
        "operation": "bronze_ingestion",
        "source": source_path,
        "target": target,
        "rows_ingested": input_rows,
    }


if __name__ == "__main__":
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "ADOP_RUN_ID", "CUSTOMER_ORDERS_SOURCE_URI", "DATA_LAKE_BUCKET"])
    sc = SparkContext()
    glue_context = GlueContext(sc)
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)
    result = ingest(glue_context, args)
    job.commit()
