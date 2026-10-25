"""
Glue Catalog Metadata Fetcher

Fetches technical metadata (schemas, data types, partitions) from AWS Glue Data Catalog.
"""

import boto3
from typing import Dict, List, Optional, Any
from botocore.exceptions import ClientError


class GlueFetcher:
    """Fetch metadata from AWS Glue Data Catalog."""

    def __init__(self, region: str = 'us-east-1', catalog_id: Optional[str] = None):
        """
        Initialize Glue client.

        Args:
            region: AWS region
            catalog_id: Glue Catalog ID (12-digit AWS account) to target.
                When None, boto3 uses the caller's catalog (single-account
                mode). When set, every Glue API call passes CatalogId so
                reads hit a remote catalog (multi-account mode). See
                docs/multi-account-deployment.md.
        """
        self.glue = boto3.client('glue', region_name=region)
        self.region = region
        self.catalog_id = catalog_id

    def _catalog_kwargs(self) -> Dict[str, str]:
        """Return {'CatalogId': ...} if multi-account, else {} (caller's catalog)."""
        return {'CatalogId': self.catalog_id} if self.catalog_id else {}

    def fetch_database_metadata(self, database: str) -> Dict[str, Any]:
        """
        Fetch database metadata.

        Args:
            database: Database name

        Returns:
            Dict with database metadata

        Raises:
            ClientError: If database not found
        """
        try:
            response = self.glue.get_database(Name=database, **self._catalog_kwargs())
            db_meta = response['Database']

            return {
                "name": db_meta['Name'],
                "description": db_meta.get('Description', ''),
                "location_uri": db_meta.get('LocationUri', ''),
                "create_time": db_meta.get('CreateTime'),
                "parameters": db_meta.get('Parameters', {})
            }

        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityNotFoundException':
                raise ValueError(f"Database '{database}' not found in Glue Catalog")
            raise

    def fetch_table_metadata(self, database: str, table: str) -> Dict[str, Any]:
        """
        Fetch table metadata from Glue Catalog.

        Args:
            database: Database name
            table: Table name

        Returns:
            Dict containing:
            - columns: List of column definitions
            - partitions: List of partition keys
            - location: S3 location
            - table_type: EXTERNAL_TABLE, MANAGED_TABLE, etc.
            - format: iceberg, parquet, csv, etc.
            - parameters: Table parameters

        Raises:
            ValueError: If table not found
        """
        try:
            response = self.glue.get_table(
                DatabaseName=database, Name=table, **self._catalog_kwargs()
            )
            table_meta = response['Table']
            storage_desc = table_meta.get('StorageDescriptor', {})

            # Extract column definitions
            columns = []
            for col in storage_desc.get('Columns', []):
                columns.append({
                    "name": col['Name'],
                    "type": col['Type'],
                    "comment": col.get('Comment', '')
                })

            # Extract partition keys
            partitions = []
            for pk in table_meta.get('PartitionKeys', []):
                partitions.append({
                    "name": pk['Name'],
                    "type": pk['Type'],
                    "comment": pk.get('Comment', '')
                })

            # Determine format
            format_type = storage_desc.get('SerdeInfo', {}).get('SerializationLibrary', '')
            if 'iceberg' in format_type.lower() or table_meta.get('Parameters', {}).get('table_type') == 'ICEBERG':
                format_name = 'iceberg'
            elif 'parquet' in format_type.lower():
                format_name = 'parquet'
            elif 'csv' in format_type.lower() or 'LazySimpleSerDe' in format_type:
                format_name = 'csv'
            elif 'json' in format_type.lower():
                format_name = 'json'
            else:
                format_name = 'unknown'

            return {
                "columns": columns,
                "partitions": partitions,
                "location": storage_desc.get('Location', ''),
                "table_type": table_meta.get('TableType', 'EXTERNAL_TABLE'),
                "format": format_name,
                "parameters": table_meta.get('Parameters', {}),
                "create_time": table_meta.get('CreateTime'),
                "update_time": table_meta.get('UpdateTime')
            }

        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityNotFoundException':
                raise ValueError(f"Table '{database}.{table}' not found in Glue Catalog")
            raise

    def list_tables(self, database: str) -> List[str]:
        """
        List all tables in a database.

        Args:
            database: Database name

        Returns:
            List of table names

        Raises:
            ValueError: If database not found
        """
        try:
            response = self.glue.get_tables(DatabaseName=database, **self._catalog_kwargs())
            return [table['Name'] for table in response['TableList']]

        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityNotFoundException':
                raise ValueError(f"Database '{database}' not found")
            raise

    def list_databases(self) -> List[str]:
        """
        List all databases.

        Returns:
            List of database names
        """
        response = self.glue.get_databases(**self._catalog_kwargs())
        return [db['Name'] for db in response['DatabaseList']]
