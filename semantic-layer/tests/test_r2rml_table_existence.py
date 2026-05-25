"""Every rr:tableName in r2rml-mappings.ttl resolves to a real Glue table.

Skipped automatically when AWS credentials are not available — CI environments
without AWS access still get the rest of the suite.
"""
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

TABLE_NAME_RE = re.compile(r'rr:tableName\s+"([^"]+)"')
SQL_QUERY_RE = re.compile(r'rr:sqlQuery\s+"""\s*(.+?)\s*"""', re.DOTALL)
FROM_RE = re.compile(r"\bFROM\s+([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)", re.IGNORECASE)


def _aws_creds_available() -> bool:
    return bool(os.environ.get("AWS_ACCESS_KEY_ID")) or bool(os.environ.get("AWS_PROFILE"))


@pytest.mark.skipif(not _aws_creds_available(), reason="No AWS credentials in environment")
def test_all_logical_tables_exist():
    import boto3

    glue = boto3.client("glue", region_name=os.environ.get("AWS_REGION", "us-west-2"))
    text = (ROOT / "r2rml-mappings.ttl").read_text()

    references: set[tuple[str, str]] = set()

    for db_table in TABLE_NAME_RE.findall(text):
        if "." not in db_table:
            pytest.fail(f"rr:tableName {db_table!r} is not fully qualified (db.table)")
        db, table = db_table.split(".", 1)
        references.add((db, table))

    for sql in SQL_QUERY_RE.findall(text):
        for db, table in FROM_RE.findall(sql):
            references.add((db, table))

    missing = []
    for db, table in sorted(references):
        try:
            glue.get_table(DatabaseName=db, Name=table)
        except glue.exceptions.EntityNotFoundException:
            missing.append(f"{db}.{table}")

    assert not missing, f"Missing Glue tables: {missing}"
