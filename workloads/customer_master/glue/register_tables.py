"""
register_tables.py — Register Customer Master tables in AWS Glue Data Catalog.

Creates:
  - Glue databases: demo_database_ai_agents_bronze, demo_database_ai_agents_goldzone
  - Bronze table: customers (CSV external table)
  - Gold tables: customer_fact, dim_segment, dim_country, dim_status, customer_summary_by_segment

Idempotent: safe to run multiple times (deletes and recreates tables).
"""

import json
import logging
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_BUCKET = "aws-glue-assets-123456789012-us-east-1"
BRONZE_DB = "demo_database_ai_agents_bronze"
GOLD_DB = "demo_database_ai_agents_goldzone"
BRONZE_S3 = f"s3://{S3_BUCKET}/demo-ai-agents/bronze/customers"
GOLD_S3 = f"s3://{S3_BUCKET}/demo-ai-agents/gold/customers"


def run_aws_cli(args: List[str], ignore_errors: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run an AWS CLI command. Returns parsed JSON output or status."""
    cmd = ["aws"] + args + ["--region", REGION, "--output", "json"]
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        err = result.stderr.strip()
        if ignore_errors:
            for pattern in ignore_errors:
                if pattern in err:
                    logger.info("Ignored expected error: %s", pattern)
                    return {"status": "already_exists", "message": err}
        logger.error("AWS CLI error: %s", err)
        raise RuntimeError(f"AWS CLI failed: {err}")

    if result.stdout.strip():
        return json.loads(result.stdout)
    return {"status": "success"}


def create_databases() -> None:
    """Create Bronze and Gold databases if they don't exist."""
    for db_name, desc in [
        (BRONZE_DB, "Bronze zone - raw ingested data for AI agents demo"),
        (GOLD_DB, "Gold zone - curated star schema for AI agents demo"),
    ]:
        db_input = json.dumps({"Name": db_name, "Description": desc})
        run_aws_cli(
            ["glue", "create-database", "--database-input", db_input],
            ignore_errors=["AlreadyExistsException"],
        )
        logger.info("Database ensured: %s", db_name)


def delete_table_if_exists(database: str, table_name: str) -> None:
    """Delete a Glue table if it exists (for idempotent re-creation)."""
    run_aws_cli(
        ["glue", "delete-table", "--database-name", database, "--name", table_name],
        ignore_errors=["EntityNotFoundException"],
    )


def create_table(database: str, table_input: dict) -> None:
    """Create a Glue table."""
    table_name = table_input["Name"]
    delete_table_if_exists(database, table_name)
    run_aws_cli([
        "glue", "create-table",
        "--database-name", database,
        "--table-input", json.dumps(table_input),
    ])
    logger.info("Created table: %s.%s", database, table_name)


def register_bronze_tables() -> None:
    """Register Bronze zone customers table."""
    table_input = {
        "Name": "customers",
        "Description": "Raw customer master CSV from CRM system",
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {
            "classification": "csv",
            "skip.header.line.count": "1",
            "has_encrypted_data": "false",
            "EXTERNAL": "TRUE",
        },
        "StorageDescriptor": {
            "Columns": [
                {"Name": "customer_id", "Type": "string", "Comment": "Primary key CUST-NNN"},
                {"Name": "name", "Type": "string", "Comment": "Customer name (PII)"},
                {"Name": "email", "Type": "string", "Comment": "Email (PII)"},
                {"Name": "phone", "Type": "string", "Comment": "Phone (PII)"},
                {"Name": "segment", "Type": "string", "Comment": "Enterprise|SMB|Individual"},
                {"Name": "industry", "Type": "string", "Comment": "Industry vertical"},
                {"Name": "country", "Type": "string", "Comment": "Country code US|UK|CA|DE"},
                {"Name": "status", "Type": "string", "Comment": "Active|Inactive|Churned"},
                {"Name": "join_date", "Type": "string", "Comment": "Join date YYYY-MM-DD"},
                {"Name": "annual_value", "Type": "string", "Comment": "Annual value USD"},
                {"Name": "credit_limit", "Type": "string", "Comment": "Credit limit USD"},
            ],
            "Location": f"{BRONZE_S3}/",
            "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.serde2.OpenCSVSerde",
                "Parameters": {
                    "separatorChar": ",",
                    "quoteChar": "\"",
                    "escapeChar": "\\",
                },
            },
            "Compressed": False,
            "StoredAsSubDirectories": False,
        },
    }
    create_table(BRONZE_DB, table_input)


def _csv_serde() -> dict:
    """Return standard CSV SerDe config for Gold tables."""
    return {
        "SerializationLibrary": "org.apache.hadoop.hive.serde2.OpenCSVSerde",
        "Parameters": {
            "separatorChar": ",",
            "quoteChar": "\"",
            "escapeChar": "\\",
        },
    }


def _csv_formats() -> tuple[str, str]:
    return (
        "org.apache.hadoop.mapred.TextInputFormat",
        "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
    )


def register_gold_tables() -> None:
    """Register Gold zone star schema tables."""
    input_fmt, output_fmt = _csv_formats()
    serde = _csv_serde()
    base_params = {
        "classification": "csv",
        "skip.header.line.count": "1",
        "EXTERNAL": "TRUE",
    }

    # customer_fact
    create_table(GOLD_DB, {
        "Name": "customer_fact",
        "Description": "Customer fact table - one row per unique customer",
        "TableType": "EXTERNAL_TABLE",
        "Parameters": base_params,
        "StorageDescriptor": {
            "Columns": [
                {"Name": "customer_id", "Type": "string", "Comment": "PK CUST-NNN"},
                {"Name": "name", "Type": "string", "Comment": "Customer name"},
                {"Name": "email_hash", "Type": "string", "Comment": "SHA-256 of email"},
                {"Name": "phone_masked", "Type": "string", "Comment": "Masked phone"},
                {"Name": "segment", "Type": "string", "Comment": "FK to dim_segment"},
                {"Name": "industry", "Type": "string", "Comment": "Industry vertical"},
                {"Name": "country_code", "Type": "string", "Comment": "FK to dim_country"},
                {"Name": "status", "Type": "string", "Comment": "FK to dim_status"},
                {"Name": "join_date", "Type": "string", "Comment": "Join date"},
                {"Name": "annual_value", "Type": "double", "Comment": "Annual value USD"},
                {"Name": "credit_limit", "Type": "double", "Comment": "Credit limit USD"},
            ],
            "Location": f"{GOLD_S3}/customer_fact/",
            "InputFormat": input_fmt,
            "OutputFormat": output_fmt,
            "SerdeInfo": serde,
            "Compressed": False,
            "StoredAsSubDirectories": False,
        },
    })

    # dim_segment
    create_table(GOLD_DB, {
        "Name": "dim_segment",
        "Description": "Segment dimension table",
        "TableType": "EXTERNAL_TABLE",
        "Parameters": base_params,
        "StorageDescriptor": {
            "Columns": [
                {"Name": "segment_id", "Type": "int", "Comment": "Surrogate key"},
                {"Name": "segment_name", "Type": "string", "Comment": "Segment name"},
            ],
            "Location": f"{GOLD_S3}/dim_segment/",
            "InputFormat": input_fmt,
            "OutputFormat": output_fmt,
            "SerdeInfo": serde,
            "Compressed": False,
            "StoredAsSubDirectories": False,
        },
    })

    # dim_country
    create_table(GOLD_DB, {
        "Name": "dim_country",
        "Description": "Country dimension table",
        "TableType": "EXTERNAL_TABLE",
        "Parameters": base_params,
        "StorageDescriptor": {
            "Columns": [
                {"Name": "country_code", "Type": "string", "Comment": "ISO country code"},
                {"Name": "country_name", "Type": "string", "Comment": "Full country name"},
            ],
            "Location": f"{GOLD_S3}/dim_country/",
            "InputFormat": input_fmt,
            "OutputFormat": output_fmt,
            "SerdeInfo": serde,
            "Compressed": False,
            "StoredAsSubDirectories": False,
        },
    })

    # dim_status
    create_table(GOLD_DB, {
        "Name": "dim_status",
        "Description": "Status dimension table",
        "TableType": "EXTERNAL_TABLE",
        "Parameters": base_params,
        "StorageDescriptor": {
            "Columns": [
                {"Name": "status_id", "Type": "int", "Comment": "Surrogate key"},
                {"Name": "status_name", "Type": "string", "Comment": "Status name"},
            ],
            "Location": f"{GOLD_S3}/dim_status/",
            "InputFormat": input_fmt,
            "OutputFormat": output_fmt,
            "SerdeInfo": serde,
            "Compressed": False,
            "StoredAsSubDirectories": False,
        },
    })

    # customer_summary_by_segment
    create_table(GOLD_DB, {
        "Name": "customer_summary_by_segment",
        "Description": "Pre-aggregated customer metrics by segment",
        "TableType": "EXTERNAL_TABLE",
        "Parameters": base_params,
        "StorageDescriptor": {
            "Columns": [
                {"Name": "segment", "Type": "string", "Comment": "Segment name"},
                {"Name": "customer_count", "Type": "int", "Comment": "Customer count"},
                {"Name": "total_annual_value", "Type": "double", "Comment": "Total annual value"},
                {"Name": "avg_annual_value", "Type": "double", "Comment": "Avg annual value"},
                {"Name": "total_credit_limit", "Type": "double", "Comment": "Total credit limit"},
            ],
            "Location": f"{GOLD_S3}/customer_summary_by_segment/",
            "InputFormat": input_fmt,
            "OutputFormat": output_fmt,
            "SerdeInfo": serde,
            "Compressed": False,
            "StoredAsSubDirectories": False,
        },
    })


def register_all() -> Dict[str, Any]:
    """Run full registration: databases + all tables."""
    create_databases()
    register_bronze_tables()
    register_gold_tables()
    return {
        "databases": [BRONZE_DB, GOLD_DB],
        "bronze_tables": ["customers"],
        "gold_tables": [
            "customer_fact", "dim_segment", "dim_country",
            "dim_status", "customer_summary_by_segment",
        ],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = register_all()
    print(json.dumps(result, indent=2))
