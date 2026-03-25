"""
SynoDB Search

Find similar past queries using vector similarity on embeddings.
"""

import boto3
import json
from typing import List, Dict, Any, Optional, Tuple
from botocore.exceptions import ClientError

from shared.embeddings.titan_client import TitanEmbeddingsClient


class SynoDBSearch:
    """Search for similar queries in SynoDB."""

    def __init__(
        self,
        table_name: str = 'synodb_queries',
        region: str = 'us-east-1'
    ):
        """
        Initialize SynoDB search.

        Args:
            table_name: DynamoDB table name
            region: AWS region
        """
        self.table_name = table_name
        self.region = region
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        self.table = self.dynamodb.Table(table_name)
        self.titan = TitanEmbeddingsClient(region=region)

    def find_similar_queries(
        self,
        nl_query: str,
        workload: str,
        top_k: int = 5,
        min_similarity: float = 0.5,
        query_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find similar past queries using vector similarity.

        Args:
            nl_query: Natural language query
            workload: Workload name
            top_k: Number of top results to return
            min_similarity: Minimum cosine similarity threshold (0.0 to 1.0)
            query_type: Optional filter ('seed', 'learned', or None for all)

        Returns:
            List of similar queries with similarity scores

        Example:
            >>> search = SynoDBSearch()
            >>> results = search.find_similar_queries(
            ...     "What is the total portfolio value?",
            ...     "financial_portfolios",
            ...     top_k=3
            ... )
            >>> len(results) <= 3
            True
            >>> results[0]['similarity'] >= 0.5
            True
        """
        # 1. Generate embedding for input query
        query_embedding = self.titan.generate_embedding(f"question: {nl_query}")

        # 2. Scan DynamoDB for workload queries
        scan_params = {
            'IndexName': 'workload-index',
            'FilterExpression': '#workload = :wl',
            'ExpressionAttributeNames': {'#workload': 'workload'},
            'ExpressionAttributeValues': {':wl': workload}
        }

        # Add query_type filter if specified
        if query_type:
            scan_params['FilterExpression'] += ' AND query_type = :qt'
            scan_params['ExpressionAttributeValues'][':qt'] = query_type

        try:
            response = self.table.query(**scan_params)
            items = response.get('Items', [])

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                scan_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
                response = self.table.query(**scan_params)
                items.extend(response.get('Items', []))

        except ClientError as e:
            print(f"Error querying DynamoDB: {e}")
            return []

        # 3. Compute cosine similarity for each query
        similarities: List[Tuple[Dict, float]] = []

        for item in items:
            stored_embedding_bytes = item.get('embedding')
            if not stored_embedding_bytes:
                continue

            # Deserialize embedding
            stored_embedding = json.loads(stored_embedding_bytes.decode('utf-8'))

            # Compute similarity
            similarity = self.titan.cosine_similarity(query_embedding, stored_embedding)

            if similarity >= min_similarity:
                similarities.append((item, similarity))

        # 4. Sort by similarity (descending) and take top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_results = similarities[:top_k]

        # 5. Format results
        results = []
        for item, similarity in top_results:
            results.append({
                'query_id': item['query_id'],
                'nl_text': item['nl_text'],
                'sql': item['sql'],
                'explanation': item.get('explanation', ''),
                'tables_used': item.get('tables_used', []),
                'query_type': item.get('query_type', 'unknown'),
                'success_count': item.get('success_count', 0),
                'similarity': round(similarity, 4)
            })

        return results

    def get_most_successful_queries(
        self,
        workload: str,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get most successful queries by success_count.

        Args:
            workload: Workload name
            top_k: Number of top results

        Returns:
            List of queries sorted by success_count

        Example:
            >>> search = SynoDBSearch()
            >>> results = search.get_most_successful_queries("financial_portfolios", top_k=5)
            >>> len(results) <= 5
            True
        """
        try:
            response = self.table.query(
                IndexName='success_count-index',
                KeyConditionExpression='#workload = :wl',
                ExpressionAttributeNames={'#workload': 'workload'},
                ExpressionAttributeValues={':wl': workload},
                ScanIndexForward=False,  # Descending order
                Limit=top_k
            )

            items = response.get('Items', [])

            # Format results
            results = []
            for item in items:
                results.append({
                    'query_id': item['query_id'],
                    'nl_text': item['nl_text'],
                    'sql': item['sql'],
                    'explanation': item.get('explanation', ''),
                    'tables_used': item.get('tables_used', []),
                    'success_count': item.get('success_count', 0),
                    'last_used': item.get('last_used')
                })

            return results

        except ClientError as e:
            print(f"Error querying DynamoDB: {e}")
            return []

    def get_query_by_id(
        self,
        query_id: str,
        workload: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific query by ID.

        Args:
            query_id: Query ID
            workload: Workload name

        Returns:
            Query dict or None if not found

        Example:
            >>> search = SynoDBSearch()
            >>> query = search.get_query_by_id("query_abc123", "financial_portfolios")
        """
        try:
            response = self.table.get_item(
                Key={'query_id': query_id, 'workload': workload}
            )

            if 'Item' not in response:
                return None

            item = response['Item']

            return {
                'query_id': item['query_id'],
                'nl_text': item['nl_text'],
                'sql': item['sql'],
                'explanation': item.get('explanation', ''),
                'tables_used': item.get('tables_used', []),
                'query_type': item.get('query_type', 'unknown'),
                'success_count': item.get('success_count', 0),
                'last_used': item.get('last_used'),
                'created_at': item.get('created_at')
            }

        except ClientError as e:
            print(f"Error getting query from DynamoDB: {e}")
            return None

    def search_by_table(
        self,
        table_name: str,
        workload: str
    ) -> List[Dict[str, Any]]:
        """
        Get all queries that use a specific table.

        Args:
            table_name: Table name to search for
            workload: Workload name

        Returns:
            List of queries using the table

        Example:
            >>> search = SynoDBSearch()
            >>> results = search.search_by_table("positions", "financial_portfolios")
        """
        try:
            response = self.table.query(
                IndexName='workload-index',
                KeyConditionExpression='#workload = :wl',
                ExpressionAttributeNames={'#workload': 'workload'},
                ExpressionAttributeValues={':wl': workload}
            )

            items = response.get('Items', [])

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = self.table.query(
                    IndexName='workload-index',
                    KeyConditionExpression='#workload = :wl',
                    ExpressionAttributeNames={'#workload': 'workload'},
                    ExpressionAttributeValues={':wl': workload},
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                items.extend(response.get('Items', []))

            # Filter by table_name
            matching_queries = []
            for item in items:
                tables_used = item.get('tables_used', [])
                if table_name in tables_used:
                    matching_queries.append({
                        'query_id': item['query_id'],
                        'nl_text': item['nl_text'],
                        'sql': item['sql'],
                        'tables_used': tables_used,
                        'success_count': item.get('success_count', 0)
                    })

            return matching_queries

        except ClientError as e:
            print(f"Error querying DynamoDB: {e}")
            return []


def find_similar_queries(
    nl_query: str,
    workload: str,
    top_k: int = 5,
    table_name: str = 'synodb_queries',
    region: str = 'us-east-1'
) -> List[Dict[str, Any]]:
    """
    Convenience function to find similar queries.

    Args:
        nl_query: Natural language query
        workload: Workload name
        top_k: Number of top results
        table_name: DynamoDB table name
        region: AWS region

    Returns:
        List of similar queries

    Example:
        >>> results = find_similar_queries(
        ...     "What is total revenue?",
        ...     "financial_portfolios",
        ...     top_k=3
        ... )
    """
    search = SynoDBSearch(table_name=table_name, region=region)
    return search.find_similar_queries(nl_query, workload, top_k=top_k)
