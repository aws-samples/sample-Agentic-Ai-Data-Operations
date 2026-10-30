"""Read-only AWS tools for Phase 3 profiling on Strands.

Human decision 2026-10-30: the Strands profiler reaches Glue, S3 and Athena
through fixed tools that can only read, not through `aws-mcp` `run_script`
(arbitrary code) and not through the excluded `glue-athena` MCP.

Read-only by construction:

* Glue: `get_databases`, `get_tables`, `get_table` only.
* S3: list up to 100 keys under a prefix; read at most 256 KiB of one object.
* Athena: one `SELECT`/`WITH` statement, no `;`, comments or DDL/DML/DCL
  keywords, row-capped with `LIMIT`. Athena writes the result set to the
  human-provided output location; that is the only side effect.

Every tool is named `aws_ro_*`; `shared/utils/cedar_gate.py` maps that prefix
to `InvokeTool` on server `aws-readonly`, and only the metadata principal is
permitted it (`shared/policies/agent_authorization/metadata_agent.cedar`).
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional

MAX_KEYS = 100
MAX_BYTES = 256 * 1024
MAX_ROWS = 1000
ATHENA_TIMEOUT_S = 120

_FORBIDDEN_SQL = re.compile(
    r"\b(?:DROP|CREATE|ALTER|TRUNCATE|INSERT|UPDATE|DELETE|MERGE|GRANT|REVOKE|"
    r"MSCK|REPAIR|UNLOAD|CALL|EXECUTE|PREPARE|DEALLOCATE|OPTIMIZE|VACUUM)\b",
    re.IGNORECASE,
)
_S3_URI = re.compile(r"^s3://([a-z0-9][a-z0-9.-]{1,61}[a-z0-9])(?:/(.*))?$")
ClientFactory = Callable[[str], Any]


class ReadOnlyViolation(ValueError):
    """Raised when a request would do anything other than read."""


def validate_select(sql: str, max_rows: int = MAX_ROWS) -> str:
    """Return a row-capped single SELECT, or raise ReadOnlyViolation."""
    text = sql.strip().rstrip()
    if not text:
        raise ReadOnlyViolation("empty query")
    for token in (";", "--", "/*"):
        if token in text:
            raise ReadOnlyViolation(f"query may not contain {token!r}")
    if not re.match(r"^(?:SELECT|WITH)\b", text, re.IGNORECASE):
        raise ReadOnlyViolation("only SELECT or WITH ... SELECT queries are allowed")
    bad = sorted({m.group(0).upper() for m in _FORBIDDEN_SQL.finditer(text)})
    if bad:
        raise ReadOnlyViolation(f"query contains non-read keywords: {bad}")
    limit = re.search(r"\bLIMIT\s+(\d+)\s*$", text, re.IGNORECASE)
    if limit:
        if int(limit.group(1)) > max_rows:
            text = text[: limit.start()] + f"LIMIT {max_rows}"
    else:
        text = f"{text}\nLIMIT {max_rows}"
    return text


def _parse_s3(uri: str) -> tuple[str, str]:
    match = _S3_URI.match(uri.strip())
    if not match or ".." in uri:
        raise ReadOnlyViolation(f"not a valid s3:// URI: {uri!r}")
    return match.group(1), match.group(2) or ""


def make_readonly_aws_tools(
    region: str,
    athena_output: Optional[str] = None,
    athena_workgroup: Optional[str] = None,
    client_factory: Optional[ClientFactory] = None,
) -> List[Any]:
    """Build the `aws_ro_*` Strands tools. `client_factory(service)` is for tests."""
    from strands import tool

    if client_factory is None:
        import boto3

        session = boto3.session.Session(region_name=region)
        client_factory = session.client
    clients: Dict[str, Any] = {}

    def client(service: str) -> Any:
        if service not in clients:
            clients[service] = client_factory(service)
        return clients[service]

    @tool(name="aws_ro_glue_get_databases")
    def glue_get_databases() -> List[str]:
        """List Glue Data Catalog database names (read-only)."""
        names: List[str] = []
        for page in client("glue").get_paginator("get_databases").paginate():
            names += [db["Name"] for db in page.get("DatabaseList", [])]
        return names

    @tool(name="aws_ro_glue_get_tables")
    def glue_get_tables(database: str) -> List[str]:
        """List table names in one Glue database (read-only)."""
        names: List[str] = []
        for page in client("glue").get_paginator("get_tables").paginate(DatabaseName=database):
            names += [t["Name"] for t in page.get("TableList", [])]
        return names

    @tool(name="aws_ro_glue_get_table")
    def glue_get_table(database: str, table: str) -> Dict[str, Any]:
        """Return one Glue table's columns, partition keys, location and format (read-only)."""
        t = client("glue").get_table(DatabaseName=database, Name=table)["Table"]
        sd = t.get("StorageDescriptor", {})
        return {
            "name": t["Name"],
            "columns": sd.get("Columns", []),
            "partition_keys": t.get("PartitionKeys", []),
            "location": sd.get("Location", ""),
            "input_format": sd.get("InputFormat", ""),
            "serde": sd.get("SerdeInfo", {}).get("SerializationLibrary", ""),
            "table_type": t.get("TableType", ""),
        }

    @tool(name="aws_ro_s3_list")
    def s3_list(prefix_uri: str, max_keys: int = MAX_KEYS) -> List[Dict[str, Any]]:
        """List up to 100 objects under an s3:// prefix (read-only)."""
        bucket, prefix = _parse_s3(prefix_uri)
        response = client("s3").list_objects_v2(
            Bucket=bucket, Prefix=prefix, MaxKeys=max(1, min(int(max_keys), MAX_KEYS))
        )
        return [{"key": o["Key"], "size": o["Size"]} for o in response.get("Contents", [])]

    @tool(name="aws_ro_s3_sample")
    def s3_sample(object_uri: str, max_bytes: int = MAX_BYTES) -> str:
        """Read the first bytes (at most 256 KiB) of one S3 object as text (read-only)."""
        bucket, key = _parse_s3(object_uri)
        if not key:
            raise ReadOnlyViolation("object URI must include a key")
        size = max(1, min(int(max_bytes), MAX_BYTES))
        body = client("s3").get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{size - 1}")["Body"]
        return body.read().decode("utf-8", errors="replace")

    @tool(name="aws_ro_athena_select")
    def athena_select(sql: str, database: str) -> Dict[str, Any]:
        """Run one row-capped SELECT in Athena and return the rows (read-only)."""
        if not athena_output:
            raise ReadOnlyViolation(
                "no Athena output location; pass --athena-output (human-provided)"
            )
        query = validate_select(sql)
        athena = client("athena")
        start: Dict[str, Any] = {
            "QueryString": query,
            "QueryExecutionContext": {"Database": database},
            "ResultConfiguration": {"OutputLocation": athena_output},
        }
        if athena_workgroup:
            start["WorkGroup"] = athena_workgroup
        query_id = athena.start_query_execution(**start)["QueryExecutionId"]
        deadline = time.monotonic() + ATHENA_TIMEOUT_S
        while True:
            status = athena.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]["Status"]
            state = status["State"]
            if state == "SUCCEEDED":
                break
            if state in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"Athena {state}: {status.get('StateChangeReason', '')}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"Athena query {query_id} exceeded {ATHENA_TIMEOUT_S}s")
            time.sleep(1)
        rows = athena.get_query_results(QueryExecutionId=query_id, MaxResults=MAX_ROWS)["ResultSet"]["Rows"]
        values = [[c.get("VarCharValue") for c in r.get("Data", [])] for r in rows]
        return {"query": query, "header": values[0] if values else [], "rows": values[1:]}

    return [glue_get_databases, glue_get_tables, glue_get_table, s3_list, s3_sample, athena_select]
