"""
Local Filesystem MCP Server

Provides MCP interface for reading/writing workload configuration files.
Used by Router Agent and Data Onboarding Agent to check existing workloads.
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, List

from fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("local-filesystem")

# Base path for workloads
BASE_PATH = Path(os.getenv('BASE_PATH', '/path/to/claude-data-operations'))


@mcp.tool()
def list_workloads() -> Dict[str, Any]:
    """
    List all existing workload directories.

    Returns:
        List of workload names with basic info
    """
    try:
        workloads_dir = BASE_PATH / "workloads"

        if not workloads_dir.exists():
            return {
                "status": "success",
                "workloads": [],
                "message": "No workloads directory found"
            }

        workloads = []
        for item in workloads_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                workload_info = {
                    "name": item.name,
                    "path": str(item),
                    "has_config": (item / "config").exists(),
                    "has_dags": (item / "dags").exists(),
                    "has_tests": (item / "tests").exists()
                }

                # Try to read source.yaml for additional info
                source_yaml = item / "config" / "source.yaml"
                if source_yaml.exists():
                    with open(source_yaml, 'r') as f:
                        source_config = yaml.safe_load(f)
                        workload_info["source_type"] = source_config.get("source", {}).get("type")
                        workload_info["location"] = source_config.get("source", {}).get("location")

                workloads.append(workload_info)

        return {
            "status": "success",
            "workloads": workloads,
            "count": len(workloads)
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@mcp.tool()
def get_workload_config(workload_name: str, config_file: str) -> Dict[str, Any]:
    """
    Read a specific configuration file from a workload.

    Args:
        workload_name: Name of the workload
        config_file: Config file name (e.g., 'source.yaml', 'semantic.yaml')

    Returns:
        Configuration content
    """
    try:
        config_path = BASE_PATH / "workloads" / workload_name / "config" / config_file

        if not config_path.exists():
            return {
                "status": "error",
                "workload": workload_name,
                "config_file": config_file,
                "error": f"Config file not found: {config_path}"
            }

        with open(config_path, 'r') as f:
            if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                config_content = yaml.safe_load(f)
            elif config_file.endswith('.json'):
                import json
                config_content = json.load(f)
            else:
                config_content = f.read()

        return {
            "status": "success",
            "workload": workload_name,
            "config_file": config_file,
            "config": config_content
        }

    except Exception as e:
        return {
            "status": "error",
            "workload": workload_name,
            "config_file": config_file,
            "error": str(e)
        }


@mcp.tool()
def search_workloads_by_source(
    source_type: str = None,
    location_pattern: str = None
) -> Dict[str, Any]:
    """
    Search for workloads matching source criteria (deduplication check).

    Args:
        source_type: Source type (e.g., 's3', 'rds', 'api')
        location_pattern: Pattern to match in source location (e.g., 'sales')

    Returns:
        List of matching workloads
    """
    try:
        all_workloads = list_workloads()

        if all_workloads['status'] == 'error':
            return all_workloads

        matching = []
        for workload in all_workloads['workloads']:
            match = True

            if source_type and workload.get('source_type') != source_type:
                match = False

            if location_pattern and 'location' in workload:
                if location_pattern.lower() not in workload['location'].lower():
                    match = False

            if match:
                matching.append(workload)

        return {
            "status": "success",
            "matches": matching,
            "count": len(matching),
            "search_criteria": {
                "source_type": source_type,
                "location_pattern": location_pattern
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@mcp.tool()
def write_workload_config(
    workload_name: str,
    config_file: str,
    config_content: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Write a configuration file for a workload.

    Args:
        workload_name: Name of the workload
        config_file: Config file name (e.g., 'source.yaml')
        config_content: Configuration content to write

    Returns:
        Confirmation of write operation
    """
    try:
        config_dir = BASE_PATH / "workloads" / workload_name / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_path = config_dir / config_file

        with open(config_path, 'w') as f:
            if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                yaml.dump(config_content, f, default_flow_style=False, sort_keys=False)
            elif config_file.endswith('.json'):
                import json
                json.dump(config_content, f, indent=2)
            else:
                f.write(str(config_content))

        return {
            "status": "success",
            "workload": workload_name,
            "config_file": config_file,
            "path": str(config_path),
            "message": f"Config written to {config_path}"
        }

    except Exception as e:
        return {
            "status": "error",
            "workload": workload_name,
            "config_file": config_file,
            "error": str(e)
        }


@mcp.tool()
def read_file(file_path: str) -> Dict[str, Any]:
    """
    Read any file within the project directory.

    Args:
        file_path: Relative path from BASE_PATH

    Returns:
        File content
    """
    try:
        full_path = BASE_PATH / file_path

        if not full_path.exists():
            return {
                "status": "error",
                "file_path": file_path,
                "error": "File not found"
            }

        # Security check: ensure path is within BASE_PATH
        if not str(full_path.resolve()).startswith(str(BASE_PATH.resolve())):
            return {
                "status": "error",
                "file_path": file_path,
                "error": "Access denied: path outside BASE_PATH"
            }

        with open(full_path, 'r') as f:
            content = f.read()

        return {
            "status": "success",
            "file_path": file_path,
            "content": content
        }

    except Exception as e:
        return {
            "status": "error",
            "file_path": file_path,
            "error": str(e)
        }


if __name__ == "__main__":
    # Run MCP server
    mcp.run()
