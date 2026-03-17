#!/usr/bin/env python3
"""
Bronze to Silver Transformation — AWS Glue ETL (PySpark + Iceberg)
Workload: product_inventory
Applies 10 cleaning rules to raw product inventory data.
Writes output as Apache Iceberg table on S3 Tables.

Lineage: Captured automatically by AWS Glue Data Lineage (--enable-data-lineage: true).
Execution: AWS Glue ETL job ONLY (PySpark runtime). No local fallback.
"""

import sys
from datetime import datetime, timezone

from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.dynamicframe import DynamicFrame
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType,
    DoubleType, DateType, BooleanType, TimestampType
)

# ── Configuration ──
JOB_NAME = "product_inventory_bronze_to_silver"
WORKLOAD = "product_inventory"
SOURCE_DATABASE = "demo_ai_agents"
SOURCE_TABLE = "bronze_product_inventory"
TARGET_DATABASE = "demo_ai_agents"
TARGET_TABLE = "silver_product_inventory"
QUARANTINE_TABLE = "quarantine_product_inventory"

# KMS keys (referenced by alias, never raw key material)
BRONZE_KMS_KEY = "alias/bronze-data-key"
SILVER_KMS_KEY = "alias/silver-data-key"


class BronzeToSilverGlueETL:
    """Glue ETL job: Bronze -> Silver with 10 cleaning rules.

    Lineage is captured automatically by Glue Data Lineage when the job
    parameter --enable-data-lineage is set to true. Every read/write uses
    transformation_ctx for accurate lineage tracking.
    """

    def __init__(self, glue_context, spark, job_run_id):
        self.glue_context = glue_context
        self.spark = spark
        self.job_run_id = job_run_id
        self.logger = glue_context.get_logger()
        self.stats = {}

    def run(self, input_df):
        """Execute all transformation steps on a Spark DataFrame."""
        self.logger.info(f"Starting Bronze -> Silver transformation: {self.job_run_id}")
        initial_count = input_df.count()
        self.stats["initial_count"] = initial_count
        self.logger.info(f"Loaded {initial_count} records from Bronze zone")

        # Apply transformations in order
        df = input_df
        df = self._step_01_deduplicate(df)
        df, q1 = self._step_02_quarantine_negative_quantities(df)
        df, q2 = self._step_03_quarantine_future_dates(df)
        df = self._step_04_normalize_category(df)
        df = self._step_05_trim_product_name(df)
        df = self._step_06_fix_invalid_status(df)
        df = self._step_07_flag_missing_supplier(df)
        df = self._step_08_flag_margin_anomaly(df)
        df = self._step_09_flag_missing_expiry(df)
        df = self._step_10_fill_missing_reorder(df)

        # Add processing metadata
        df = df.withColumn("processing_timestamp", F.current_timestamp())
        df = df.withColumn("job_run_id", F.lit(self.job_run_id))

        # Calculate data quality score
        df = self._calculate_quality_score(df)

        final_count = df.count()
        self.stats["final_count"] = final_count
        quarantine_count = self.stats.get("negative_quantities_quarantined", 0) + self.stats.get("future_dates_quarantined", 0)

        self.logger.info("=" * 60)
        self.logger.info("Bronze -> Silver Transformation Complete")
        self.logger.info(f"Input: {initial_count} | Output: {final_count} | Quarantined: {quarantine_count}")
        self.logger.info("=" * 60)

        return df

    # ── Transformation Steps ──

    def _step_01_deduplicate(self, df):
        """Remove duplicate rows based on product_id + sku, keep first."""
        before = df.count()
        df = df.dropDuplicates(["product_id", "sku"])
        after = df.count()
        removed = before - after
        self.stats["duplicates_removed"] = removed
        self.logger.info(f"Step 1: Removed {removed} duplicate records")
        return df

    def _step_02_quarantine_negative_quantities(self, df):
        """Quarantine records with negative quantity_on_hand."""
        quarantined = df.filter(F.col("quantity_on_hand") < 0)
        q_count = quarantined.count()
        clean = df.filter(F.col("quantity_on_hand") >= 0)
        self.stats["negative_quantities_quarantined"] = q_count
        self.logger.info(f"Step 2: Quarantined {q_count} records with negative quantities")
        return clean, quarantined

    def _step_03_quarantine_future_dates(self, df):
        """Quarantine records with last_restocked_date in the future."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        quarantined = df.filter(F.col("last_restocked_date") > F.lit(today))
        q_count = quarantined.count()
        clean = df.filter(
            (F.col("last_restocked_date") <= F.lit(today)) | F.col("last_restocked_date").isNull()
        )
        self.stats["future_dates_quarantined"] = q_count
        self.logger.info(f"Step 3: Quarantined {q_count} records with future restock dates")
        return clean, quarantined

    def _step_04_normalize_category(self, df):
        """Standardize category names to title case."""
        df = df.withColumn("category", F.initcap(F.trim(F.col("category"))))
        self.logger.info("Step 4: Normalized category casing")
        return df

    def _step_05_trim_product_name(self, df):
        """Remove leading and trailing whitespace from product_name."""
        df = df.withColumn("product_name", F.trim(F.col("product_name")))
        self.logger.info("Step 5: Trimmed whitespace from product_name")
        return df

    def _step_06_fix_invalid_status(self, df):
        """Map invalid status 'aktive' to 'active'."""
        df = df.withColumn(
            "status",
            F.when(F.lower(F.col("status")) == "aktive", F.lit("active")).otherwise(F.col("status"))
        )
        self.logger.info("Step 6: Fixed invalid status values")
        return df

    def _step_07_flag_missing_supplier(self, df):
        """Flag records with missing supplier_id or supplier_name."""
        df = df.withColumn(
            "is_supplier_missing",
            F.col("supplier_id").isNull() | F.col("supplier_name").isNull()
        )
        df = df.withColumn(
            "supplier_name",
            F.when(F.col("supplier_name").isNull(), F.lit("Unknown Supplier")).otherwise(F.col("supplier_name"))
        )
        flagged = df.filter(F.col("is_supplier_missing")).count()
        self.stats["supplier_missing_flagged"] = flagged
        self.logger.info(f"Step 7: Flagged {flagged} records with missing supplier")
        return df

    def _step_08_flag_margin_anomaly(self, df):
        """Flag records where cost_price exceeds unit_price."""
        df = df.withColumn(
            "is_margin_anomaly",
            F.col("cost_price") > F.col("unit_price")
        )
        flagged = df.filter(F.col("is_margin_anomaly")).count()
        self.stats["margin_anomaly_flagged"] = flagged
        self.logger.info(f"Step 8: Flagged {flagged} records with margin anomaly")
        return df

    def _step_09_flag_missing_expiry(self, df):
        """Flag Grocery items with missing expiry_date."""
        df = df.withColumn(
            "is_expiry_missing",
            (F.col("category") == "Grocery") & F.col("expiry_date").isNull()
        )
        flagged = df.filter(F.col("is_expiry_missing")).count()
        self.stats["expiry_missing_flagged"] = flagged
        self.logger.info(f"Step 9: Flagged {flagged} Grocery items with missing expiry_date")
        return df

    def _step_10_fill_missing_reorder(self, df):
        """Set missing reorder_level to 0 and flag."""
        df = df.withColumn(
            "is_reorder_missing",
            F.col("reorder_level").isNull()
        )
        df = df.withColumn(
            "reorder_level",
            F.when(F.col("reorder_level").isNull(), F.lit(0)).otherwise(F.col("reorder_level"))
        )
        flagged = df.filter(F.col("is_reorder_missing")).count()
        self.stats["reorder_missing_filled"] = flagged
        self.logger.info(f"Step 10: Filled {flagged} missing reorder_level values")
        return df

    def _calculate_quality_score(self, df):
        """Compute per-row data quality score based on flags."""
        df = df.withColumn("data_quality_score", F.lit(1.0))
        df = df.withColumn(
            "data_quality_score",
            F.col("data_quality_score")
            - F.when(F.col("is_supplier_missing"), 0.1).otherwise(0.0)
            - F.when(F.col("is_margin_anomaly"), 0.2).otherwise(0.0)
            - F.when(F.col("is_expiry_missing"), 0.1).otherwise(0.0)
            - F.when(F.col("is_reorder_missing"), 0.05).otherwise(0.0)
        )
        return df


# ═══════════════════════════════════════════════════════════
# Glue ETL entry point
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    args = getResolvedOptions(sys.argv, [
        "JOB_NAME",
        "source_database",
        "source_table",
        "target_s3_path",
        "quarantine_s3_path",
    ])

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    # Configure Iceberg catalog
    spark.conf.set("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog")
    spark.conf.set("spark.sql.catalog.glue_catalog.warehouse", args["target_s3_path"])
    spark.conf.set("spark.sql.catalog.glue_catalog.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog")
    spark.conf.set("spark.sql.catalog.glue_catalog.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")

    # Read Bronze data from Glue Catalog (transformation_ctx required for lineage)
    bronze_dyf = glue_context.create_dynamic_frame.from_catalog(
        database=args["source_database"],
        table_name=args["source_table"],
        transformation_ctx="bronze_source",
    )
    bronze_df = bronze_dyf.toDF()

    # Run transformation
    job_run_id = args.get("JOB_RUN_ID", f"glue-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}")
    etl = BronzeToSilverGlueETL(glue_context, spark, job_run_id)
    silver_df = etl.run(bronze_df)

    # Write Silver as Iceberg table via Glue Catalog (transformation_ctx for lineage)
    silver_dyf = DynamicFrame.fromDF(silver_df, glue_context, "silver_output")
    glue_context.write_dynamic_frame.from_catalog(
        frame=silver_dyf,
        database=TARGET_DATABASE,
        table_name=TARGET_TABLE,
        transformation_ctx="silver_target",
        additional_options={"enableUpdateCatalog": True, "updateBehavior": "UPDATE_IN_DATABASE"},
    )

    glue_context.get_logger().info(f"Wrote Silver Iceberg table: {TARGET_DATABASE}.{TARGET_TABLE}")
    job.commit()
