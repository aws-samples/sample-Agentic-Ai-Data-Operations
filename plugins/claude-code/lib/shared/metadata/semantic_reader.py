"""
Semantic YAML Reader

Reads semantic.yaml business context files from workload directories.
"""

import yaml
from typing import Dict, Any
from pathlib import Path


def read_semantic_yaml(workload: str) -> Dict[str, Any]:
    """
    Read semantic.yaml for a workload.

    Args:
        workload: Workload name (e.g., "financial_portfolios")

    Returns:
        Dict with parsed semantic.yaml content

    Raises:
        FileNotFoundError: If semantic.yaml not found
        yaml.YAMLError: If YAML parsing fails

    Example:
        >>> semantic = read_semantic_yaml("financial_portfolios")
        >>> semantic['workload']
        'financial_portfolios'
        >>> len(semantic['tables'])
        3
    """
    path = Path(f"workloads/{workload}/config/semantic.yaml")

    if not path.exists():
        raise FileNotFoundError(
            f"semantic.yaml not found at {path}. "
            f"Expected path: workloads/{workload}/config/semantic.yaml"
        )

    with open(path, 'r', encoding='utf-8') as f:
        try:
            return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Failed to parse {path}: {e}")


def validate_semantic_yaml(semantic: Dict[str, Any]) -> bool:
    """
    Validate semantic.yaml structure.

    Args:
        semantic: Parsed semantic.yaml content

    Returns:
        True if valid

    Raises:
        ValueError: If structure is invalid
    """
    # Required top-level keys
    if 'workload' not in semantic:
        raise ValueError("Missing required field: 'workload'")

    if 'tables' not in semantic or not isinstance(semantic['tables'], list):
        raise ValueError("Missing or invalid 'tables' field (must be a list)")

    # Validate each table
    for i, table in enumerate(semantic['tables']):
        if 'name' not in table:
            raise ValueError(f"Table {i}: missing 'name' field")

        if 'table_type' not in table:
            raise ValueError(f"Table {i} ({table.get('name')}): missing 'table_type' field")

        if table['table_type'] not in ['fact', 'dimension', 'reference']:
            raise ValueError(
                f"Table {table.get('name')}: invalid table_type '{table['table_type']}' "
                "(must be 'fact', 'dimension', or 'reference')"
            )

        if 'grain' not in table:
            raise ValueError(f"Table {table.get('name')}: missing 'grain' field")

        if 'primary_key' not in table:
            raise ValueError(f"Table {table.get('name')}: missing 'primary_key' field")

        if 'columns' not in table or not isinstance(table['columns'], list):
            raise ValueError(f"Table {table.get('name')}: missing or invalid 'columns' field")

        # Validate columns
        for j, col in enumerate(table['columns']):
            if 'name' not in col:
                raise ValueError(f"Table {table.get('name')}, column {j}: missing 'name' field")

            if 'role' not in col:
                raise ValueError(f"Table {table.get('name')}, column {col.get('name')}: missing 'role' field")

            if col['role'] not in ['measure', 'dimension', 'temporal', 'identifier', 'attribute']:
                raise ValueError(
                    f"Table {table.get('name')}, column {col.get('name')}: "
                    f"invalid role '{col['role']}' "
                    "(must be 'measure', 'dimension', 'temporal', 'identifier', or 'attribute')"
                )

    return True


def get_table_from_semantic(semantic: Dict[str, Any], table_name: str) -> Dict[str, Any]:
    """
    Get specific table definition from semantic.yaml.

    Args:
        semantic: Parsed semantic.yaml content
        table_name: Name of table to retrieve

    Returns:
        Table definition dict

    Raises:
        KeyError: If table not found
    """
    for table in semantic.get('tables', []):
        if table['name'] == table_name:
            return table

    raise KeyError(f"Table '{table_name}' not found in semantic.yaml")
