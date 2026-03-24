"""
Lake Formation MCP Server

Provides MCP interface for AWS Lake Formation operations:
- LF-Tag management (create, list, apply, remove)
- Permission grants and revocations (TBAC)
- Resource tag inspection
"""

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError
from fastmcp import FastMCP

mcp = FastMCP("lakeformation")

session = boto3.Session(
    region_name=os.getenv('AWS_REGION', 'us-east-1'),
    profile_name=os.getenv('AWS_PROFILE', None) if os.getenv('AWS_PROFILE') else None
)
client = session.client('lakeformation')


@mcp.tool()
def create_lf_tag(tag_key: str, tag_values: list[str]) -> dict[str, Any]:
    """
    Create a new Lake Formation LF-Tag.

    Args:
        tag_key: Tag key name (e.g., PII_Classification, PII_Type, Data_Sensitivity)
        tag_values: Allowed values for the tag (e.g., ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"])
    """
    try:
        client.create_lf_tag(TagKey=tag_key, TagValues=tag_values)
        return {"status": "success", "tag_key": tag_key, "tag_values": tag_values}
    except ClientError as e:
        if e.response['Error']['Code'] == 'AlreadyExistsException':
            return {"status": "already_exists", "tag_key": tag_key, "tag_values": tag_values}
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def get_lf_tag(tag_key: str) -> dict[str, Any]:
    """
    Get details of a Lake Formation LF-Tag.

    Args:
        tag_key: Tag key name to retrieve
    """
    try:
        response = client.get_lf_tag(TagKey=tag_key)
        return {
            "status": "success",
            "tag_key": response['TagKey'],
            "tag_values": response['TagValues']
        }
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def list_lf_tags() -> dict[str, Any]:
    """List all Lake Formation LF-Tags in the account."""
    try:
        paginator = client.get_paginator('list_lf_tags')
        tags = []
        for page in paginator.paginate():
            for tag in page.get('LFTags', []):
                tags.append({"tag_key": tag['TagKey'], "tag_values": tag['TagValues']})
        return {"status": "success", "tags": tags, "count": len(tags)}
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def add_lf_tags_to_resource(
    database: str,
    table: str,
    lf_tags: list[dict],
    column_names: list[str] | None = None
) -> dict[str, Any]:
    """
    Apply LF-Tags to a Glue table or specific columns.

    Args:
        database: Glue database name
        table: Glue table name
        lf_tags: List of tag dicts, e.g., [{"TagKey": "PII_Classification", "TagValues": ["HIGH"]}]
        column_names: If provided, apply tags to these columns only. If None, apply to the table.
    """
    try:
        if column_names:
            resource = {
                "TableWithColumns": {
                    "DatabaseName": database,
                    "Name": table,
                    "ColumnNames": column_names
                }
            }
        else:
            resource = {
                "Table": {
                    "DatabaseName": database,
                    "Name": table
                }
            }

        client.add_lf_tags_to_resource(Resource=resource, LFTags=lf_tags)
        return {
            "status": "success",
            "database": database,
            "table": table,
            "columns": column_names,
            "tags_applied": lf_tags
        }
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def remove_lf_tags_from_resource(
    database: str,
    table: str,
    lf_tags: list[dict],
    column_names: list[str] | None = None
) -> dict[str, Any]:
    """
    Remove LF-Tags from a Glue table or specific columns.

    Args:
        database: Glue database name
        table: Glue table name
        lf_tags: List of tag dicts to remove
        column_names: If provided, remove tags from these columns only.
    """
    try:
        if column_names:
            resource = {
                "TableWithColumns": {
                    "DatabaseName": database,
                    "Name": table,
                    "ColumnNames": column_names
                }
            }
        else:
            resource = {
                "Table": {
                    "DatabaseName": database,
                    "Name": table
                }
            }

        client.remove_lf_tags_from_resource(Resource=resource, LFTags=lf_tags)
        return {"status": "success", "database": database, "table": table, "tags_removed": lf_tags}
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def get_resource_lf_tags(database: str, table: str) -> dict[str, Any]:
    """
    Get all LF-Tags applied to a Glue table and its columns.

    Args:
        database: Glue database name
        table: Glue table name
    """
    try:
        response = client.get_resource_lf_tags(
            Resource={"Table": {"DatabaseName": database, "Name": table}},
            ShowAssignedLFTags=True
        )
        return {
            "status": "success",
            "database_tags": response.get('LFTagOnDatabase', []),
            "table_tags": response.get('LFTagsOnTable', []),
            "column_tags": response.get('LFTagsOnColumns', [])
        }
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def grant_permissions(
    principal_arn: str,
    permissions: list[str],
    resource: dict
) -> dict[str, Any]:
    """
    Grant Lake Formation permissions to a principal.

    Args:
        principal_arn: IAM role/user ARN (e.g., arn:aws:iam::ACCOUNT:role/GlueRole)
        permissions: List of permissions (e.g., ["SELECT", "DESCRIBE"])
        resource: Resource dict — supports Table, Database, or LFTagPolicy.
            Example LFTagPolicy: {"LFTagPolicy": {"ResourceType": "TABLE", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["LOW", "MEDIUM"]}]}}
            Example Table: {"Table": {"DatabaseName": "mydb", "Name": "mytable"}}
            Example Database: {"Database": {"Name": "mydb"}}
    """
    try:
        client.grant_permissions(
            Principal={"DataLakePrincipalIdentifier": principal_arn},
            Resource=resource,
            Permissions=permissions
        )
        return {"status": "success", "principal": principal_arn, "permissions": permissions}
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def revoke_permissions(
    principal_arn: str,
    permissions: list[str],
    resource: dict
) -> dict[str, Any]:
    """
    Revoke Lake Formation permissions from a principal.

    Args:
        principal_arn: IAM role/user ARN
        permissions: List of permissions to revoke
        resource: Resource dict (same format as grant_permissions)
    """
    try:
        client.revoke_permissions(
            Principal={"DataLakePrincipalIdentifier": principal_arn},
            Resource=resource,
            Permissions=permissions
        )
        return {"status": "success", "principal": principal_arn, "permissions_revoked": permissions}
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


@mcp.tool()
def batch_grant_permissions(entries: list[dict]) -> dict[str, Any]:
    """
    Grant permissions to multiple principals/resources in one call.

    Args:
        entries: List of grant entries. Each entry has:
            - Id: Unique identifier for this entry
            - Principal: {"DataLakePrincipalIdentifier": "arn:..."}
            - Resource: Table, Database, or LFTagPolicy resource
            - Permissions: ["SELECT", "DESCRIBE", ...]
    """
    try:
        response = client.batch_grant_permissions(Entries=entries)
        failures = response.get('Failures', [])
        return {
            "status": "success" if not failures else "partial_failure",
            "total": len(entries),
            "succeeded": len(entries) - len(failures),
            "failures": failures
        }
    except ClientError as e:
        return {"status": "error", "error": str(e), "code": e.response['Error']['Code']}


if __name__ == "__main__":
    mcp.run()
