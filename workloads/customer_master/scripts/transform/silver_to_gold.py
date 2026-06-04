# spec_hash: 1a2903ba83ae1746f33afa67e2f07ae716e1effd04efcf38b030ff4fabe8770f
# template_id: gold_aggregate
# template_hash: 35ee80935d120bc92d3951a7149c24651178ed5e5ff9fd1006f3476141133e34
# schema_version: v1
# rendered_at: 2026-06-03T00:00:00Z
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
    agent="gold_aggregate",
    workload="customer_master",
    run_id="standalone",
)


def aggregate(glue_context, args):
    spark = glue_context.spark_session
    logger.log("info", "gold_transform_start", source="glue_catalog.customer_master_db.silver_customer_master", schema_type="star_schema")

    silver_df = spark.table("glue_catalog.customer_master_db.silver_customer_master")
    input_rows = silver_df.count()

    # Pre-aggregation derived columns (computed on Silver before groupBy)
    pre_agg_df = silver_df
    pre_agg_df = pre_agg_df.withColumn(
        "email_masked",
        F.expr("concat(\u0027***@\u0027, email_domain)")
    )

    # Star schema: build fact table with aggregated measures
    fact_df = pre_agg_df.groupBy(
        "customer_id",
    ).agg(
        F.count("customer_id").alias("customer_count"),
        F.avg("credit_score").alias("avg_credit_score"),
        F.avg("annual_income").alias("avg_annual_income"),
        F.avg("customer_tenure_months").alias("avg_tenure_months"),
    )


    table_name = "glue_catalog.customer_master_db.dim_customer"
    fact_df.writeTo(table_name).using("iceberg").createOrReplace()
    output_rows = fact_df.count()


    logger.log("info", "gold_transform_complete",
        input_rows=input_rows, output_rows=output_rows, target_table=table_name)

    return {
        "workload": "customer_master",
        "transformation": "silver_to_gold",
        "source": "glue_catalog.customer_master_db.silver_customer_master",
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
