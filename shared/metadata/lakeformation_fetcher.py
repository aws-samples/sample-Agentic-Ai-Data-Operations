"""
Lake Formation Metadata Fetcher

Fetches LF-Tags and TBAC grants from AWS Lake Formation.
"""

import boto3
from typing import Dict, List, Optional, Any
from botocore.exceptions import ClientError


class LakeFormationFetcher:
    """Fetch LF-Tags and permissions from AWS Lake Formation."""

    def __init__(self, region: str = 'us-east-1'):
        """
        Initialize Lake Formation client.

        Args:
            region: AWS region
        """
        self.lf = boto3.client('lakeformation', region_name=region)
        self.region = region

    def fetch_table_lf_tags(self, database: str, table: str) -> Dict[str, List[Dict[str, str]]]:
        """
        Fetch LF-Tags for a table and its columns.

        Args:
            database: Database name
            table: Table name

        Returns:
            Dict with structure:
            {
                "table_tags": [{"TagKey": "...", "TagValues": [...]}],
                "column_tags": {
                    "column_name": [{"TagKey": "...", "TagValues": [...]}]
                }
            }

        Raises:
            ValueError: If table not found or no LF-Tags applied
        """
        try:
            response = self.lf.get_resource_lf_tags(
                Resource={
                    'Table': {
                        'DatabaseName': database,
                        'Name': table
                    }
                },
                ShowAssignedLFTags=True
            )

            # Table-level tags
            table_tags = response.get('LFTagOnDatabase', []) + response.get('LFTagsOnTable', [])

            # Column-level tags
            column_tags = {}
            for col_tag_info in response.get('LFTagsOnColumns', []):
                col_name = col_tag_info['Name']
                tags = col_tag_info.get('LFTags', [])
                column_tags[col_name] = tags

            return {
                "table_tags": table_tags,
                "column_tags": column_tags
            }

        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityNotFoundException':
                # Table exists but no LF-Tags applied - return empty
                return {
                    "table_tags": [],
                    "column_tags": {}
                }
            raise

    def fetch_column_lf_tags(self, database: str, table: str, column: str) -> List[Dict[str, str]]:
        """
        Fetch LF-Tags for a specific column.

        Args:
            database: Database name
            table: Table name
            column: Column name

        Returns:
            List of LF-Tags [{"TagKey": "...", "TagValues": [...]}]

        Example:
            >>> lf = LakeFormationFetcher()
            >>> tags = lf.fetch_column_lf_tags("financial_portfolios_db", "positions", "manager_name")
            >>> tags
            [
                {"TagKey": "PII_Classification", "TagValues": ["MEDIUM"]},
                {"TagKey": "PII_Type", "TagValues": ["NAME"]},
                {"TagKey": "Data_Sensitivity", "TagValues": ["MEDIUM"]}
            ]
        """
        all_tags = self.fetch_table_lf_tags(database, table)
        return all_tags["column_tags"].get(column, [])

    def get_tag_value(self, tags: List[Dict[str, str]], tag_key: str) -> Optional[str]:
        """
        Extract tag value from LF-Tags list.

        Args:
            tags: List of LF-Tags
            tag_key: Tag key to find

        Returns:
            Tag value (first value if multiple), or None if not found

        Example:
            >>> tags = [{"TagKey": "PII_Classification", "TagValues": ["HIGH"]}]
            >>> get_tag_value(tags, "PII_Classification")
            'HIGH'
        """
        for tag in tags:
            if tag['TagKey'] == tag_key:
                values = tag.get('TagValues', [])
                return values[0] if values else None
        return None

    def list_lf_tags(self) -> List[Dict[str, Any]]:
        """
        List all LF-Tags defined in Lake Formation.

        Returns:
            List of LF-Tag definitions

        Example:
            >>> lf = LakeFormationFetcher()
            >>> tags = lf.list_lf_tags()
            >>> [t['TagKey'] for t in tags]
            ['PII_Classification', 'PII_Type', 'Data_Sensitivity']
        """
        try:
            response = self.lf.list_lf_tags()
            return response.get('LFTags', [])
        except ClientError:
            return []

    def fetch_table_permissions(self, database: str, table: str) -> List[Dict[str, Any]]:
        """
        Fetch all permissions granted on a table.

        Args:
            database: Database name
            table: Table name

        Returns:
            List of permission grants

        Example:
            >>> lf = LakeFormationFetcher()
            >>> perms = lf.fetch_table_permissions("financial_portfolios_db", "positions")
            >>> len(perms)
            3
        """
        try:
            response = self.lf.list_permissions(
                Resource={
                    'Table': {
                        'DatabaseName': database,
                        'Name': table
                    }
                }
            )
            return response.get('PrincipalResourcePermissions', [])
        except ClientError:
            return []
