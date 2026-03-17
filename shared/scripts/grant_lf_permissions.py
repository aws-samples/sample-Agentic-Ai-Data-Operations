
import boto3
import json
import sys

lf_client = boto3.client('lakeformation')

def grant_database_permissions(role_arn, databases):
    """Grant Lake Formation database permissions"""
    for database in databases:
        try:
            response = lf_client.grant_permissions(
                Principal={'DataLakePrincipalIdentifier': role_arn},
                Resource={
                    'Database': {
                        'Name': database
                    }
                },
                Permissions=['DESCRIBE'],
                PermissionsWithGrantOption=[]
            )
            print(f"✓ Granted DESCRIBE on database: {database}")
        except Exception as e:
            print(f"✗ Failed to grant on {database}: {e}", file=sys.stderr)

def grant_table_permissions(role_arn, database, table='*'):
    """Grant Lake Formation table permissions"""
    try:
        response = lf_client.grant_permissions(
            Principal={'DataLakePrincipalIdentifier': role_arn},
            Resource={
                'Table': {
                    'DatabaseName': database,
                    'Name': table
                }
            },
            Permissions=['SELECT', 'DESCRIBE'],
            PermissionsWithGrantOption=[]
        )
        print(f"✓ Granted SELECT/DESCRIBE on {database}.{table}")
    except Exception as e:
        print(f"✗ Failed to grant table permissions: {e}", file=sys.stderr)

if __name__ == "__main__":
    role_arn = "arn:aws:iam::123456789012:role/demo_role"

    # Get all databases from Glue Catalog
    glue_client = boto3.client('glue')
    databases = []

    try:
        paginator = glue_client.get_paginator('get_databases')
        for page in paginator.paginate():
            databases.extend([db['Name'] for db in page['DatabaseList']])
    except Exception as e:
        print(f"✗ Failed to list databases: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(databases)} databases: {', '.join(databases)}")

    # Grant database-level permissions
    grant_database_permissions(role_arn, databases)

    # Grant table-level permissions
    for db in databases:
        grant_table_permissions(role_arn, db, '*')

    print("\n✓ Lake Formation permissions granted successfully")
