"""
QuickSight Dashboard Configuration Utility

Reads analytics.yaml config files and generates QuickSight API payloads.
Used by the Data Onboarding Agent to deploy dashboards from workload configs.

Usage:
    from shared.utils.quicksight_dashboard import (
        generate_dashboard_definition,
        validate_analytics_config,
    )

    # Validate config
    errors = validate_analytics_config("/path/to/analytics.yaml")
    if errors:
        raise ValueError(f"Invalid config: {errors}")

    # Generate QuickSight API payload
    payload = generate_dashboard_definition("/path/to/analytics.yaml")
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

# Valid SQL table name pattern: schema.table or just table (alphanumeric, underscore, dot, hyphen)
_TABLE_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*){0,2}$')


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# Required top-level keys in analytics.yaml
_REQUIRED_TOP_KEYS = {"dashboard", "datasets", "visuals", "permissions", "refresh"}

# Required keys within the dashboard section
_REQUIRED_DASHBOARD_KEYS = {"name", "display_name", "description"}

# Required keys per dataset entry
_REQUIRED_DATASET_KEYS = {"id", "name", "source_table", "import_mode", "columns"}

# Valid import modes
_VALID_IMPORT_MODES = {"SPICE", "DIRECT_QUERY"}

# Required keys per visual entry
_REQUIRED_VISUAL_KEYS = {"id", "title", "type"}

# Valid visual types
_VALID_VISUAL_TYPES = {
    "KPI",
    "BAR_CHART",
    "HORIZONTAL_BAR_CHART",
    "LINE_CHART",
    "PIE_CHART",
    "HEAT_MAP",
    "TABLE",
    "SCATTER_PLOT",
    "AREA_CHART",
    "COMBO_CHART",
    "FUNNEL_CHART",
    "GAUGE_CHART",
    "TREE_MAP",
    "WORD_CLOUD",
    "PIVOT_TABLE",
}

# Required keys per permission entry
_REQUIRED_PERMISSION_KEYS = {"principal_type", "principal_name", "actions"}

# Valid permission roles
_VALID_ROLES = {"VIEWER", "AUTHOR", "OWNER"}

# Required keys per column entry
_REQUIRED_COLUMN_KEYS = {"name", "type"}


def validate_analytics_config(config_path: str) -> list[str]:
    """Validate an analytics.yaml configuration file.

    Args:
        config_path: Absolute path to the analytics.yaml file.

    Returns:
        List of validation error strings. Empty list means valid.
    """
    errors: list[str] = []

    # -- File existence --
    if not os.path.isfile(config_path):
        return [f"Config file not found: {config_path}"]

    # -- Parse YAML --
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        return [f"YAML parse error: {exc}"]

    if not isinstance(config, dict):
        return ["Config must be a YAML mapping (dict) at top level"]

    # -- Top-level keys --
    missing_top = _REQUIRED_TOP_KEYS - set(config.keys())
    if missing_top:
        errors.append(f"Missing top-level keys: {sorted(missing_top)}")
        # Cannot validate further if top-level structure is broken
        return errors

    # -- Dashboard section --
    dashboard = config.get("dashboard", {})
    if not isinstance(dashboard, dict):
        errors.append("'dashboard' must be a mapping")
    else:
        missing_dash = _REQUIRED_DASHBOARD_KEYS - set(dashboard.keys())
        if missing_dash:
            errors.append(f"Missing dashboard keys: {sorted(missing_dash)}")

    # -- Datasets --
    datasets = config.get("datasets", [])
    if not isinstance(datasets, list) or len(datasets) == 0:
        errors.append("'datasets' must be a non-empty list")
    else:
        dataset_ids: set[str] = set()
        for i, ds in enumerate(datasets):
            if not isinstance(ds, dict):
                errors.append(f"datasets[{i}]: must be a mapping")
                continue
            missing_ds = _REQUIRED_DATASET_KEYS - set(ds.keys())
            if missing_ds:
                errors.append(f"datasets[{i}] ({ds.get('id', '?')}): missing keys {sorted(missing_ds)}")
            ds_id = ds.get("id")
            if ds_id:
                if ds_id in dataset_ids:
                    errors.append(f"datasets[{i}]: duplicate id '{ds_id}'")
                dataset_ids.add(ds_id)
            source_table = ds.get("source_table")
            if source_table and not _TABLE_NAME_PATTERN.match(source_table):
                errors.append(
                    f"datasets[{i}] ({ds_id}): invalid source_table '{source_table}' — "
                    f"must match pattern 'schema.table' (alphanumeric and underscores only)"
                )
            mode = ds.get("import_mode")
            if mode and mode not in _VALID_IMPORT_MODES:
                errors.append(f"datasets[{i}] ({ds_id}): invalid import_mode '{mode}', must be one of {_VALID_IMPORT_MODES}")
            # Validate columns
            columns = ds.get("columns", [])
            if isinstance(columns, list):
                for j, col in enumerate(columns):
                    if isinstance(col, dict):
                        missing_col = _REQUIRED_COLUMN_KEYS - set(col.keys())
                        if missing_col:
                            errors.append(f"datasets[{i}].columns[{j}]: missing keys {sorted(missing_col)}")

    # -- Visuals --
    visuals = config.get("visuals", [])
    if not isinstance(visuals, list) or len(visuals) == 0:
        errors.append("'visuals' must be a non-empty list")
    else:
        visual_ids: set[str] = set()
        for i, vis in enumerate(visuals):
            if not isinstance(vis, dict):
                errors.append(f"visuals[{i}]: must be a mapping")
                continue
            missing_vis = _REQUIRED_VISUAL_KEYS - set(vis.keys())
            if missing_vis:
                errors.append(f"visuals[{i}] ({vis.get('id', '?')}): missing keys {sorted(missing_vis)}")
            vis_id = vis.get("id")
            if vis_id:
                if vis_id in visual_ids:
                    errors.append(f"visuals[{i}]: duplicate id '{vis_id}'")
                visual_ids.add(vis_id)
            vis_type = vis.get("type")
            if vis_type and vis_type not in _VALID_VISUAL_TYPES:
                errors.append(f"visuals[{i}] ({vis_id}): invalid type '{vis_type}', must be one of {sorted(_VALID_VISUAL_TYPES)}")
            # Validate dataset reference (TABLE type can use custom_sql with null dataset_id)
            ds_ref = vis.get("dataset_id")
            if ds_ref is not None and datasets and ds_ref not in dataset_ids:
                errors.append(f"visuals[{i}] ({vis_id}): dataset_id '{ds_ref}' not found in datasets")
            # TABLE type with null dataset_id must have custom_sql
            if ds_ref is None and vis_type == "TABLE" and not vis.get("custom_sql"):
                errors.append(f"visuals[{i}] ({vis_id}): TABLE with null dataset_id must have 'custom_sql'")

    # -- Permissions --
    permissions = config.get("permissions", [])
    if not isinstance(permissions, list) or len(permissions) == 0:
        errors.append("'permissions' must be a non-empty list")
    else:
        for i, perm in enumerate(permissions):
            if not isinstance(perm, dict):
                errors.append(f"permissions[{i}]: must be a mapping")
                continue
            missing_perm = _REQUIRED_PERMISSION_KEYS - set(perm.keys())
            if missing_perm:
                errors.append(f"permissions[{i}]: missing keys {sorted(missing_perm)}")
            role = perm.get("role")
            if role and role not in _VALID_ROLES:
                errors.append(f"permissions[{i}]: invalid role '{role}', must be one of {_VALID_ROLES}")
            actions = perm.get("actions", [])
            if not isinstance(actions, list) or len(actions) == 0:
                errors.append(f"permissions[{i}]: 'actions' must be a non-empty list")

    # -- Refresh --
    refresh = config.get("refresh", {})
    if not isinstance(refresh, dict):
        errors.append("'refresh' must be a mapping")
    else:
        schedule = refresh.get("schedule")
        if not isinstance(schedule, dict) or "cron" not in (schedule or {}):
            errors.append("refresh.schedule must include 'cron'")
        refresh_datasets = refresh.get("datasets", [])
        if not isinstance(refresh_datasets, list):
            errors.append("refresh.datasets must be a list")

    return errors


# ---------------------------------------------------------------------------
# Payload generation
# ---------------------------------------------------------------------------

def _build_dataset_definitions(
    datasets: list[dict[str, Any]],
    aws_account_id: str,
    data_source_arn: str,
) -> list[dict[str, Any]]:
    """Build QuickSight DataSet definitions from config datasets."""
    definitions = []
    for ds in datasets:
        ds_def: dict[str, Any] = {
            "DataSetId": ds["id"],
            "Name": ds["name"],
            "ImportMode": ds["import_mode"],
            "PhysicalTableMap": {
                f"{ds['id']}_physical": {
                    "CustomSql": {
                        "DataSourceArn": data_source_arn,
                        "Name": ds["name"],
                        "SqlQuery": f"SELECT * FROM {_safe_table_name(ds['source_table'])}",
                        "Columns": [
                            {
                                "Name": col["name"],
                                "Type": _map_column_type(col["type"]),
                            }
                            for col in ds.get("columns", [])
                        ],
                    }
                }
            },
        }
        definitions.append(ds_def)
    return definitions


def _safe_table_name(table: str) -> str:
    """Validate and return a safe SQL table name. Raises on injection attempts."""
    if not _TABLE_NAME_PATTERN.match(table):
        raise ValueError(f"Invalid table name '{table}' — possible SQL injection")
    return table


def _map_column_type(yaml_type: str) -> str:
    """Map analytics.yaml column types to QuickSight column types."""
    mapping = {
        "STRING": "STRING",
        "INTEGER": "INTEGER",
        "DECIMAL": "DECIMAL",
        "DATE": "DATETIME",
        "DATETIME": "DATETIME",
        "BOOLEAN": "BIT",
    }
    return mapping.get(yaml_type.upper(), "STRING")


def _build_visual_definition(vis: dict[str, Any]) -> dict[str, Any]:
    """Build a single QuickSight visual definition from config."""
    visual_def: dict[str, Any] = {
        "VisualId": vis["id"],
        "Title": {"Visibility": "VISIBLE", "FormatText": {"PlainText": vis["title"]}},
    }

    vis_type = vis["type"]

    if vis_type == "KPI":
        visual_def["KPIVisual"] = {
            "VisualId": vis["id"],
            "Title": visual_def["Title"],
            "ChartConfiguration": {
                "FieldWells": {
                    "Values": [
                        {"Expression": m["expression"], "Label": m.get("label", "")}
                        for m in vis.get("measures", [])
                    ]
                }
            },
        }
    elif vis_type in ("BAR_CHART", "HORIZONTAL_BAR_CHART"):
        visual_def["BarChartVisual"] = {
            "VisualId": vis["id"],
            "Title": visual_def["Title"],
            "ChartConfiguration": {
                "Orientation": "VERTICAL" if vis_type == "BAR_CHART" else "HORIZONTAL",
                "FieldWells": {
                    "Category": [
                        {"Column": d["column"], "Label": d.get("label", "")}
                        for d in vis.get("dimensions", [])
                    ],
                    "Values": [
                        {"Expression": m["expression"], "Label": m.get("label", "")}
                        for m in vis.get("measures", [])
                    ],
                },
            },
        }
    elif vis_type == "LINE_CHART":
        visual_def["LineChartVisual"] = {
            "VisualId": vis["id"],
            "Title": visual_def["Title"],
            "ChartConfiguration": {
                "FieldWells": {
                    "Category": [
                        {
                            "Column": d["column"],
                            "Label": d.get("label", ""),
                            "DateGranularity": d.get("granularity", "MONTH"),
                        }
                        for d in vis.get("dimensions", [])
                    ],
                    "Values": [
                        {"Expression": m["expression"], "Label": m.get("label", "")}
                        for m in vis.get("measures", [])
                    ],
                }
            },
        }
    elif vis_type == "PIE_CHART":
        visual_def["PieChartVisual"] = {
            "VisualId": vis["id"],
            "Title": visual_def["Title"],
            "ChartConfiguration": {
                "FieldWells": {
                    "Category": [
                        {"Column": d["column"], "Label": d.get("label", "")}
                        for d in vis.get("dimensions", [])
                    ],
                    "Size": [
                        {"Expression": m["expression"], "Label": m.get("label", "")}
                        for m in vis.get("measures", [])
                    ],
                }
            },
        }
    elif vis_type == "HEAT_MAP":
        dims = vis.get("dimensions", [])
        rows = [d for d in dims if d.get("axis") == "ROW"]
        cols = [d for d in dims if d.get("axis") == "COLUMN"]
        visual_def["HeatMapVisual"] = {
            "VisualId": vis["id"],
            "Title": visual_def["Title"],
            "ChartConfiguration": {
                "FieldWells": {
                    "Rows": [
                        {"Column": d["column"], "Label": d.get("label", "")}
                        for d in rows
                    ],
                    "Columns": [
                        {"Column": d["column"], "Label": d.get("label", "")}
                        for d in cols
                    ],
                    "Values": [
                        {"Expression": m["expression"], "Label": m.get("label", "")}
                        for m in vis.get("measures", [])
                    ],
                }
            },
        }
    elif vis_type == "TABLE":
        table_config: dict[str, Any] = {
            "VisualId": vis["id"],
            "Title": visual_def["Title"],
            "ChartConfiguration": {},
        }
        if vis.get("custom_sql"):
            table_config["ChartConfiguration"]["CustomSql"] = vis["custom_sql"]
        if vis.get("columns_display"):
            table_config["ChartConfiguration"]["FieldOptions"] = [
                {
                    "FieldId": col["name"],
                    "Label": col.get("label", col["name"]),
                    "Width": str(col.get("width", 100)) + "px",
                }
                for col in vis["columns_display"]
            ]
        if vis.get("sort"):
            table_config["ChartConfiguration"]["SortConfiguration"] = {
                "FieldSortOptions": [
                    {
                        "FieldId": vis["sort"]["column"],
                        "Direction": vis["sort"].get("direction", "DESC"),
                    }
                ]
            }
        visual_def["TableVisual"] = table_config
    else:
        # Generic fallback for other visual types
        visual_def["GenericVisual"] = {
            "VisualId": vis["id"],
            "Title": visual_def["Title"],
            "Type": vis_type,
        }

    return visual_def


def _build_filter_definitions(visuals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract filter definitions from visuals."""
    filters: list[dict[str, Any]] = []
    for vis in visuals:
        for filt in vis.get("filters", []):
            if not filt or filt.get("column") is None:
                continue
            filter_def: dict[str, Any] = {
                "FilterId": f"{vis['id']}_{filt['column']}",
                "Column": filt["column"],
                "Operator": filt.get("operator", "EQUALS"),
                "Values": filt.get("values", []),
                "Scope": {"VisualIds": [vis["id"]]},
            }
            filters.append(filter_def)
    return filters


def _build_permissions(permissions: list[dict[str, Any]], aws_account_id: str) -> list[dict[str, Any]]:
    """Build QuickSight permission grants."""
    grants = []
    for perm in permissions:
        principal_type = perm["principal_type"].lower()
        principal_name = perm["principal_name"]
        # QuickSight principal ARN format
        arn = f"arn:aws:quicksight:us-east-1:{aws_account_id}:{principal_type}/{principal_name}"
        grants.append(
            {
                "Principal": arn,
                "Actions": perm["actions"],
            }
        )
    return grants


def generate_dashboard_definition(
    config_path: str,
    aws_account_id: str | None = None,
    data_source_arn: str | None = None,
) -> dict[str, Any]:
    """Generate a QuickSight CreateDashboard API payload from analytics.yaml.

    Args:
        config_path: Absolute path to the analytics.yaml file.
        aws_account_id: AWS account ID. If None, uses placeholder for validation.
        data_source_arn: QuickSight data source ARN. If None, uses placeholder.

    Returns:
        Dict matching the QuickSight CreateDashboard API structure.

    Raises:
        FileNotFoundError: If config_path does not exist.
        ValueError: If config validation fails.
    """
    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    # Validate first
    errors = validate_analytics_config(config_path)
    if errors:
        raise ValueError(f"Config validation failed: {errors}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Defaults for optional parameters (use placeholders if not provided)
    account_id = aws_account_id or "PLACEHOLDER_ACCOUNT_ID"
    ds_arn = data_source_arn or f"arn:aws:quicksight:us-east-1:{account_id}:datasource/athena-gold"

    dashboard = config["dashboard"]
    datasets = config["datasets"]
    visuals = config["visuals"]
    permissions = config["permissions"]
    refresh = config["refresh"]

    dashboard_id = dashboard["name"]

    # -- Build payload --
    payload: dict[str, Any] = {
        "AwsAccountId": account_id,
        "DashboardId": dashboard_id,
        "Name": dashboard["display_name"],
        "Permissions": _build_permissions(permissions, account_id),
        "DashboardPublishOptions": {
            "AdHocFilteringOption": {"AvailabilityStatus": "ENABLED"},
            "ExportToCSVOption": {"AvailabilityStatus": "ENABLED"},
            "SheetLayoutElementMaximizationOption": {"AvailabilityStatus": "ENABLED"},
        },
        "Definition": {
            "DataSetIdentifierDeclarations": [
                {
                    "Identifier": ds["id"],
                    "DataSetArn": f"arn:aws:quicksight:us-east-1:{account_id}:dataset/{ds['id']}",
                }
                for ds in datasets
            ],
            "Sheets": [
                {
                    "SheetId": "main-sheet",
                    "Name": dashboard["display_name"],
                    "Visuals": [_build_visual_definition(vis) for vis in visuals],
                    "FilterControls": [],
                    "Layouts": [
                        {
                            "Configuration": {
                                "GridLayout": {
                                    "Elements": [
                                        {
                                            "ElementId": vis["id"],
                                            "ElementType": "VISUAL",
                                            "ColumnIndex": vis.get("position", {}).get("col", 0),
                                            "RowIndex": vis.get("position", {}).get("row", 0),
                                            "ColumnSpan": vis.get("position", {}).get("width", 12),
                                            "RowSpan": vis.get("position", {}).get("height", 4),
                                        }
                                        for vis in visuals
                                    ]
                                }
                            }
                        }
                    ],
                }
            ],
            "FilterDefinitions": _build_filter_definitions(visuals),
        },
        "Tags": [
            {"Key": "workload", "Value": dashboard.get("name", "")},
            {"Key": "managed-by", "Value": "data-onboarding-agent"},
        ] + [
            {"Key": "tag", "Value": tag}
            for tag in dashboard.get("tags", [])
        ],
    }

    # -- Add dataset definitions as a separate key for the caller --
    payload["_DataSetDefinitions"] = _build_dataset_definitions(datasets, account_id, ds_arn)

    # -- Add SPICE refresh schedule --
    spice_datasets = [
        rd for rd in refresh.get("datasets", []) if rd.get("import_mode") == "SPICE"
    ]
    if spice_datasets:
        payload["_RefreshSchedule"] = {
            "Cron": refresh["schedule"]["cron"],
            "Timezone": refresh["schedule"].get("timezone", "UTC"),
            "DataSetIds": [rd["dataset_id"] for rd in spice_datasets],
        }

    return payload
