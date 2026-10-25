# spec_hash: f22e8e282cc1434dd007fe07f5a298de226d768039ed4e8b041b172731cc45cd
# template_id: gold_aggregate
# template_hash: 446296e7eb03da93afb22e05f4a8be2590dac32bf0315f833ff159760dc4b55f
# schema_version: v2
# rendered_at: 2026-10-22T18:18:44Z
import os
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
from shared.utils.pii_detection_and_tagging import detect_pii_by_column_name

logger = StructuredLogger(
    agent="gold_aggregate",
    workload="customer_orders",
    run_id="local",
)


def _configure_logger(args):
    """Use Airflow's ADOP_RUN_ID while keeping direct local calls testable."""
    logger.context["run_id"] = (
        args.get("ADOP_RUN_ID") or os.environ.get("ADOP_RUN_ID") or "local"
    )


def _log_pii_inventory(df):
    """Log column metadata only; detection never reads values or changes the dataframe."""
    inventory = {}
    for column_name in df.columns:
        detected = detect_pii_by_column_name(column_name)
        if detected:
            inventory[column_name] = [
                {"pii_type": pii_type, "sensitivity": sensitivity}
                for pii_type, sensitivity in detected
            ]
    logger.log(
        "info",
        "pii_inventory_detected",
        detected_columns=inventory,
        detected_column_count=len(inventory),
    )


def aggregate(glue_context, args):
    _configure_logger(args)
    spark = glue_context.spark_session
    logger.log("info", "gold_transform_start", source="glue_catalog.customer_orders_db.silver_customer_orders", schema_type="flat_iceberg")

    silver_df = spark.table("glue_catalog.customer_orders_db.silver_customer_orders")
    input_rows = silver_df.count()

    pre_agg_df = silver_df

    # Flat Iceberg: denormalized table with all measures
    gold_df = pre_agg_df.groupBy(
        "order_id",
    ).agg(
        F.count("order_id").alias("order_count"),
        F.sum("revenue").alias("revenue"),
        F.first("customer_id", ignorenulls=True).alias("customer_id"),
        F.first("product_id", ignorenulls=True).alias("product_id"),
        F.first("order_date", ignorenulls=True).alias("order_date"),
        F.first("ship_date", ignorenulls=True).alias("ship_date"),
        F.first("quantity", ignorenulls=True).alias("quantity"),
        F.first("unit_price", ignorenulls=True).alias("unit_price"),
        F.first("discount_pct", ignorenulls=True).alias("discount_pct"),
        F.first("payment_method", ignorenulls=True).alias("payment_method"),
        F.first("order_status", ignorenulls=True).alias("order_status"),
        F.first("data_subject_id", ignorenulls=True).alias("data_subject_id"),
        F.first("consent_given", ignorenulls=True).alias("consent_given"),
        F.first("consent_timestamp", ignorenulls=True).alias("consent_timestamp"),
        F.first("is_deleted", ignorenulls=True).alias("is_deleted"),
        F.first("deletion_requested_at", ignorenulls=True).alias("deletion_requested_at"),
    )


    table_name = "glue_catalog.customer_orders_db.gold_customer_orders"
    _log_pii_inventory(gold_df)
    gold_df.writeTo(table_name).using("iceberg").createOrReplace()
    output_rows = gold_df.count()

    logger.log("info", "gold_transform_complete",
        input_rows=input_rows, output_rows=output_rows, target_table=table_name)

    return {
        "workload": "customer_orders",
        "transformation": "silver_to_gold",
        "source": "glue_catalog.customer_orders_db.silver_customer_orders",
        "target": table_name,
        "input_rows": input_rows,
        "output_rows": output_rows,
    }


if __name__ == "__main__":
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "ADOP_RUN_ID"])
    sc = SparkContext()
    glue_context = GlueContext(sc)
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)
    result = aggregate(glue_context, args)
    job.commit()
