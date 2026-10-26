"""Render-time and runtime guards added for the Strands reviewer's HIGH findings."""

from __future__ import annotations

import ast
import copy
import re
from pathlib import Path

import pytest

from shared.codegen.exceptions import UnsupportedSpecValueError
from shared.codegen.renderer import render_dry_run
from shared.codegen.spec_loader import load_spec

ROOT = Path(__file__).resolve().parents[3]
WORKLOAD = ROOT / "workloads" / "customer_orders" / "config"
RENDERED_AT = "2026-01-01T00:00:00Z"


def _render(spec: dict, template_id: str, schema_version: str) -> str:
    rendered, _ = render_dry_run(
        spec=spec, spec_hash="0" * 64, template_id=template_id,
        template_version="1.0.0", run_started_at=RENDERED_AT,
        schema_version=schema_version,
    )
    return rendered.decode("utf-8")


def _quality_spec_with(sql: str) -> dict:
    spec, _ = load_spec(WORKLOAD / "quality_rules.yaml", "quality", "v1")
    spec = copy.deepcopy(spec)
    spec["rules"].setdefault("accuracy", []).append({
        "rule_id": "accuracy_probe", "column": "quantity", "check_type": "custom_sql",
        "threshold": 1.0, "severity": "warning", "zone": "silver",
        "params": {"sql": sql}, "description": "probe",
    })
    return spec


@pytest.mark.parametrize("sql", [
    "true); DROP TABLE silver_customer_orders; --",
    "quantity > 0 -- trailing comment",
    "quantity > 0 /* comment */",
    "exists (select 1) or 1=1; CREATE TABLE x AS SELECT 1",
    "quantity > 0 OR (DELETE FROM t)",
])
def test_quality_template_refuses_statement_sql(sql: str) -> None:
    with pytest.raises(UnsupportedSpecValueError, match="custom_sql containing"):
        _render(_quality_spec_with(sql), "quality_check", "v1")


def test_quality_template_still_renders_a_plain_predicate() -> None:
    text = _render(_quality_spec_with("quantity >= 1 AND last_update IS NOT NULL"),
                   "quality_check", "v1")
    # tojson escapes ">" as \u003e, so match the part without it.
    assert "AND last_update IS NOT NULL" in text


def _s3_guard() -> callable:
    spec, _ = load_spec(WORKLOAD / "bronze.yaml", "bronze", "v2")
    tree = ast.parse(_render(spec, "bronze_ingestion", "v2"))
    keep = [
        node for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name == "_require_s3_uri")
        or (isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_S3_BUCKET" for t in node.targets))
    ]
    assert len(keep) == 2, "rendered bronze script lost its S3 URI guard"
    namespace: dict = {"re": re, "urlparse": __import__("urllib.parse").parse.urlparse}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "<guard>", "exec"), namespace)  # noqa: S102
    return namespace["_require_s3_uri"]


@pytest.mark.parametrize("uri", [
    "s3://\nfile:///etc/passwd",
    "s3://bucket/a\rb",
    "file:///etc/passwd",
    "s3://Bad_Bucket/key",
    "s3://bucket/../other/key",
    "s3:///no-bucket",
])
def test_bronze_guard_rejects_malformed_s3_uris(uri: str) -> None:
    with pytest.raises(ValueError):
        _s3_guard()(uri, "source_path")


@pytest.mark.parametrize("uri", [
    "s3://data-lake-bucket/bronze/customer_orders/",
    "s3a://my.bucket-01/landing/file.csv",
])
def test_bronze_guard_accepts_valid_s3_uris(uri: str) -> None:
    assert _s3_guard()(uri, "source_path") == uri
