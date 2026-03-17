#!/usr/bin/env python3
"""
Silver to Gold Transformation — AWS Glue ETL (PySpark + Iceberg)
Workload: product_inventory
Creates star schema: fact_inventory + dim_product + dim_supplier + dim_warehouse
Writes output as Apache Iceberg tables.

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
from pyspark.sql import Window

# ── Configuration ──
JOB_NAME = "product_inventory_silver_to_gold"
WORKLOAD = "product_inventory"
SOURCE_DATABASE = "demo_ai_agents"
SOURCE_TABLE = "silver_product_inventory"
TARGET_DATABASE = "demo_ai_agents"
GOLD_TABLES = {
    "fact": "gold_fact_inventory",
    "dim_product": "gold_dim_product",
    "dim_supplier": "gold_dim_supplier",
    "dim_warehouse": "gold_dim_warehouse",
}

SILVER_KMS_KEY = "alias/silver-data-key"
GOLD_KMS_KEY = "alias/gold-data-key"


class SilverToGoldGlueETL:
    """Glue ETL job: Silver -> Gold star schema.

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

    def run(self, silver_df):
        """Execute star schema creation from Silver Spark DataFrame."""
        self.logger.info(f"Starting Silver -> Gold transformation: {self.job_run_id}")
        initial_count = silver_df.count()
        self.stats["silver_records"] = initial_count
        self.logger.info(f"Loaded {initial_count} records from Silver zone")

        # Create dimension tables
        dim_product = self._create_dim_product(silver_df)
        dim_supplier = self._create_dim_supplier(silver_df)
        dim_warehouse = self._create_dim_warehouse(silver_df)

        # Create fact table
        fact_inventory = self._create_fact_inventory(silver_df, dim_product, dim_supplier, dim_warehouse)

        self.logger.info("=" * 60)
        self.logger.info("Silver -> Gold Star Schema Created")
        for key, value in self.stats.items():
            self.logger.info(f"  {key}: {value}")
        self.logger.info("=" * 60)

        return {
            "fact_inventory": fact_inventory,
            "dim_product": dim_product,
            "dim_supplier": dim_supplier,
            "dim_warehouse": dim_warehouse,
        }

    # ── Dimension Builders (PySpark) ──

    def _create_dim_product(self, df):
        self.logger.info("Creating dim_product...")
        dim = df.select("product_id", "sku", "product_name", "category", "subcategory", "brand", "status") \
                 .dropDuplicates(["product_id"])
        w = Window.orderBy("product_id")
        dim = dim.withColumn("product_key", F.row_number().over(w))
        dim = dim.select("product_key", "product_id", "sku", "product_name", "category", "subcategory", "brand", "status")
        count = dim.count()
        self.stats["dim_product_rows"] = count
        self.logger.info(f"Created dim_product with {count} rows")
        return dim

    def _create_dim_supplier(self, df):
        self.logger.info("Creating dim_supplier...")
        dim = df.select("supplier_id", "supplier_name") \
                 .dropDuplicates(["supplier_id"]) \
                 .filter(F.col("supplier_id").isNotNull())
        w = Window.orderBy("supplier_id")
        dim = dim.withColumn("supplier_key", F.row_number().over(w))
        dim = dim.select("supplier_key", "supplier_id", "supplier_name")
        count = dim.count()
        self.stats["dim_supplier_rows"] = count
        self.logger.info(f"Created dim_supplier with {count} rows")
        return dim

    def _create_dim_warehouse(self, df):
        self.logger.info("Creating dim_warehouse...")
        dim = df.select("warehouse_location").dropDuplicates()
        dim = dim.withColumn("region", F.when(F.upper(F.col("warehouse_location")).contains("EAST"), "EAST")
                                       .when(F.upper(F.col("warehouse_location")).contains("WEST"), "WEST")
                                       .when(F.upper(F.col("warehouse_location")).contains("CENTRAL"), "CENTRAL")
                                       .otherwise("UNKNOWN"))
        w = Window.orderBy("warehouse_location")
        dim = dim.withColumn("warehouse_key", F.row_number().over(w))
        dim = dim.select("warehouse_key", "warehouse_location", "region")
        count = dim.count()
        self.stats["dim_warehouse_rows"] = count
        self.logger.info(f"Created dim_warehouse with {count} rows")
        return dim

    def _create_fact_inventory(self, silver_df, dim_product, dim_supplier, dim_warehouse):
        self.logger.info("Creating fact_inventory...")
        fact = silver_df.join(dim_product.select("product_key", "product_id"), "product_id", "left")
        fact = fact.join(dim_supplier.select("supplier_key", "supplier_id"), "supplier_id", "left")
        fact = fact.join(dim_warehouse.select("warehouse_key", "warehouse_location"), "warehouse_location", "left")

        fact = fact.withColumn("margin", F.col("unit_price") - F.col("cost_price"))
        fact = fact.withColumn("margin_pct",
            F.when(F.col("unit_price") > 0, (F.col("margin") / F.col("unit_price")) * 100).otherwise(0))
        fact = fact.withColumn("inventory_value", F.col("unit_price") * F.col("quantity_on_hand"))
        fact = fact.withColumn("needs_reorder", F.col("quantity_on_hand") <= F.col("reorder_level"))

        fact = fact.select(
            "product_key", "supplier_key", "warehouse_key",
            "unit_price", "cost_price", "margin", "margin_pct",
            "quantity_on_hand", "reorder_level", "reorder_quantity",
            "weight_kg", "inventory_value", "needs_reorder"
        )
        count = fact.count()
        self.stats["fact_inventory_rows"] = count
        self.logger.info(f"Created fact_inventory with {count} rows")
        return fact


# ═══════════════════════════════════════════════════════════
# Glue ETL entry point
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    args = getResolvedOptions(sys.argv, [
        "JOB_NAME",
        "source_database",
        "source_table",
        "target_s3_path",
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

    # Read Silver Iceberg table from Glue Catalog (transformation_ctx for lineage)
    silver_dyf = glue_context.create_dynamic_frame.from_catalog(
        database=args["source_database"],
        table_name=args["source_table"],
        transformation_ctx="silver_source",
    )
    silver_df = silver_dyf.toDF()

    # Run transformation
    job_run_id = args.get("JOB_RUN_ID", f"glue-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}")
    etl = SilverToGoldGlueETL(glue_context, spark, job_run_id)
    tables = etl.run(silver_df)

    # Write Gold Iceberg tables via Glue Catalog (transformation_ctx for lineage)
    table_map = {
        "fact_inventory": GOLD_TABLES["fact"],
        "dim_product": GOLD_TABLES["dim_product"],
        "dim_supplier": GOLD_TABLES["dim_supplier"],
        "dim_warehouse": GOLD_TABLES["dim_warehouse"],
    }
    for df_key, catalog_table in table_map.items():
        gold_df = tables[df_key]
        gold_dyf = DynamicFrame.fromDF(gold_df, glue_context, f"gold_{df_key}")
        glue_context.write_dynamic_frame.from_catalog(
            frame=gold_dyf,
            database=TARGET_DATABASE,
            table_name=catalog_table,
            transformation_ctx=f"gold_target_{df_key}",
            additional_options={"enableUpdateCatalog": True, "updateBehavior": "UPDATE_IN_DATABASE"},
        )
        glue_context.get_logger().info(f"Wrote Gold Iceberg table: {TARGET_DATABASE}.{catalog_table}")

    job.commit()
