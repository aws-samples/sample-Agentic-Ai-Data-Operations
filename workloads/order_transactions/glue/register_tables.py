"""
Register order_transactions tables in AWS Glue Data Catalog.

Creates:
- Bronze database: demo_database_ai_agents_bronze (if not exists)
- Gold database: demo_database_ai_agents_goldzone (if not exists)
- Bronze table: orders
- Gold tables: order_fact, dim_product, dim_region, dim_status, order_summary
"""

import os
import logging
import json

logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_BUCKET = os.environ.get("S3_BUCKET", "aws-glue-assets-123456789012-us-east-1")
BRONZE_DB = "demo_database_ai_agents_bronze"
GOLD_DB = "demo_database_ai_agents_goldzone"
BRONZE_PREFIX = "demo-ai-agents/bronze/orders/"
GOLD_PREFIX = "demo-ai-agents/gold/orders/"


def _get_glue_client():
    """Get Glue client."""
    import boto3
    return boto3.client("glue", region_name=REGION)


def create_databases(glue_client=None) -> dict:
    """Create Bronze and Gold databases if they don't exist."""
    client = glue_client or _get_glue_client()
    results = {}

    for db_name, desc in [
        (BRONZE_DB, "Bronze zone - raw ingested data for AI agents demo"),
        (GOLD_DB, "Gold zone - curated star schema for AI agents demo"),
    ]:
        try:
            client.create_database(
                DatabaseInput={"Name": db_name, "Description": desc}
            )
            results[db_name] = "created"
            logger.info("Created database: %s", db_name)
        except client.exceptions.AlreadyExistsException:
            results[db_name] = "already_exists"
            logger.info("Database already exists: %s", db_name)

    return results


def _csv_serde_info():
    """Return CSV SerDe configuration for Glue table."""
    return {
        "SerializationLibrary": "org.apache.hadoop.hive.serde2.OpenCSVSerde",
        "Parameters": {
            "separatorChar": ",",
            "quoteChar": "\"",
            "escapeChar": "\\",
        },
    }


def _csv_input_format():
    return "org.apache.hadoop.mapred.TextInputFormat"


def _csv_output_format():
    return "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"


def register_bronze_table(glue_client=None) -> str:
    """Register orders table in Bronze database."""
    client = glue_client or _get_glue_client()
    location = f"s3://{S3_BUCKET}/{BRONZE_PREFIX}"

    columns = [
        {"Name": "order_id", "Type": "string", "Comment": "Unique order identifier (PK)"},
        {"Name": "customer_id", "Type": "string", "Comment": "Customer FK to customer_master"},
        {"Name": "order_date", "Type": "string", "Comment": "Order date YYYY-MM-DD"},
        {"Name": "product_name", "Type": "string", "Comment": "Product name"},
        {"Name": "category", "Type": "string", "Comment": "Product category"},
        {"Name": "quantity", "Type": "int", "Comment": "Units ordered"},
        {"Name": "unit_price", "Type": "double", "Comment": "Price per unit"},
        {"Name": "discount_pct", "Type": "double", "Comment": "Discount percentage"},
        {"Name": "revenue", "Type": "double", "Comment": "Order revenue"},
        {"Name": "status", "Type": "string", "Comment": "Order status"},
        {"Name": "region", "Type": "string", "Comment": "Sales region"},
    ]

    table_input = {
        "Name": "orders",
        "Description": "Raw order transactions - Bronze zone (immutable)",
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {
            "classification": "csv",
            "skip.header.line.count": "1",
            "has_encrypted_data": "false",
            "EXTERNAL": "TRUE",
        },
        "StorageDescriptor": {
            "Columns": columns,
            "Location": location,
            "InputFormat": _csv_input_format(),
            "OutputFormat": _csv_output_format(),
            "SerdeInfo": _csv_serde_info(),
            "Compressed": False,
        },
    }

    try:
        client.delete_table(DatabaseName=BRONZE_DB, Name="orders")
        logger.info("Deleted existing Bronze orders table for re-creation")
    except Exception:
        pass

    client.create_table(DatabaseName=BRONZE_DB, TableInput=table_input)
    logger.info("Registered Bronze table: %s.orders at %s", BRONZE_DB, location)
    return f"{BRONZE_DB}.orders"


def register_gold_tables(glue_client=None) -> list[str]:
    """Register all Gold zone tables."""
    client = glue_client or _get_glue_client()
    registered = []

    tables = [
        {
            "name": "order_fact",
            "description": "Order fact table - one row per validated order",
            "subfolder": "order_fact",
            "columns": [
                {"Name": "order_id", "Type": "string", "Comment": "PK - unique order ID"},
                {"Name": "customer_id", "Type": "string", "Comment": "FK to dim_customer"},
                {"Name": "order_date", "Type": "string", "Comment": "Order date"},
                {"Name": "product_id", "Type": "string", "Comment": "FK to dim_product"},
                {"Name": "region_id", "Type": "string", "Comment": "FK to dim_region"},
                {"Name": "status_id", "Type": "string", "Comment": "FK to dim_status"},
                {"Name": "status_name", "Type": "string", "Comment": "Denormalized status"},
                {"Name": "quantity", "Type": "int", "Comment": "Units ordered"},
                {"Name": "unit_price", "Type": "double", "Comment": "Price per unit"},
                {"Name": "discount_pct", "Type": "double", "Comment": "Discount pct"},
                {"Name": "revenue", "Type": "double", "Comment": "Order revenue"},
            ],
        },
        {
            "name": "dim_product",
            "description": "Product dimension - product name and category",
            "subfolder": "dim_product",
            "columns": [
                {"Name": "product_id", "Type": "string", "Comment": "Surrogate key"},
                {"Name": "product_name", "Type": "string", "Comment": "Product name"},
                {"Name": "category", "Type": "string", "Comment": "Product category"},
            ],
        },
        {
            "name": "dim_region",
            "description": "Region dimension - sales regions",
            "subfolder": "dim_region",
            "columns": [
                {"Name": "region_id", "Type": "string", "Comment": "Surrogate key"},
                {"Name": "region_name", "Type": "string", "Comment": "Region name"},
            ],
        },
        {
            "name": "dim_status",
            "description": "Status dimension - order statuses",
            "subfolder": "dim_status",
            "columns": [
                {"Name": "status_id", "Type": "string", "Comment": "Surrogate key"},
                {"Name": "status_name", "Type": "string", "Comment": "Status name"},
            ],
        },
        {
            "name": "order_summary",
            "description": "Pre-aggregated order metrics by region and category",
            "subfolder": "order_summary",
            "columns": [
                {"Name": "region", "Type": "string", "Comment": "Sales region"},
                {"Name": "category", "Type": "string", "Comment": "Product category"},
                {"Name": "total_revenue", "Type": "double", "Comment": "Sum of revenue"},
                {"Name": "total_quantity", "Type": "int", "Comment": "Sum of quantity"},
                {"Name": "order_count", "Type": "int", "Comment": "Count of orders"},
                {"Name": "avg_unit_price", "Type": "double", "Comment": "Average unit price"},
                {"Name": "avg_discount_pct", "Type": "double", "Comment": "Average discount pct"},
            ],
        },
    ]

    for tbl in tables:
        location = f"s3://{S3_BUCKET}/{GOLD_PREFIX}{tbl['subfolder']}/"
        table_input = {
            "Name": tbl["name"],
            "Description": tbl["description"],
            "TableType": "EXTERNAL_TABLE",
            "Parameters": {
                "classification": "csv",
                "skip.header.line.count": "1",
                "has_encrypted_data": "false",
                "EXTERNAL": "TRUE",
            },
            "StorageDescriptor": {
                "Columns": tbl["columns"],
                "Location": location,
                "InputFormat": _csv_input_format(),
                "OutputFormat": _csv_output_format(),
                "SerdeInfo": _csv_serde_info(),
                "Compressed": False,
            },
        }

        try:
            client.delete_table(DatabaseName=GOLD_DB, Name=tbl["name"])
        except Exception:
            pass

        client.create_table(DatabaseName=GOLD_DB, TableInput=table_input)
        full_name = f"{GOLD_DB}.{tbl['name']}"
        registered.append(full_name)
        logger.info("Registered Gold table: %s at %s", full_name, location)

    return registered


def register_all(glue_client=None) -> dict:
    """Register all databases and tables. Main entry point."""
    client = glue_client or _get_glue_client()
    db_results = create_databases(client)
    bronze_table = register_bronze_table(client)
    gold_tables = register_gold_tables(client)

    return {
        "databases": db_results,
        "bronze_table": bronze_table,
        "gold_tables": gold_tables,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = register_all()
    print(json.dumps(result, indent=2))
