# spec_hash: e12dafbd6668baa28ec6772798bb88fbc33d859b3d370ae9bd1557463d08b6c9
# template_id: gold_aggregate
# template_hash: d353a6119751f96f58aae8eaeb55c4216a4487219393c64bdc8c1e037f03b485
# schema_version: v1
# rendered_at: 2026-05-21T06:00:00Z
import sys
from datetime import datetime
from pathlib import Path

from pyspark.sql import functions as F
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.structured_logger import StructuredLogger

logger = StructuredLogger(
    workload="claims_v2",
    script="silver_to_gold",
)


def aggregate(glue_context, args):
    spark = glue_context.spark_session
    logger.log_event("gold_transform_start", {
        "source": "glue_catalog.claims_v2_db.silver_claims_v2",
        "schema_type": "flat_iceberg",
    })

    silver_df = spark.table("glue_catalog.claims_v2_db.silver_claims_v2")
    input_rows = silver_df.count()

    # Flat Iceberg: denormalized table with all measures
    gold_df = silver_df.groupBy(
        "claim_type",
        "payer_name",
    ).agg(
        F.sum("billed_amount").alias("total_billed"),
        F.sum("paid_amount").alias("total_paid"),
        F.sum("allowed_amount").alias("total_allowed"),
        F.sum("patient_responsibility").alias("total_patient_responsibility"),
        F.count("claim_id").alias("claim_count"),
        F.avg("billed_amount").alias("avg_billed"),
        F.count("claim_id").alias("denied_count"),
    )

    table_name = "glue_catalog.claims_v2_db.gold_claims_v2"
    gold_df.writeTo(table_name).using("iceberg").createOrReplace()
    output_rows = gold_df.count()

    logger.log_event("gold_transform_complete", {
        "input_rows": input_rows,
        "output_rows": output_rows,
        "target_table": table_name,
        "quality_threshold": 0.95,
    })

    return {
        "workload": "claims_v2",
        "transformation": "silver_to_gold",
        "source": "glue_catalog.claims_v2_db.silver_claims_v2",
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
    result = aggregate(glue_context, args)
    job.commit()
