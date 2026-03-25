"""
SQL Generator

Generate SQL from natural language queries using:
1. Neptune metadata (table schemas, column roles, relationships)
2. SynoDB similar queries (learned patterns)
3. AWS Bedrock Claude (LLM reasoning)
"""

import boto3
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from shared.analysis_agent.nl_parser import NLQueryParser, QueryIntent
from shared.analysis_agent.neptune_search import NeptuneSemanticSearch
from shared.synodb.search import SynoDBSearch


@dataclass
class SQLGenerationResult:
    """Result of SQL generation."""
    sql: str
    explanation: str
    tables_used: List[str]
    confidence: float
    metadata_used: Dict[str, Any]
    similar_queries: List[Dict[str, Any]]


class SQLGenerator:
    """Generate SQL from natural language queries."""

    def __init__(
        self,
        neptune_endpoint: str,
        region: str = 'us-east-1',
        model_id: str = 'anthropic.claude-3-sonnet-20240229-v1:0'
    ):
        """
        Initialize SQL generator.

        Args:
            neptune_endpoint: Neptune cluster endpoint
            region: AWS region
            model_id: Claude model ID for SQL generation
        """
        self.region = region
        self.model_id = model_id

        self.bedrock_runtime = boto3.client('bedrock-runtime', region_name=region)
        self.nl_parser = NLQueryParser(region=region)
        self.neptune_search = NeptuneSemanticSearch(neptune_endpoint, region=region)
        self.synodb_search = SynoDBSearch(region=region)

    def generate_sql(
        self,
        nl_query: str,
        workload: str,
        database: str,
        limit: Optional[int] = 10000
    ) -> SQLGenerationResult:
        """
        Generate SQL from natural language query.

        Args:
            nl_query: Natural language query
            workload: Workload name (for SynoDB lookup)
            database: Database name
            limit: Default LIMIT clause

        Returns:
            SQLGenerationResult with generated SQL and metadata

        Example:
            >>> generator = SQLGenerator("my-neptune.cluster.amazonaws.com")
            >>> result = generator.generate_sql(
            ...     "What is the total portfolio value by region?",
            ...     "financial_portfolios",
            ...     "financial_portfolios_db"
            ... )
            >>> "SELECT" in result.sql
            True
            >>> "SUM" in result.sql
            True
        """
        # Step 1: Parse natural language query
        intent = self.nl_parser.parse_query(nl_query)

        # Step 2: Find relevant tables using semantic search
        relevant_tables = self.neptune_search.semantic_search_tables(
            nl_query,
            database=database,
            top_k=3
        )

        if not relevant_tables:
            raise ValueError("No relevant tables found for query")

        # Step 3: Get full metadata for top table(s)
        table_metadata = []
        for table_info in relevant_tables[:2]:  # Top 2 tables
            metadata = self.neptune_search.get_table_metadata(
                database=database,
                table_name=table_info['table_name']
            )
            table_metadata.append(metadata)

        # Step 4: Find similar past queries from SynoDB
        similar_queries = self.synodb_search.find_similar_queries(
            nl_query=nl_query,
            workload=workload,
            top_k=3,
            min_similarity=0.5
        )

        # Step 5: Generate SQL using LLM
        sql, explanation, confidence = self._generate_sql_with_llm(
            nl_query=nl_query,
            intent=intent,
            table_metadata=table_metadata,
            similar_queries=similar_queries,
            database=database,
            limit=limit
        )

        # Extract tables used
        tables_used = [t['table_name'] for t in table_metadata]

        return SQLGenerationResult(
            sql=sql,
            explanation=explanation,
            tables_used=tables_used,
            confidence=confidence,
            metadata_used={'tables': table_metadata, 'intent': intent.to_dict()},
            similar_queries=similar_queries
        )

    def _generate_sql_with_llm(
        self,
        nl_query: str,
        intent: QueryIntent,
        table_metadata: List[Dict[str, Any]],
        similar_queries: List[Dict[str, Any]],
        database: str,
        limit: int
    ) -> tuple[str, str, float]:
        """
        Generate SQL using Claude with metadata and examples.

        Returns:
            (sql, explanation, confidence)
        """
        # Build comprehensive prompt
        prompt = self._build_sql_generation_prompt(
            nl_query=nl_query,
            intent=intent,
            table_metadata=table_metadata,
            similar_queries=similar_queries,
            database=database,
            limit=limit
        )

        # Call Bedrock Claude
        try:
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 4000,
                    "temperature": 0.0  # Deterministic SQL generation
                })
            )

            response_body = json.loads(response['body'].read())
            content = response_body['content'][0]['text']

            # Parse response
            sql, explanation, confidence = self._parse_llm_response(content)

            return sql, explanation, confidence

        except Exception as e:
            raise ValueError(f"Failed to generate SQL: {e}") from e

    def _build_sql_generation_prompt(
        self,
        nl_query: str,
        intent: QueryIntent,
        table_metadata: List[Dict[str, Any]],
        similar_queries: List[Dict[str, Any]],
        database: str,
        limit: int
    ) -> str:
        """Build comprehensive prompt for Claude."""

        # Section 1: Task description
        prompt_parts = [
            "You are a SQL expert. Generate SQL to answer this natural language question.",
            "",
            f"**Question**: {nl_query}",
            ""
        ]

        # Section 2: Parsed intent
        prompt_parts.extend([
            "**Parsed Intent**:",
            f"- Type: {intent.intent_type}",
            f"- Measures: {', '.join(intent.measures) if intent.measures else 'none'}",
            f"- Dimensions: {', '.join(intent.dimensions) if intent.dimensions else 'none'}",
            f"- Filters: {json.dumps(intent.filters) if intent.filters else 'none'}",
            ""
        ])

        # Section 3: Available tables
        prompt_parts.append("**Available Tables**:")
        for table in table_metadata:
            prompt_parts.append(f"\nTable: `{database}.{table['table_name']}`")
            prompt_parts.append(f"- Type: {table['type']} (grain: {table['grain']})")
            prompt_parts.append(f"- Primary key: {', '.join(table['primary_key'])}")

            # Measures
            measures = [c for c in table['columns'] if c['role'] == 'measure']
            if measures:
                prompt_parts.append("- Measures (aggregate these):")
                for col in measures:
                    agg = col.get('default_aggregation', 'SUM')
                    prompt_parts.append(f"  - `{col['name']}` ({col['data_type']}) - default: {agg}")

            # Dimensions
            dimensions = [c for c in table['columns'] if c['role'] == 'dimension']
            if dimensions:
                prompt_parts.append("- Dimensions (group by these):")
                for col in dimensions:
                    prompt_parts.append(f"  - `{col['name']}` ({col['data_type']})")

            # Temporal
            temporal = [c for c in table['columns'] if c['role'] == 'temporal']
            if temporal:
                prompt_parts.append("- Temporal columns:")
                for col in temporal:
                    prompt_parts.append(f"  - `{col['name']}` ({col['data_type']})")

            # Relationships
            if table.get('relationships'):
                prompt_parts.append("- Relationships:")
                for rel in table['relationships']:
                    prompt_parts.append(
                        f"  - JOIN {rel['target_table']} ON {table['table_name']}.{rel['source_column']} = {rel['target_table']}.{rel['target_column']}"
                    )

        prompt_parts.append("")

        # Section 4: Similar queries (few-shot examples)
        if similar_queries:
            prompt_parts.append("**Similar Past Queries** (for pattern reference):")
            for i, query in enumerate(similar_queries[:3], 1):
                prompt_parts.append(f"\n{i}. Question: {query['nl_text']}")
                prompt_parts.append(f"   SQL: {query['sql'][:300]}...")  # Truncate
                if query.get('explanation'):
                    prompt_parts.append(f"   Explanation: {query['explanation']}")
            prompt_parts.append("")

        # Section 5: SQL generation rules
        prompt_parts.extend([
            "**SQL Generation Rules**:",
            "1. Use fully qualified table names: `database.table`",
            "2. For measures with role='measure', use their default_aggregation (SUM/AVG/COUNT)",
            "3. For dimensions, use GROUP BY",
            "4. For temporal columns, use DATE_TRUNC or EXTRACT as needed",
            f"5. Always add LIMIT {limit} for safety",
            "6. Join tables using FK relationships from metadata",
            "7. Use CTEs for complex queries (better readability)",
            "8. Only query columns that exist in the metadata",
            "9. Handle NULLs appropriately (COALESCE for measures)",
            "10. Add meaningful column aliases",
            "",
            "**Output Format**:",
            "Return JSON:",
            "{",
            '  "sql": "SELECT ... FROM ... WHERE ... GROUP BY ... ORDER BY ... LIMIT ...",',
            '  "explanation": "This query calculates X by Y using table Z...",',
            '  "confidence": 0.9',
            "}",
            "",
            "Return ONLY the JSON object, no markdown code blocks."
        ])

        return "\n".join(prompt_parts)

    def _parse_llm_response(self, content: str) -> tuple[str, str, float]:
        """
        Parse Claude response to extract SQL, explanation, confidence.

        Returns:
            (sql, explanation, confidence)
        """
        # Remove markdown code blocks if present
        content = content.strip()
        if content.startswith('```'):
            # Remove opening ```json or ```
            content = content.split('\n', 1)[1] if '\n' in content else content[3:]
        if content.endswith('```'):
            content = content.rsplit('\n', 1)[0] if '\n' in content else content[:-3]

        # Parse JSON
        try:
            result = json.loads(content)
            sql = result.get('sql', '').strip()
            explanation = result.get('explanation', '').strip()
            confidence = float(result.get('confidence', 0.7))

            if not sql:
                raise ValueError("No SQL generated")

            return sql, explanation, confidence

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Fallback: extract SQL from text
            sql = self._extract_sql_from_text(content)
            explanation = "SQL extracted from LLM response"
            confidence = 0.5

            return sql, explanation, confidence

    def _extract_sql_from_text(self, text: str) -> str:
        """Extract SQL statement from text (fallback)."""
        import re

        # Look for SELECT ... ; pattern
        match = re.search(r'SELECT\s+.*?;', text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(0).strip()

        # Look for SELECT ... LIMIT pattern
        match = re.search(r'SELECT\s+.*?LIMIT\s+\d+', text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(0).strip()

        # Return first line starting with SELECT
        for line in text.split('\n'):
            if line.strip().upper().startswith('SELECT'):
                return line.strip()

        raise ValueError("Could not extract SQL from LLM response")

    def close(self):
        """Close Neptune connection."""
        self.neptune_search.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def generate_sql(
    nl_query: str,
    workload: str,
    database: str,
    neptune_endpoint: str,
    region: str = 'us-east-1'
) -> SQLGenerationResult:
    """
    Convenience function to generate SQL.

    Args:
        nl_query: Natural language query
        workload: Workload name
        database: Database name
        neptune_endpoint: Neptune cluster endpoint
        region: AWS region

    Returns:
        SQLGenerationResult

    Example:
        >>> result = generate_sql(
        ...     "What is total revenue by region?",
        ...     "financial_portfolios",
        ...     "financial_portfolios_db",
        ...     "my-neptune.cluster.amazonaws.com"
        ... )
        >>> "SELECT" in result.sql
        True
    """
    with SQLGenerator(neptune_endpoint, region=region) as generator:
        return generator.generate_sql(nl_query, workload, database)
