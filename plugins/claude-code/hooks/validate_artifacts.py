#!/usr/bin/env python3
"""ADOP validate-artifacts hook (Phase 4.5).

Runs after Write/Edit. Validates generated pipeline artifacts under workloads/<name>/ so bad
code is caught at build time, before promotion. Non-blocking by default: it surfaces findings
to the model via a JSON decision so it can self-correct, and only BLOCKs on hard failures
(unparseable Python, credential leaks).

Reads the PostToolUse payload from stdin (Claude Code contract). Emits a JSON object on stdout:
  {"decision": "block", "reason": "..."}  -> feeds reason back to the model
  {}                                        -> allow, nothing to say
"""
import ast
import json
import re
import sys


def _read_payload():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def _edited_path(payload):
    ti = payload.get("tool_input") or {}
    return ti.get("file_path") or ti.get("path") or ""


# Credentials that must never be committed (invariant: no-credentials-in-code).
SECRET_PATTERNS = [
    r"AKIA[0-9A-Z]{16}",                     # AWS access key id
    r"aws_secret_access_key\s*=\s*['\"][^'\"]+",
    r"(?i)password\s*=\s*['\"][^'\"]{3,}",
]


def main():
    payload = _read_payload()
    path = _edited_path(payload)

    # Only inspect files inside a workload.
    if "workloads/" not in path.replace("\\", "/"):
        print("{}")
        return

    findings = []
    hard_block = False

    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
    except Exception:
        print("{}")
        return

    lower = path.lower()

    # 1) Python artifacts must parse (scripts/, dags/, tests/).
    if lower.endswith(".py"):
        try:
            ast.parse(content)
        except SyntaxError as e:
            hard_block = True
            findings.append(f"Python syntax error in {path}: {e}")

    # 2) Credential leak check (BLOCK).
    for pat in SECRET_PATTERNS:
        if re.search(pat, content):
            hard_block = True
            findings.append(
                f"Possible hardcoded credential in {path} (invariant no-credentials-in-code). "
                "Use Secrets Manager / Airflow Connections."
            )
            break

    # 3) Airflow DAG best-practice nudges (WARN, non-blocking).
    if "/dags/" in lower.replace("\\", "/") and lower.endswith(".py"):
        if "retries" not in content:
            findings.append("DAG has no 'retries' configured (recommend retries=3 + backoff).")
        if "DAG(" not in content and "with DAG" not in content:
            findings.append("File under dags/ does not define a DAG object.")

    # 4) Glue ETL lineage invariant nudge (WARN).
    if "/scripts/" in lower.replace("\\", "/") and lower.endswith(".py"):
        if "enable-data-lineage" not in content and "enable_data_lineage" not in content:
            findings.append(
                "ETL script does not reference data lineage (invariant lineage-always: "
                "set --enable-data-lineage: true on the Glue job)."
            )

    if findings:
        reason = "ADOP artifact validation:\n- " + "\n- ".join(findings)
        if hard_block:
            print(json.dumps({"decision": "block", "reason": reason}))
        else:
            # Surface as context without blocking.
            print(json.dumps({"decision": "block", "reason": reason})
                  if False else json.dumps({"systemMessage": reason}))
        return

    print("{}")


if __name__ == "__main__":
    main()
