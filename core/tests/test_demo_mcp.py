"""Regression tests for the live demo MCP contract."""

from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_demo_profile_has_complete_server_set() -> None:
    profile = json.loads(
        (ROOT / "mcp-profiles/demo/profile.json").read_text(encoding="utf-8")
    )
    assert profile["servers"] == [
        "aws-mcp",
        "glue-athena",
        "lakeformation",
        "iam",
        "pii-detection",
        "cloudtrail",
    ]


def test_glue_server_exposes_customer_demo_methods() -> None:
    source = (
        ROOT / "mcp-servers/glue-athena-server/server.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {
        "create_job",
        "update_job",
        "get_job",
        "get_job_run",
        "get_job_runs",
        "stop_job_run",
    } <= functions


def test_glue_lambda_transport_matches_customer_demo_methods() -> None:
    source = (
        ROOT / "mcp-servers/glue-athena-server/lambda_handler.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {
        "create_job",
        "update_job",
        "get_job",
        "get_job_run",
        "get_job_runs",
        "start_job_run",
        "stop_job_run",
    } <= functions


def test_demo_launcher_is_syntax_valid() -> None:
    source = (ROOT / "scripts/mcp_demo.py").read_text(encoding="utf-8")
    ast.parse(source, filename="scripts/mcp_demo.py")
