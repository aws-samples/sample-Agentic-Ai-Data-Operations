"""
SageMaker Catalog MCP Server

Provides MCP interface for SageMaker Catalog custom metadata operations.
Stores business context (column roles, PII flags, hierarchies, relationships)
as custom metadata properties on Glue Data Catalog tables/columns.
"""

import json
import os
from typing import Any, Dict, Optional

import boto3
from fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("sagemaker-catalog")

# AWS clients
glue_client = boto3.client('glue', region_name=os.getenv('AWS_REGION', 'us-east-1'))


@mcp.tool()
def put_custom_metadata(
    database: str,
    table: str,
    custom_metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Store custom business metadata for a table/columns in SageMaker Catalog.

    This extends Glue Data Catalog with custom properties for:
    - Column roles (measure, dimension, temporal, identifier)
    - Default aggregations (sum, avg, count, count_distinct, etc.)
    - Business names and descriptions
    - PII flags
    - Dimension hierarchies
    - Relationships (foreign keys)
    - Default filters
    - Time intelligence settings

    Args:
        database: Glue database name
        table: Glue table name
        custom_metadata: Custom metadata structure with column-level details

    Returns:
        Confirmation of metadata storage
    """
    try:
        # Get existing table metadata
        response = glue_client.get_table(DatabaseName=database, Name=table)
        table_metadata = response['Table']

        # Merge custom metadata into table parameters
        if 'Parameters' not in table_metadata:
            table_metadata['Parameters'] = {}

        # Store as JSON in a custom parameter key
        table_metadata['Parameters']['custom_metadata'] = json.dumps(custom_metadata)

        # Update table with new parameters
        table_input = {
            'Name': table_metadata['Name'],
            'StorageDescriptor': table_metadata['StorageDescriptor'],
            'Parameters': table_metadata['Parameters']
        }

        if 'PartitionKeys' in table_metadata:
            table_input['PartitionKeys'] = table_metadata['PartitionKeys']
        if 'ViewOriginalText' in table_metadata:
            table_input['ViewOriginalText'] = table_metadata['ViewOriginalText']
        if 'ViewExpandedText' in table_metadata:
            table_input['ViewExpandedText'] = table_metadata['ViewExpandedText']

        glue_client.update_table(
            DatabaseName=database,
            TableInput=table_input
        )

        return {
            "status": "success",
            "database": database,
            "table": table,
            "message": f"Custom metadata stored for {database}.{table}"
        }

    except Exception as e:
        return {
            "status": "error",
            "database": database,
            "table": table,
            "error": str(e)
        }


@mcp.tool()
def get_custom_metadata(
    database: str,
    table: str
) -> Dict[str, Any]:
    """
    Retrieve custom business metadata for a table from SageMaker Catalog.

    Args:
        database: Glue database name
        table: Glue table name

    Returns:
        Custom metadata structure or empty dict if none exists
    """
    try:
        response = glue_client.get_table(DatabaseName=database, Name=table)
        table_metadata = response['Table']

        if 'Parameters' in table_metadata and 'custom_metadata' in table_metadata['Parameters']:
            custom_metadata = json.loads(table_metadata['Parameters']['custom_metadata'])
            return {
                "status": "success",
                "database": database,
                "table": table,
                "custom_metadata": custom_metadata
            }
        else:
            return {
                "status": "success",
                "database": database,
                "table": table,
                "custom_metadata": {},
                "message": "No custom metadata found"
            }

    except Exception as e:
        return {
            "status": "error",
            "database": database,
            "table": table,
            "error": str(e)
        }


@mcp.tool()
def get_column_metadata(
    database: str,
    table: str,
    column: str
) -> Dict[str, Any]:
    """
    Retrieve metadata for a specific column.

    Args:
        database: Glue database name
        table: Glue table name
        column: Column name

    Returns:
        Column metadata including custom properties
    """
    try:
        # Get full table metadata
        result = get_custom_metadata(database, table)

        if result['status'] == 'error':
            return result

        custom_metadata = result.get('custom_metadata', {})
        columns = custom_metadata.get('columns', {})

        if column in columns:
            return {
                "status": "success",
                "database": database,
                "table": table,
                "column": column,
                "metadata": columns[column]
            }
        else:
            return {
                "status": "success",
                "database": database,
                "table": table,
                "column": column,
                "metadata": {},
                "message": f"No custom metadata found for column {column}"
            }

    except Exception as e:
        return {
            "status": "error",
            "database": database,
            "table": table,
            "column": column,
            "error": str(e)
        }


@mcp.tool()
def list_measures(
    database: str,
    table: str
) -> Dict[str, Any]:
    """
    List all measure columns in a table (for SQL generation).

    Args:
        database: Glue database name
        table: Glue table name

    Returns:
        List of measure columns with their aggregation types
    """
    try:
        result = get_custom_metadata(database, table)

        if result['status'] == 'error':
            return result

        custom_metadata = result.get('custom_metadata', {})
        columns = custom_metadata.get('columns', {})

        measures = {
            col_name: {
                "default_aggregation": col_meta.get("default_aggregation", "sum"),
                "business_name": col_meta.get("business_name", col_name)
            }
            for col_name, col_meta in columns.items()
            if col_meta.get("role") == "measure"
        }

        return {
            "status": "success",
            "database": database,
            "table": table,
            "measures": measures
        }

    except Exception as e:
        return {
            "status": "error",
            "database": database,
            "table": table,
            "error": str(e)
        }


@mcp.tool()
def list_dimensions(
    database: str,
    table: str
) -> Dict[str, Any]:
    """
    List all dimension columns in a table.

    Args:
        database: Glue database name
        table: Glue table name

    Returns:
        List of dimension columns
    """
    try:
        result = get_custom_metadata(database, table)

        if result['status'] == 'error':
            return result

        custom_metadata = result.get('custom_metadata', {})
        columns = custom_metadata.get('columns', {})

        dimensions = {
            col_name: {
                "business_name": col_meta.get("business_name", col_name),
                "hierarchy": col_meta.get("hierarchy", None)
            }
            for col_name, col_meta in columns.items()
            if col_meta.get("role") == "dimension"
        }

        return {
            "status": "success",
            "database": database,
            "table": table,
            "dimensions": dimensions
        }

    except Exception as e:
        return {
            "status": "error",
            "database": database,
            "table": table,
            "error": str(e)
        }


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=int(os.getenv("MCP_PORT", "8003")))
    else:
        mcp.run()
