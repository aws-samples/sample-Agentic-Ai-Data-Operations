"""Phase 3 profiling on Strands: read-only AWS tools, Cedar-gated, candidates only."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtimes" / "strands"))

pytest.importorskip("strands", reason="needs the optional strands extra")
pytest.importorskip("cedarpy")

from strands.hooks import BeforeToolCallEvent, HookRegistry  # noqa: E402

import shared.utils.cedar_gate as gate  # noqa: E402
from adop_strands import cli  # noqa: E402
from adop_strands.aws_readonly import (  # noqa: E402
    ReadOnlyViolation, make_readonly_aws_tools, validate_select,
)
from adop_strands.cedar_hook import CedarToolGate  # noqa: E402


@pytest.fixture(autouse=True)
def enforce(tmp_path, monkeypatch):
    mode = tmp_path / "enforcement.json"
    mode.write_text(json.dumps({"mode": "enforce"}))
    monkeypatch.setattr(gate, "MODE_FILE", mode)
    monkeypatch.setattr(gate, "DECISION_LOG", tmp_path / "decisions.jsonl")


# ── SQL is read-only by construction ────────────────────────────────────────


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE orders",
        "SELECT * FROM orders; DROP TABLE orders",
        "INSERT INTO orders SELECT * FROM staging",
        "CREATE TABLE x AS SELECT * FROM orders",
        "SELECT * FROM orders -- comment",
        "SELECT * FROM orders /* x */",
        "UNLOAD (SELECT * FROM orders) TO 's3://b/x'",
        "MSCK REPAIR TABLE orders",
        "WITH t AS (SELECT 1) DELETE FROM orders",
        "",
    ],
)
def test_non_read_sql_is_refused(sql: str) -> None:
    with pytest.raises(ReadOnlyViolation):
        validate_select(sql)


def test_select_is_row_capped() -> None:
    assert validate_select("SELECT * FROM orders").endswith("LIMIT 1000")
    assert validate_select("SELECT * FROM orders LIMIT 5").endswith("LIMIT 5")
    assert validate_select("SELECT * FROM orders LIMIT 999999").endswith("LIMIT 1000")
    assert validate_select("WITH t AS (SELECT 1 AS a) SELECT a FROM t").endswith("LIMIT 1000")


# ── tools call only read APIs ───────────────────────────────────────────────


class Recorder:
    """Fake boto3 client that records every API called on it."""

    def __init__(self, service: str, calls: list) -> None:
        self.service, self.calls = service, calls

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((self.service, name, kwargs))
            return _RESPONSES[(self.service, name)](kwargs)
        if name == "get_paginator":
            return lambda op: type("P", (), {"paginate": lambda _s, **kw: [
                _RESPONSES[(self.service, op)](kw)]})()
        return call


_RESPONSES = {
    ("glue", "get_databases"): lambda kw: {"DatabaseList": [{"Name": "orders_db"}]},
    ("glue", "get_tables"): lambda kw: {"TableList": [{"Name": "orders"}]},
    ("glue", "get_table"): lambda kw: {"Table": {"Name": "orders", "StorageDescriptor": {
        "Columns": [{"Name": "order_id", "Type": "string"}], "Location": "s3://data-bucket/orders/"}}},
    ("s3", "list_objects_v2"): lambda kw: {"Contents": [{"Key": "orders/a.csv", "Size": 10}]},
    ("s3", "get_object"): lambda kw: {"Body": io.BytesIO(b"order_id,amount\n1,2\n")},
    ("athena", "start_query_execution"): lambda kw: {"QueryExecutionId": "q1"},
    ("athena", "get_query_execution"): lambda kw: {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}},
    ("athena", "get_query_results"): lambda kw: {"ResultSet": {"Rows": [
        {"Data": [{"VarCharValue": "n"}]}, {"Data": [{"VarCharValue": "42"}]}]}},
}
READ_APIS = {"get_databases", "get_tables", "get_table", "list_objects_v2", "get_object",
             "start_query_execution", "get_query_execution", "get_query_results"}


def _tools(calls: list, athena_output: str | None = "s3://results/adop/"):
    tools = make_readonly_aws_tools("us-east-1", athena_output, None,
                                    client_factory=lambda svc: Recorder(svc, calls))
    return {t.tool_name: t for t in tools}


def test_every_tool_uses_only_read_apis() -> None:
    calls: list = []
    t = _tools(calls)
    assert t["aws_ro_glue_get_databases"]() == ["orders_db"]
    assert t["aws_ro_glue_get_tables"](database="orders_db") == ["orders"]
    assert t["aws_ro_glue_get_table"](database="orders_db", table="orders")["columns"]
    assert t["aws_ro_s3_list"](prefix_uri="s3://data-bucket/orders/")[0]["key"] == "orders/a.csv"
    assert t["aws_ro_s3_sample"](object_uri="s3://data-bucket/orders/a.csv").startswith("order_id")
    out = t["aws_ro_athena_select"](sql="SELECT count(*) AS n FROM orders", database="orders_db")
    assert out["rows"] == [["42"]] and out["query"].endswith("LIMIT 1000")
    assert {name for _, name, _ in calls} <= READ_APIS


def test_s3_reads_are_bounded() -> None:
    calls: list = []
    t = _tools(calls)
    t["aws_ro_s3_list"](prefix_uri="s3://data-bucket/x/", max_keys=10_000)
    t["aws_ro_s3_sample"](object_uri="s3://data-bucket/x/a.csv", max_bytes=10**9)
    list_call = next(kw for svc, n, kw in calls if n == "list_objects_v2")
    get_call = next(kw for svc, n, kw in calls if n == "get_object")
    assert list_call["MaxKeys"] == 100
    assert get_call["Range"] == f"bytes=0-{256 * 1024 - 1}"


def test_athena_needs_a_human_provided_output_location() -> None:
    t = _tools([], athena_output=None)
    with pytest.raises(ReadOnlyViolation, match="athena-output"):
        t["aws_ro_athena_select"](sql="SELECT 1", database="d")


def test_bad_s3_uris_are_refused() -> None:
    t = _tools([])
    for uri in ("https://b/x", "s3://B/x", "s3://data-bucket/../etc"):
        with pytest.raises(ReadOnlyViolation):
            t["aws_ro_s3_list"](prefix_uri=uri)


# ── Cedar: only the profiler (metadata) may use the read-only AWS tools ─────


def _fire(agent: str, tool: str) -> BeforeToolCallEvent:
    registry = HookRegistry()
    registry.add_hook(CedarToolGate(ROOT, agent))
    event = BeforeToolCallEvent(agent=None, selected_tool=None,
                                tool_use={"toolUseId": "t", "name": tool, "input": {}},
                                invocation_state={})
    registry.invoke_callbacks(event)
    return event


def test_profiler_may_use_read_only_aws_tools() -> None:
    for tool in ("aws_ro_glue_get_table", "aws_ro_s3_sample", "aws_ro_athena_select"):
        assert _fire("adop-build-metadata", tool).cancel_tool is False, tool


@pytest.mark.parametrize("agent", ["adop-build-transform", "adop-build-quality", "adop-build-dag",
                                   "adop-build-ontology", "adop-requirements-auditor"])
def test_other_build_agents_may_not(agent: str) -> None:
    assert "Cedar policy denies" in str(_fire(agent, "aws_ro_athena_select").cancel_tool)


def test_profiler_still_has_no_mcp_or_cli() -> None:
    assert "Cedar policy denies" in str(_fire("adop-build-metadata", "mcp__iam__create_role").cancel_tool)


# ── CLI ─────────────────────────────────────────────────────────────────────


def _repo(tmp_path: Path, workload: str = "orders") -> Path:
    (tmp_path / "workloads" / workload / "run").mkdir(parents=True)
    args = {"workload_name": workload, "source": {"source_path": "s3://data-bucket/orders/"}}
    (tmp_path / "args.json").write_text(json.dumps(args))
    return tmp_path


def test_profile_dry_run_writes_candidates_only(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert cli.main(["--repo-root", str(repo), "profile", "--args", "args.json", "--dry-run"]) == 0
    record = json.loads((repo / "workloads/orders/run/source_profile.json").read_text())
    assert record["phase"] == "3" and record["runtime"] == "strands"
    assert record["status"] == "candidates_pending_human_confirmation"


def test_profile_refuses_unknown_workloads_and_creates_nothing(tmp_path: Path) -> None:
    (tmp_path / "args.json").write_text(json.dumps({"workload_name": "ghost", "source": {"a": 1}}))
    assert cli.main(["--repo-root", str(tmp_path), "profile", "--args", "args.json", "--dry-run"]) == 2
    assert not (tmp_path / "workloads" / "ghost").exists()


def test_profile_requires_human_source(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "args.json").write_text(json.dumps({"workload_name": "orders"}))
    assert cli.main(["--repo-root", str(repo), "profile", "--args", "args.json", "--dry-run"]) == 2
