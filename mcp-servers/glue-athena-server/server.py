"""
Glue + Athena MCP Server

Provides MCP interface for AWS Glue Data Catalog and Athena operations:
- Glue: database/table/crawler/job management
- Athena: synchronous query execution (wraps async start/poll/get-results)

These services are tightly coupled — Glue Catalog is Athena's metastore.
"""

import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError
from fastmcp import FastMCP

mcp = FastMCP("glue-athena")

session = boto3.Session(
    region_name=os.getenv('AWS_REGION', 'us-east-1'),
    profile_name=os.getenv('AWS_PROFILE', None) if os.getenv('AWS_PROFILE') else None
)
glue = session.client('glue')
athena = session.client('athena')


# --- Glue Database Operations ---

@mcp.tool()
def create_database(name: str, description: str = "") -> dict[str, Any]:
    """
    Create a Glue Data Catalog database.

    Args:
        name: Database name (e.g., financial_portfolios_db)
        description: Optional description
    """
    try:
        glue.create_database(
            DatabaseInput={"Name": name, "Description": description}
        )
        return {"status": "success", "database": name}
    except ClientError as e:
        if e.response['Error']['Code'] == 'AlreadyExistsException':
            return {"status": "already_exists", "database": name}
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def get_database(name: str) -> dict[str, Any]:
    """
    Get details of a Glue database.

    Args:
        name: Database name
    """
    try:
        response = glue.get_database(Name=name)
        db = response['Database']
        return {
            "status": "success",
            "name": db['Name'],
            "description": db.get('Description', ''),
            "location": db.get('LocationUri', ''),
            "parameters": db.get('Parameters', {}),
            "create_time": str(db.get('CreateTime', ''))
        }
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def get_databases() -> dict[str, Any]:
    """List all Glue databases."""
    try:
        paginator = glue.get_paginator('get_databases')
        databases = []
        for page in paginator.paginate():
            for db in page['DatabaseList']:
                databases.append({
                    "name": db['Name'],
                    "description": db.get('Description', ''),
                    "location": db.get('LocationUri', '')
                })
        return {"status": "success", "databases": databases, "count": len(databases)}
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


# --- Glue Table Operations ---

@mcp.tool()
def get_table(database: str, table: str) -> dict[str, Any]:
    """
    Get details of a Glue table including columns and parameters.

    Args:
        database: Database name
        table: Table name
    """
    try:
        response = glue.get_table(DatabaseName=database, Name=table)
        t = response['Table']
        columns = []
        for col in t.get('StorageDescriptor', {}).get('Columns', []):
            columns.append({"name": col['Name'], "type": col['Type'], "comment": col.get('Comment', '')})
        for col in t.get('PartitionKeys', []):
            columns.append({"name": col['Name'], "type": col['Type'], "comment": col.get('Comment', ''), "partition_key": True})

        return {
            "status": "success",
            "name": t['Name'],
            "database": database,
            "table_type": t.get('Parameters', {}).get('table_type', t.get('TableType', '')),
            "location": t.get('StorageDescriptor', {}).get('Location', ''),
            "columns": columns,
            "parameters": t.get('Parameters', {}),
            "create_time": str(t.get('CreateTime', ''))
        }
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def get_tables(database: str) -> dict[str, Any]:
    """
    List all tables in a Glue database.

    Args:
        database: Database name
    """
    try:
        paginator = glue.get_paginator('get_tables')
        tables = []
        for page in paginator.paginate(DatabaseName=database):
            for t in page['TableList']:
                tables.append({
                    "name": t['Name'],
                    "table_type": t.get('Parameters', {}).get('table_type', t.get('TableType', '')),
                    "columns": len(t.get('StorageDescriptor', {}).get('Columns', []))
                })
        return {"status": "success", "database": database, "tables": tables, "count": len(tables)}
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def create_table(database: str, table_input: dict) -> dict[str, Any]:
    """
    Create a table in the Glue Data Catalog.

    Args:
        database: Database name
        table_input: Full TableInput dict per Glue API spec (Name, StorageDescriptor, Parameters, etc.)
    """
    try:
        glue.create_table(DatabaseName=database, TableInput=table_input)
        return {"status": "success", "database": database, "table": table_input.get('Name', '')}
    except ClientError as e:
        if e.response['Error']['Code'] == 'AlreadyExistsException':
            return {"status": "already_exists", "database": database, "table": table_input.get('Name', '')}
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def update_table(database: str, table_input: dict) -> dict[str, Any]:
    """
    Update an existing table in the Glue Data Catalog.

    Args:
        database: Database name
        table_input: Full TableInput dict with updated properties
    """
    try:
        glue.update_table(DatabaseName=database, TableInput=table_input)
        return {"status": "success", "database": database, "table": table_input.get('Name', '')}
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


# --- Glue Crawler Operations ---

@mcp.tool()
def create_crawler(
    name: str,
    role: str,
    database_name: str,
    s3_targets: list[str],
    table_prefix: str = ""
) -> dict[str, Any]:
    """
    Create a Glue Crawler for schema discovery.

    Args:
        name: Crawler name
        role: IAM role ARN for the crawler
        database_name: Target Glue database
        s3_targets: List of S3 paths to crawl (e.g., ["s3://bucket/landing/"])
        table_prefix: Prefix for discovered table names (e.g., "bronze_")
    """
    try:
        targets = {"S3Targets": [{"Path": path} for path in s3_targets]}
        glue.create_crawler(
            Name=name,
            Role=role,
            DatabaseName=database_name,
            Targets=targets,
            TablePrefix=table_prefix
        )
        return {"status": "success", "crawler": name}
    except ClientError as e:
        if e.response['Error']['Code'] == 'AlreadyExistsException':
            return {"status": "already_exists", "crawler": name}
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def start_crawler(name: str) -> dict[str, Any]:
    """
    Start a Glue Crawler.

    Args:
        name: Crawler name
    """
    try:
        glue.start_crawler(Name=name)
        return {"status": "success", "crawler": name, "message": "Crawler started"}
    except ClientError as e:
        if 'CrawlerRunningException' in str(e):
            return {"status": "already_running", "crawler": name}
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def get_crawler(name: str) -> dict[str, Any]:
    """
    Get crawler status and details.

    Args:
        name: Crawler name
    """
    try:
        response = glue.get_crawler(Name=name)
        c = response['Crawler']
        return {
            "status": "success",
            "name": c['Name'],
            "state": c.get('State', 'UNKNOWN'),
            "database": c.get('DatabaseName', ''),
            "last_crawl": {
                "status": c.get('LastCrawl', {}).get('Status', ''),
                "tables_created": c.get('LastCrawl', {}).get('TablesCreated', 0),
                "tables_updated": c.get('LastCrawl', {}).get('TablesUpdated', 0),
                "error": c.get('LastCrawl', {}).get('ErrorMessage', '')
            }
        }
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


# --- Glue Job Operations ---

@mcp.tool()
def start_job_run(job_name: str, arguments: dict | None = None) -> dict[str, Any]:
    """
    Start a Glue ETL job run.

    Args:
        job_name: Name of the Glue job
        arguments: Optional job arguments dict (e.g., {"--bronze_path": "s3://..."})
    """
    try:
        kwargs = {"JobName": job_name}
        if arguments:
            kwargs["Arguments"] = arguments
        response = glue.start_job_run(**kwargs)
        return {"status": "success", "job_name": job_name, "run_id": response['JobRunId']}
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def get_job_run(job_name: str, run_id: str) -> dict[str, Any]:
    """
    Get status of a Glue job run.

    Args:
        job_name: Name of the Glue job
        run_id: Job run ID returned from start_job_run
    """
    try:
        response = glue.get_job_run(JobName=job_name, RunId=run_id)
        r = response['JobRun']
        return {
            "status": "success",
            "job_name": job_name,
            "run_id": run_id,
            "state": r.get('JobRunState', 'UNKNOWN'),
            "started_on": str(r.get('StartedOn', '')),
            "completed_on": str(r.get('CompletedOn', '')),
            "execution_time": r.get('ExecutionTime', 0),
            "error_message": r.get('ErrorMessage', '')
        }
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


# --- Athena Query ---

@mcp.tool()
def athena_query(
    query: str,
    database: str,
    output_location: str,
    timeout_seconds: int = 60
) -> dict[str, Any]:
    """
    Execute an Athena SQL query synchronously (handles start, poll, get-results).

    Args:
        query: SQL query string
        database: Glue database to query against
        output_location: S3 path for query results (e.g., s3://bucket/athena-results/)
        timeout_seconds: Max wait time (default 60s). Returns execution_id if exceeded.
    """
    try:
        start_response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": database},
            ResultConfiguration={"OutputLocation": output_location}
        )
        execution_id = start_response['QueryExecutionId']

        # Poll until complete or timeout
        elapsed = 0
        while elapsed < timeout_seconds:
            exec_response = athena.get_query_execution(QueryExecutionId=execution_id)
            state = exec_response['QueryExecution']['Status']['State']

            if state == 'SUCCEEDED':
                results = athena.get_query_results(QueryExecutionId=execution_id)
                rows = []
                columns = [col['Label'] for col in results['ResultSet']['ResultSetMetadata']['ColumnInfo']]
                for row in results['ResultSet']['Rows'][1:]:  # Skip header row
                    rows.append({columns[i]: row['Data'][i].get('VarCharValue', '') for i in range(len(columns))})

                return {
                    "status": "success",
                    "execution_id": execution_id,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows)
                }
            elif state in ('FAILED', 'CANCELLED'):
                reason = exec_response['QueryExecution']['Status'].get('StateChangeReason', '')
                return {"status": "failed", "execution_id": execution_id, "state": state, "reason": reason}

            time.sleep(1)
            elapsed += 1

        return {
            "status": "timeout",
            "execution_id": execution_id,
            "message": f"Query still running after {timeout_seconds}s. Check manually with execution_id."
        }
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


if __name__ == "__main__":
    mcp.run()
