"""
Query Executor

Execute SQL queries via Athena, cache results, and save successful queries to SynoDB.
"""

import boto3
import hashlib
import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from shared.analysis_agent.sql_generator import SQLGenerationResult
from shared.synodb.loader import SynoDBLoader


@dataclass
class QueryResult:
    """Result of query execution."""
    query_id: str
    sql: str
    status: str  # 'success', 'failed', 'cached'
    row_count: int
    columns: List[str] = field(default_factory=list)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    execution_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    from_cache: bool = False
    athena_query_execution_id: Optional[str] = None


class QueryExecutor:
    """Execute SQL queries via Athena with caching."""

    def __init__(
        self,
        athena_database: str,
        s3_output_location: str,
        region: str = 'us-east-1',
        cache_ttl_seconds: int = 3600,
        enable_cache: bool = True
    ):
        """
        Initialize query executor.

        Args:
            athena_database: Athena database name
            s3_output_location: S3 path for Athena query results (e.g., s3://bucket/athena-results/)
            region: AWS region
            cache_ttl_seconds: Cache TTL in seconds (default: 1 hour)
            enable_cache: Enable result caching
        """
        self.athena_database = athena_database
        self.s3_output_location = s3_output_location
        self.region = region
        self.cache_ttl_seconds = cache_ttl_seconds
        self.enable_cache = enable_cache

        self.athena = boto3.client('athena', region_name=region)
        self.s3 = boto3.client('s3', region_name=region)

        # In-memory cache (for demo; use Redis/ElastiCache in production)
        self._cache: Dict[str, tuple[QueryResult, datetime]] = {}

    def execute_query(
        self,
        sql: str,
        workload: Optional[str] = None,
        nl_query: Optional[str] = None,
        max_results: int = 1000
    ) -> QueryResult:
        """
        Execute SQL query via Athena.

        Args:
            sql: SQL query to execute
            workload: Optional workload name (for SynoDB)
            nl_query: Optional natural language query (for SynoDB)
            max_results: Maximum number of rows to return

        Returns:
            QueryResult with execution status and data

        Example:
            >>> executor = QueryExecutor(
            ...     athena_database="financial_portfolios_db",
            ...     s3_output_location="s3://my-bucket/athena-results/"
            ... )
            >>> result = executor.execute_query("SELECT COUNT(*) FROM positions")
            >>> result.status
            'success'
            >>> result.row_count >= 0
            True
        """
        query_id = self._generate_query_id(sql)

        # Check cache
        if self.enable_cache:
            cached_result = self._get_from_cache(query_id)
            if cached_result:
                return cached_result

        # Execute query
        start_time = time.time()

        try:
            # Start Athena query execution
            response = self.athena.start_query_execution(
                QueryString=sql,
                QueryExecutionContext={'Database': self.athena_database},
                ResultConfiguration={'OutputLocation': self.s3_output_location}
            )

            query_execution_id = response['QueryExecutionId']

            # Wait for query to complete
            result = self._wait_for_query_completion(query_execution_id)

            execution_time_ms = int((time.time() - start_time) * 1000)

            if result['status'] == 'success':
                # Fetch results
                columns, rows = self._fetch_query_results(query_execution_id, max_results)

                query_result = QueryResult(
                    query_id=query_id,
                    sql=sql,
                    status='success',
                    row_count=len(rows),
                    columns=columns,
                    rows=rows,
                    execution_time_ms=execution_time_ms,
                    from_cache=False,
                    athena_query_execution_id=query_execution_id
                )

                # Cache result
                if self.enable_cache:
                    self._put_in_cache(query_id, query_result)

                # Save to SynoDB if workload provided
                if workload and nl_query:
                    self._save_to_synodb(
                        nl_query=nl_query,
                        sql=sql,
                        workload=workload,
                        tables_used=self._extract_tables_from_sql(sql),
                        success=True,
                        execution_time_ms=execution_time_ms
                    )

                return query_result

            else:
                # Query failed
                error_message = result.get('error_message', 'Unknown error')

                query_result = QueryResult(
                    query_id=query_id,
                    sql=sql,
                    status='failed',
                    row_count=0,
                    error_message=error_message,
                    execution_time_ms=execution_time_ms,
                    athena_query_execution_id=query_execution_id
                )

                return query_result

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)

            return QueryResult(
                query_id=query_id,
                sql=sql,
                status='failed',
                row_count=0,
                error_message=str(e),
                execution_time_ms=execution_time_ms
            )

    def execute_generated_query(
        self,
        generation_result: SQLGenerationResult,
        workload: str,
        nl_query: str,
        max_results: int = 1000
    ) -> QueryResult:
        """
        Execute SQL generated by SQLGenerator.

        Args:
            generation_result: Result from SQLGenerator
            workload: Workload name
            nl_query: Original natural language query
            max_results: Maximum rows to return

        Returns:
            QueryResult

        Example:
            >>> executor = QueryExecutor(...)
            >>> generator = SQLGenerator(...)
            >>> gen_result = generator.generate_sql("What is total revenue?", "sales", "sales_db")
            >>> exec_result = executor.execute_generated_query(gen_result, "sales", "What is total revenue?")
        """
        return self.execute_query(
            sql=generation_result.sql,
            workload=workload,
            nl_query=nl_query,
            max_results=max_results
        )

    def _wait_for_query_completion(
        self,
        query_execution_id: str,
        max_wait_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        Wait for Athena query to complete.

        Args:
            query_execution_id: Athena query execution ID
            max_wait_seconds: Maximum wait time in seconds

        Returns:
            Dict with status and error_message (if failed)
        """
        start_time = time.time()

        while True:
            response = self.athena.get_query_execution(
                QueryExecutionId=query_execution_id
            )

            state = response['QueryExecution']['Status']['State']

            if state == 'SUCCEEDED':
                return {'status': 'success'}

            elif state in ['FAILED', 'CANCELLED']:
                error_message = response['QueryExecution']['Status'].get(
                    'StateChangeReason',
                    'Query failed'
                )
                return {'status': 'failed', 'error_message': error_message}

            elif state in ['QUEUED', 'RUNNING']:
                # Check timeout
                if time.time() - start_time > max_wait_seconds:
                    return {
                        'status': 'failed',
                        'error_message': f'Query timeout after {max_wait_seconds}s'
                    }

                # Wait before polling again
                time.sleep(2)

            else:
                return {'status': 'failed', 'error_message': f'Unknown state: {state}'}

    def _fetch_query_results(
        self,
        query_execution_id: str,
        max_results: int
    ) -> tuple[List[str], List[Dict[str, Any]]]:
        """
        Fetch query results from Athena.

        Args:
            query_execution_id: Athena query execution ID
            max_results: Maximum rows to return

        Returns:
            (columns, rows) where rows is list of dicts
        """
        # Get results
        response = self.athena.get_query_results(
            QueryExecutionId=query_execution_id,
            MaxResults=max_results
        )

        # Extract column names
        column_info = response['ResultSet']['ResultSetMetadata']['ColumnInfo']
        columns = [col['Name'] for col in column_info]

        # Extract rows (skip header row)
        rows = []
        for row in response['ResultSet']['Rows'][1:]:  # Skip header
            row_data = {}
            for i, col in enumerate(columns):
                value = row['Data'][i].get('VarCharValue')
                row_data[col] = value
            rows.append(row_data)

        # Handle pagination if needed
        while 'NextToken' in response and len(rows) < max_results:
            response = self.athena.get_query_results(
                QueryExecutionId=query_execution_id,
                MaxResults=max_results - len(rows),
                NextToken=response['NextToken']
            )

            for row in response['ResultSet']['Rows']:
                row_data = {}
                for i, col in enumerate(columns):
                    value = row['Data'][i].get('VarCharValue')
                    row_data[col] = value
                rows.append(row_data)

        return columns, rows

    def _generate_query_id(self, sql: str) -> str:
        """Generate deterministic query ID from SQL."""
        hash_obj = hashlib.md5(sql.strip().encode('utf-8'))
        return f"query_{hash_obj.hexdigest()[:16]}"

    def _get_from_cache(self, query_id: str) -> Optional[QueryResult]:
        """Get query result from cache if not expired."""
        if query_id in self._cache:
            result, cached_at = self._cache[query_id]

            # Check if expired
            if datetime.now() - cached_at < timedelta(seconds=self.cache_ttl_seconds):
                # Mark as cached
                result.from_cache = True
                result.status = 'cached'
                return result
            else:
                # Expired, remove from cache
                del self._cache[query_id]

        return None

    def _put_in_cache(self, query_id: str, result: QueryResult):
        """Put query result in cache."""
        self._cache[query_id] = (result, datetime.now())

    def _save_to_synodb(
        self,
        nl_query: str,
        sql: str,
        workload: str,
        tables_used: List[str],
        success: bool,
        execution_time_ms: int
    ):
        """Save successful query to SynoDB."""
        try:
            loader = SynoDBLoader(region=self.region)
            loader.save_learned_query(
                nl_query=nl_query,
                sql=sql,
                workload=workload,
                tables_used=tables_used,
                success=success,
                execution_time_ms=execution_time_ms
            )
        except Exception as e:
            # Don't fail the query if SynoDB save fails
            print(f"Warning: Failed to save query to SynoDB: {e}")

    def _extract_tables_from_sql(self, sql: str) -> List[str]:
        """Extract table names from SQL (simple heuristic)."""
        import re

        # Remove comments
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)

        # Find patterns: FROM table, JOIN table
        patterns = [
            r'\bFROM\s+([a-zA-Z0-9_\.]+)',
            r'\bJOIN\s+([a-zA-Z0-9_\.]+)'
        ]

        tables = set()
        for pattern in patterns:
            matches = re.findall(pattern, sql, re.IGNORECASE)
            for match in matches:
                # Extract table name (remove database/schema prefix if present)
                table = match.split('.')[-1]
                tables.add(table)

        return list(tables)

    def clear_cache(self):
        """Clear result cache."""
        self._cache.clear()


def execute_nl_query(
    nl_query: str,
    workload: str,
    database: str,
    neptune_endpoint: str,
    athena_database: str,
    s3_output_location: str,
    region: str = 'us-east-1',
    max_results: int = 1000
) -> tuple[SQLGenerationResult, QueryResult]:
    """
    Complete end-to-end: NL query → SQL generation → execution.

    Args:
        nl_query: Natural language query
        workload: Workload name
        database: Database name (for metadata)
        neptune_endpoint: Neptune cluster endpoint
        athena_database: Athena database name (for execution)
        s3_output_location: S3 path for Athena results
        region: AWS region
        max_results: Maximum rows to return

    Returns:
        (generation_result, execution_result)

    Example:
        >>> gen_result, exec_result = execute_nl_query(
        ...     nl_query="What is total revenue by region?",
        ...     workload="sales",
        ...     database="sales_db",
        ...     neptune_endpoint="my-neptune.cluster.amazonaws.com",
        ...     athena_database="sales_db",
        ...     s3_output_location="s3://my-bucket/athena-results/"
        ... )
        >>> exec_result.status
        'success'
        >>> len(exec_result.rows) > 0
        True
    """
    from shared.analysis_agent.sql_generator import SQLGenerator

    # Generate SQL
    with SQLGenerator(neptune_endpoint, region=region) as generator:
        gen_result = generator.generate_sql(
            nl_query=nl_query,
            workload=workload,
            database=database
        )

    # Execute SQL
    executor = QueryExecutor(
        athena_database=athena_database,
        s3_output_location=s3_output_location,
        region=region
    )

    exec_result = executor.execute_generated_query(
        generation_result=gen_result,
        workload=workload,
        nl_query=nl_query,
        max_results=max_results
    )

    return gen_result, exec_result
