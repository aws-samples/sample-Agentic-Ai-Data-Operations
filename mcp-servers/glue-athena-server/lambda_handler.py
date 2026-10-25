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


def _job_update(
    role: str,
    script_location: str,
    glue_version: str,
    worker_type: str,
    number_of_workers: int,
    python_version: str,
    default_arguments: dict | None,
    description: str,
) -> dict:
    update = {
        "Role": role,
        "Command": {
            "Name": "glueetl",
            "ScriptLocation": script_location,
            "PythonVersion": python_version,
        },
        "GlueVersion": glue_version,
        "WorkerType": worker_type,
        "NumberOfWorkers": number_of_workers,
    }
    if default_arguments:
        update["DefaultArguments"] = default_arguments
    if description:
        update["Description"] = description
    return update


def get_job(job_name: str) -> dict:
    """Get the configuration of a Glue ETL job."""
    try:
        job = glue.get_job(JobName=job_name)["Job"]
        command = job.get("Command", {})
        return {
            "status": "success",
            "job_name": job_name,
            "role": job.get("Role", ""),
            "script_location": command.get("ScriptLocation", ""),
            "command_name": command.get("Name", ""),
            "python_version": command.get("PythonVersion", ""),
            "glue_version": job.get("GlueVersion", ""),
            "worker_type": job.get("WorkerType", ""),
            "number_of_workers": job.get("NumberOfWorkers", 0),
            "default_arguments": job.get("DefaultArguments", {}),
            "description": job.get("Description", ""),
        }
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def create_job(
    job_name: str,
    role: str,
    script_location: str,
    glue_version: str = "5.0",
    worker_type: str = "G.1X",
    number_of_workers: int = 2,
    python_version: str = "3",
    default_arguments: dict | None = None,
    description: str = "",
) -> dict:
    """Create a Glue ETL job for a generated demo or workload script."""
    try:
        response = glue.create_job(
            Name=job_name,
            **_job_update(
                role,
                script_location,
                glue_version,
                worker_type,
                number_of_workers,
                python_version,
                default_arguments,
                description,
            ),
        )
        return {"status": "success", "job_name": response.get("Name", job_name)}
    except ClientError as e:
        if e.response["Error"]["Code"] == "AlreadyExistsException":
            return {"status": "already_exists", "job_name": job_name}
        return {"status": "error", "error": str(e)}


def update_job(
    job_name: str,
    role: str,
    script_location: str,
    glue_version: str = "5.0",
    worker_type: str = "G.1X",
    number_of_workers: int = 2,
    python_version: str = "3",
    default_arguments: dict | None = None,
    description: str = "",
) -> dict:
    """Update the bounded Glue ETL job configuration used by the demo."""
    try:
        response = glue.update_job(
            JobName=job_name,
            JobUpdate=_job_update(
                role,
                script_location,
                glue_version,
                worker_type,
                number_of_workers,
                python_version,
                default_arguments,
                description,
            ),
        )
        return {"status": "success", "job_name": response.get("JobName", job_name)}
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def get_job_run(job_name: str, run_id: str) -> dict:
    """Get a Glue job run for demo monitoring and debugging."""
    try:
        run = glue.get_job_run(JobName=job_name, RunId=run_id)["JobRun"]
        return {
            "status": "success",
            "job_name": job_name,
            "run_id": run_id,
            "state": run.get("JobRunState", "UNKNOWN"),
            "started_on": str(run.get("StartedOn", "")),
            "completed_on": str(run.get("CompletedOn", "")),
            "execution_time": run.get("ExecutionTime", 0),
            "error_message": run.get("ErrorMessage", ""),
        }
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def get_job_runs(job_name: str, max_results: int = 10) -> dict:
    """List recent runs for a Glue job."""
    try:
        response = glue.get_job_runs(
            JobName=job_name,
            MaxResults=max(1, min(max_results, 100)),
        )
        runs = [
            {
                "run_id": run.get("Id", ""),
                "state": run.get("JobRunState", "UNKNOWN"),
                "started_on": str(run.get("StartedOn", "")),
                "completed_on": str(run.get("CompletedOn", "")),
                "execution_time": run.get("ExecutionTime", 0),
                "error_message": run.get("ErrorMessage", ""),
                "arguments": run.get("Arguments", {}),
            }
            for run in response.get("JobRuns", [])
        ]
        return {"status": "success", "job_name": job_name, "runs": runs, "count": len(runs)}
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def start_job_run(job_name: str, arguments: dict | None = None) -> dict:
    """Start a Glue job run."""
    try:
        request = {"JobName": job_name}
        if arguments:
            request["Arguments"] = arguments
        response = glue.start_job_run(**request)
        return {"status": "success", "job_name": job_name, "run_id": response["JobRunId"]}
    except ClientError as e:
        return {"status": "error", "error": str(e)}


def stop_job_run(job_name: str, run_id: str) -> dict:
    """Stop one Glue job run after explicit human approval."""
    try:
        response = glue.batch_stop_job_run(JobName=job_name, JobRunIds=[run_id])
        errors = response.get("Errors", [])
        if errors:
            return {"status": "error", "job_name": job_name, "run_id": run_id, "errors": errors}
        return {"status": "success", "job_name": job_name, "run_id": run_id, "stopped": True}
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
            tools = [
                'create_database', 'get_database', 'get_databases', 'get_tables',
                'get_job', 'create_job', 'update_job', 'start_job_run',
                'get_job_run', 'get_job_runs', 'stop_job_run', 'athena_query'
            ]
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
            'get_job': get_job,
            'create_job': create_job,
            'update_job': update_job,
            'start_job_run': start_job_run,
            'get_job_run': get_job_run,
            'get_job_runs': get_job_runs,
            'stop_job_run': stop_job_run,
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
