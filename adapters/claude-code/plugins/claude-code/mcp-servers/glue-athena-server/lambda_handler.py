"""
AWS Lambda handler for Glue + Athena MCP Server.

Standalone Lambda function that doesn't require FastMCP.
"""

import json
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

# Initialize AWS clients
session = boto3.Session(region_name=os.getenv('AWS_REGION', 'us-east-1'))
glue = session.client('glue')
athena = session.client('athena')


# --- Tool Functions ---

def create_database(name: str, description: str = "") -> dict:
    """Create a Glue Data Catalog database."""
    try:
        glue.create_database(
            DatabaseInput={"Name": name, "Description": description}
        )
        return {"status": "success", "database": name}
    except ClientError as e:
        if e.response['Error']['Code'] == 'AlreadyExistsException':
            return {"status": "already_exists", "database": name}
        return {"status": "error", "error": str(e)}


def get_database(name: str) -> dict:
    """Get details of a Glue database."""
    try:
        response = glue.get_database(Name=name)
        db = response['Database']
        return {
            "status": "success",
            "name": db['Name'],
            "description": db.get('Description', ''),
            "location": db.get('LocationUri', '')
        }
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def get_databases() -> dict:
    """List all Glue databases."""
    try:
        response = glue.get_databases()
        databases = [
            {
                "name": db['Name'],
                "description": db.get('Description', ''),
                "location": db.get('LocationUri', '')
            }
            for db in response['DatabaseList']
        ]
        return {"status": "success", "databases": databases, "count": len(databases)}
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def get_tables(database: str) -> dict:
    """List all tables in a Glue database."""
    try:
        response = glue.get_tables(DatabaseName=database)
        tables = [
            {
                "name": table['Name'],
                "type": table.get('TableType', 'EXTERNAL_TABLE'),
                "location": table.get('StorageDescriptor', {}).get('Location', ''),
                "columns": len(table.get('StorageDescriptor', {}).get('Columns', []))
            }
            for table in response['TableList']
        ]
        return {"status": "success", "database": database, "tables": tables, "count": len(tables)}
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def athena_query(query: str, database: str, workgroup: str = "primary", timeout_seconds: int = 300) -> dict:
    """Execute an Athena query synchronously."""
    try:
        # Start query
        response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext={'Database': database},
            WorkGroup=workgroup
        )
        execution_id = response['QueryExecutionId']

        # Poll for completion
        elapsed = 0
        while elapsed < timeout_seconds:
            response = athena.get_query_execution(QueryExecutionId=execution_id)
            state = response['QueryExecution']['Status']['State']

            if state == 'SUCCEEDED':
                # Get results
                results = athena.get_query_results(QueryExecutionId=execution_id, MaxResults=100)
                rows = []
                for row in results['ResultSet']['Rows'][1:]:  # Skip header
                    rows.append([col.get('VarCharValue', '') for col in row['Data']])

                return {
                    "status": "success",
                    "execution_id": execution_id,
                    "rows": rows,
                    "row_count": len(rows)
                }

            if state in ['FAILED', 'CANCELLED']:
                reason = response['QueryExecution']['Status'].get('StateChangeReason', 'Unknown')
                return {"status": "failed", "execution_id": execution_id, "reason": reason}

            time.sleep(1)
            elapsed += 1

        return {
            "status": "timeout",
            "execution_id": execution_id,
            "message": f"Query still running after {timeout_seconds}s"
        }
    except ClientError as e:
        return {"status": "error", "error": str(e)}


# --- Lambda Handler ---

def handler(event, context):
    """AWS Lambda handler - HTTP request/response via Function URL."""
    try:
        # Parse request
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})

        tool_name = body.get('tool')
        arguments = body.get('arguments', {})

        # Health check
        if tool_name == 'health_check':
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'status': 'healthy',
                    'server': 'glue-athena',
                    'function': os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'unknown')
                })
            }

        # List tools
        if tool_name == 'list_tools':
            tools = ['create_database', 'get_database', 'get_databases', 'get_tables', 'athena_query']
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'status': 'success',
                    'tools': tools,
                    'count': len(tools)
                })
            }

        # Map tools to functions
        tool_map = {
            'create_database': create_database,
            'get_database': get_database,
            'get_databases': get_databases,
            'get_tables': get_tables,
            'athena_query': athena_query
        }

        if tool_name not in tool_map:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'status': 'error',
                    'error': f'Unknown tool: {tool_name}'
                })
            }

        # Call the tool
        result = tool_map[tool_name](**arguments)

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'success',
                'tool': tool_name,
                'result': result
            })
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'status': 'error',
                'error': str(e),
                'type': type(e).__name__
            })
        }
