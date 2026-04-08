"""
Natural Language Query Parser

Uses AWS Bedrock Claude to extract query intent from natural language.
"""

import boto3
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from botocore.exceptions import ClientError

from shared.utils.prompt_sanitizer import sanitize_identifier, sanitize_user_query


@dataclass
class QueryIntent:
    """Parsed query intent from natural language."""

    # Core intent
    intent_type: str  # 'aggregation', 'filtering', 'join', 'time-series', 'comparison', 'ranking'
    entities: List[str] = field(default_factory=list)  # Table names, column names, business terms

    # Query structure
    measures: List[str] = field(default_factory=list)  # Columns to aggregate
    dimensions: List[str] = field(default_factory=list)  # Columns to group by
    filters: List[Dict[str, Any]] = field(default_factory=list)  # WHERE conditions

    # Time context
    time_column: Optional[str] = None
    time_range: Optional[Dict[str, str]] = None  # {'start': '2023-01-01', 'end': '2023-12-31'}
    time_granularity: Optional[str] = None  # 'day', 'week', 'month', 'quarter', 'year'

    # Ranking/sorting
    order_by: Optional[str] = None  # Column to sort by
    order_direction: str = 'DESC'  # 'ASC' or 'DESC'
    limit: Optional[int] = None

    # Comparison
    comparison_type: Optional[str] = None  # 'period-over-period', 'target-vs-actual', 'segment-comparison'
    baseline_period: Optional[str] = None

    # Confidence
    confidence: float = 0.0  # 0.0 to 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'intent_type': self.intent_type,
            'entities': self.entities,
            'measures': self.measures,
            'dimensions': self.dimensions,
            'filters': self.filters,
            'time_column': self.time_column,
            'time_range': self.time_range,
            'time_granularity': self.time_granularity,
            'order_by': self.order_by,
            'order_direction': self.order_direction,
            'limit': self.limit,
            'comparison_type': self.comparison_type,
            'baseline_period': self.baseline_period,
            'confidence': self.confidence
        }


class NLQueryParser:
    """Parse natural language queries into structured intent."""

    def __init__(
        self,
        region: str = 'us-east-1',
        model_id: str = 'anthropic.claude-3-sonnet-20240229-v1:0'
    ):
        """
        Initialize NL parser with Bedrock Claude.

        Args:
            region: AWS region
            model_id: Claude model ID
        """
        self.region = region
        self.model_id = model_id
        self.bedrock_runtime = boto3.client('bedrock-runtime', region_name=region)

    def parse_query(
        self,
        nl_query: str,
        available_tables: Optional[List[str]] = None,
        available_columns: Optional[Dict[str, List[str]]] = None
    ) -> QueryIntent:
        """
        Parse natural language query into structured intent.

        Args:
            nl_query: Natural language query
            available_tables: Optional list of available table names
            available_columns: Optional dict of {table_name: [column_names]}

        Returns:
            QueryIntent with extracted information

        Example:
            >>> parser = NLQueryParser()
            >>> intent = parser.parse_query("What is the total portfolio value by region?")
            >>> intent.intent_type
            'aggregation'
            >>> 'portfolio' in intent.entities or 'value' in intent.entities
            True
        """
        # Build context for LLM
        context = self._build_context(available_tables, available_columns)

        # Build prompt
        prompt = self._build_prompt(nl_query, context)

        # Call Bedrock Claude
        try:
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2000,
                    "temperature": 0.0  # Deterministic parsing
                })
            )

            response_body = json.loads(response['body'].read())
            content = response_body['content'][0]['text']

            # Parse JSON response
            intent_dict = json.loads(self._extract_json(content))

            # Convert to QueryIntent
            return QueryIntent(
                intent_type=intent_dict.get('intent_type', 'unknown'),
                entities=intent_dict.get('entities', []),
                measures=intent_dict.get('measures', []),
                dimensions=intent_dict.get('dimensions', []),
                filters=intent_dict.get('filters', []),
                time_column=intent_dict.get('time_column'),
                time_range=intent_dict.get('time_range'),
                time_granularity=intent_dict.get('time_granularity'),
                order_by=intent_dict.get('order_by'),
                order_direction=intent_dict.get('order_direction', 'DESC'),
                limit=intent_dict.get('limit'),
                comparison_type=intent_dict.get('comparison_type'),
                baseline_period=intent_dict.get('baseline_period'),
                confidence=intent_dict.get('confidence', 0.8)
            )

        except (ClientError, json.JSONDecodeError, KeyError) as e:
            # Return default intent on error
            return QueryIntent(
                intent_type='unknown',
                entities=self._extract_keywords(nl_query),
                confidence=0.3
            )

    def _build_context(
        self,
        available_tables: Optional[List[str]],
        available_columns: Optional[Dict[str, List[str]]]
    ) -> str:
        """Build context string for LLM."""
        context_parts = []

        if available_tables:
            safe_tables = [sanitize_identifier(t) for t in available_tables]
            context_parts.append(f"Available tables: {', '.join(safe_tables)}")

        if available_columns:
            for table, columns in available_columns.items():
                safe_cols = [sanitize_identifier(c) for c in columns[:20]]
                context_parts.append(f"Columns in {sanitize_identifier(table)}: {', '.join(safe_cols)}")

        return "\n".join(context_parts) if context_parts else "No metadata available."

    def _build_prompt(self, nl_query: str, context: str) -> str:
        """Build prompt for Claude."""
        return f"""You are a SQL query intent parser. Parse the following natural language query and extract structured information.

Context:
{context}

Query: {sanitize_user_query(nl_query)}

Extract the following information and return as JSON:
{{
  "intent_type": "one of: aggregation, filtering, join, time-series, comparison, ranking",
  "entities": ["list of mentioned table names, column names, or business terms"],
  "measures": ["columns to aggregate (e.g., revenue, count, value)"],
  "dimensions": ["columns to group by (e.g., region, product, customer)"],
  "filters": [
    {{"column": "status", "operator": "=", "value": "Active"}},
    {{"column": "date", "operator": ">=", "value": "2023-01-01"}}
  ],
  "time_column": "column name for time-based queries (or null)",
  "time_range": {{"start": "2023-01-01", "end": "2023-12-31"}} or null,
  "time_granularity": "day, week, month, quarter, year, or null",
  "order_by": "column to sort by (or null)",
  "order_direction": "ASC or DESC",
  "limit": 10 or null,
  "comparison_type": "period-over-period, target-vs-actual, segment-comparison, or null",
  "baseline_period": "e.g., 'last year', 'previous quarter', or null",
  "confidence": 0.0 to 1.0
}}

Return ONLY the JSON object, no explanation."""

    def _extract_json(self, text: str) -> str:
        """Extract JSON object from Claude response."""
        # Find JSON block
        start = text.find('{')
        end = text.rfind('}') + 1

        if start == -1 or end == 0:
            raise ValueError("No JSON found in response")

        return text[start:end]

    def _extract_keywords(self, nl_query: str) -> List[str]:
        """Extract basic keywords as fallback (simple tokenization)."""
        import re

        # Remove common words
        stop_words = {
            'what', 'is', 'the', 'of', 'by', 'for', 'in', 'on', 'at', 'to', 'from',
            'show', 'me', 'give', 'get', 'find', 'how', 'many', 'much', 'total',
            'sum', 'avg', 'average', 'count', 'min', 'max', 'a', 'an', 'and', 'or'
        }

        # Tokenize
        words = re.findall(r'\b\w+\b', nl_query.lower())

        # Filter stop words
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        return keywords[:10]  # Limit to 10 keywords


def parse_nl_query(
    nl_query: str,
    region: str = 'us-east-1'
) -> QueryIntent:
    """
    Convenience function to parse a natural language query.

    Args:
        nl_query: Natural language query
        region: AWS region

    Returns:
        QueryIntent

    Example:
        >>> intent = parse_nl_query("Show me monthly revenue by region")
        >>> intent.intent_type in ['aggregation', 'time-series']
        True
    """
    parser = NLQueryParser(region=region)
    return parser.parse_query(nl_query)
