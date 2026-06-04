# spec_hash: 567a3af743016510400d1485d651649670991023857a83daf0edd87ba9c45e5f
# template_id: silver_transform
# template_hash: 270b6c620017cf1f7d46bc7032e845e1775a1a43f588767631c3df9bd48f2f6c
# schema_version: v1
# rendered_at: 2026-05-21T06:00:00Z
import sys
import hashlib
from datetime import datetime
from pathlib import Path

from pyspark.sql import functions as F
from pyspark.sql.window import Window
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.structured_logger import StructuredLogger

logger = StructuredLogger(
    agent="silver_transform",
    workload="claims_v2",
    run_id="standalone",
)


def transform(glue_context, args):
    spark = glue_context.spark_session
    logger.log("info", "transform_start", source="glue_catalog.claims_v2_db.bronze_claims_v2")

    bronze_df = spark.table("glue_catalog.claims_v2_db.bronze_claims_v2")
    input_rows = bronze_df.count()
    logger.log("info", "input_count", rows=input_rows)

    # Drop rows with null primary key columns
    bronze_df = bronze_df.filter(F.col("claim_id").isNotNull())
    after_pk_filter = bronze_df.count()

    # Deduplication: keep_latest
    window = Window.partitionBy(
        "claim_id",
    ).orderBy(F.desc("submission_date"))
    deduped_df = bronze_df \
        .withColumn("_row_num", F.row_number().over(window)) \
        .filter(F.col("_row_num") == 1) \
        .drop("_row_num")
    dedup_rows = deduped_df.count()

    # Type casting
    typed_df = deduped_df
    typed_df = typed_df.withColumn(
        "billed_amount",
        F.col("billed_amount").cast("decimal(10,2)")
    )
    typed_df = typed_df.withColumn(
        "allowed_amount",
        F.col("allowed_amount").cast("decimal(10,2)")
    )
    typed_df = typed_df.withColumn(
        "paid_amount",
        F.col("paid_amount").cast("decimal(10,2)")
    )
    typed_df = typed_df.withColumn(
        "patient_responsibility",
        F.col("patient_responsibility").cast("decimal(10,2)")
    )
    typed_df = typed_df.withColumn(
        "service_date",
        F.to_date(F.col("service_date"), "yyyy-MM-dd")
    )
    typed_df = typed_df.withColumn(
        "submission_date",
        F.to_date(F.col("submission_date"), "yyyy-MM-dd")
    )
    typed_df = typed_df.withColumn(
        "member_dob",
        F.to_date(F.col("member_dob"), "yyyy-MM-dd")
    )

    pre_pii_df = typed_df

    # PII masking
    masked_df = pre_pii_df
    masked_df = masked_df.withColumn(
        "member_ssn",
        F.sha2(F.col("member_ssn").cast("string"), 256)
    )
    masked_df = masked_df.withColumn(
        "member_dob",
        F.sha2(F.col("member_dob").cast("string"), 256)
    )
    masked_df = masked_df.withColumn(
        "member_email",
        F.sha2(F.col("member_email").cast("string"), 256)
    )

    derived_df = masked_df

    final_df = derived_df

    # Write to Iceberg Silver table
    table_name = "glue_catalog.claims_v2_db.silver_claims_v2"
    final_df.writeTo(table_name) \
        .using("iceberg") \
        .createOrReplace()

    output_rows = final_df.count()
    logger.log("info", "transform_complete",
        input_rows=input_rows,
        pk_null_dropped=input_rows - after_pk_filter,
        duplicates_removed=after_pk_filter - dedup_rows,
        output_rows=output_rows,
        target_table=table_name,
        quality_threshold=0.8)

    return {
        "workload": "claims_v2",
        "transformation": "bronze_to_silver",
        "source": "glue_catalog.claims_v2_db.bronze_claims_v2",
        "target": table_name,
        "input_rows": input_rows,
        "output_rows": output_rows,
    }


if __name__ == "__main__":
    args = getResolvedOptions(sys.argv, ["JOB_NAME"])
    sc = SparkContext()
    glue_context = GlueContext(sc)
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)
    result = transform(glue_context, args)
    job.commit()
