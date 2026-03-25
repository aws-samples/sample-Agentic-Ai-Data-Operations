"""
SynoDB Setup

Creates DynamoDB table for storing seed queries and learned SQL patterns.
"""

import boto3
from typing import Dict, Any
from botocore.exceptions import ClientError


def create_synodb_table(
    table_name: str = 'synodb_queries',
    region: str = 'us-east-1',
    billing_mode: str = 'PAY_PER_REQUEST'
) -> Dict[str, Any]:
    """
    Create DynamoDB table for SynoDB.

    Table schema:
    - Partition key: query_id (string)
    - Sort key: workload (string)
    - GSI: workload-index (for querying all queries in a workload)
    - GSI: success_count-index (for finding most successful queries)

    Args:
        table_name: DynamoDB table name
        region: AWS region
        billing_mode: 'PAY_PER_REQUEST' or 'PROVISIONED'

    Returns:
        Dict with table metadata

    Raises:
        ClientError: If table creation fails

    Example:
        >>> create_synodb_table()
        {'TableName': 'synodb_queries', 'TableStatus': 'CREATING'}
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)

    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'query_id', 'KeyType': 'HASH'},  # Partition key
                {'AttributeName': 'workload', 'KeyType': 'RANGE'}  # Sort key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'query_id', 'AttributeType': 'S'},
                {'AttributeName': 'workload', 'AttributeType': 'S'},
                {'AttributeName': 'success_count', 'AttributeType': 'N'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'workload-index',
                    'KeySchema': [
                        {'AttributeName': 'workload', 'KeyType': 'HASH'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'}
                },
                {
                    'IndexName': 'success_count-index',
                    'KeySchema': [
                        {'AttributeName': 'workload', 'KeyType': 'HASH'},
                        {'AttributeName': 'success_count', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'}
                }
            ],
            BillingMode=billing_mode
        )

        # Wait for table to be created
        table.meta.client.get_waiter('table_exists').wait(TableName=table_name)

        return {
            'TableName': table.name,
            'TableStatus': table.table_status,
            'ItemCount': table.item_count,
            'TableArn': table.table_arn
        }

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            # Table already exists
            table = dynamodb.Table(table_name)
            return {
                'TableName': table.name,
                'TableStatus': 'ACTIVE',
                'Message': 'Table already exists'
            }
        raise


def delete_synodb_table(
    table_name: str = 'synodb_queries',
    region: str = 'us-east-1'
):
    """
    Delete SynoDB table (USE WITH CAUTION!).

    Args:
        table_name: DynamoDB table name
        region: AWS region

    Example:
        >>> delete_synodb_table()  # Deletes the table
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    table.delete()
    table.meta.client.get_waiter('table_not_exists').wait(TableName=table_name)


def get_table_info(
    table_name: str = 'synodb_queries',
    region: str = 'us-east-1'
) -> Dict[str, Any]:
    """
    Get SynoDB table information.

    Args:
        table_name: DynamoDB table name
        region: AWS region

    Returns:
        Dict with table metadata

    Example:
        >>> info = get_table_info()
        >>> info['TableName']
        'synodb_queries'
        >>> info['ItemCount'] >= 0
        True
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    # Force metadata refresh
    table.reload()

    return {
        'TableName': table.name,
        'TableStatus': table.table_status,
        'ItemCount': table.item_count,
        'TableSizeBytes': table.table_size_bytes,
        'CreationDateTime': str(table.creation_date_time),
        'TableArn': table.table_arn
    }


def ensure_table_exists(
    table_name: str = 'synodb_queries',
    region: str = 'us-east-1'
) -> bool:
    """
    Ensure SynoDB table exists (create if missing).

    Args:
        table_name: DynamoDB table name
        region: AWS region

    Returns:
        True if table exists or was created

    Example:
        >>> ensure_table_exists()
        True
    """
    try:
        get_table_info(table_name, region)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            # Table doesn't exist, create it
            create_synodb_table(table_name, region)
            return True
        raise
