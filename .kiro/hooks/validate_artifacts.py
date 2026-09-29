#!/usr/bin/env python3
"""ADOP validate-artifacts hook (Phase 4.5).

Runs after Write/Edit. Validates generated pipeline artifacts under workloads/<name>/ so bad
code is caught at build time, before promotion. Non-blocking by default: it surfaces findings
to the model via a JSON decision so it can self-correct, and only BLOCKs on hard failures
(unparseable Python, credential leaks).

Reads the PostToolUse payload from stdin. Emits a JSON object on stdout:
  {"decision": "block", "reason": "..."}  -> feeds reason back to the model
  {}                                        -> allow, nothing to say
"""
import ast
import json
import pathlib
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
    # YAML assignment. The three patterns above assume `key = "value"`, but every ADOP
    # spec is YAML (`key: value`), so a secret in workloads/*/config/*.yaml was invisible
    # unless it happened to be an AKIA key. Divergence from upstream -- report there too.
    r"(?i)(aws_secret_access_key|secret_access_key|password|passwd|secret_key"
    r"|api_key|private_key|token)\s*:\s*(?!\s*$)(?![\"']?\s*(\$\{|\$[A-Z_]+|arn:aws:"
    r"|<|\{\{|CHANGE_?ME|REPLACE_?ME|TODO|null|~|\[\])) *[\"']?[^\s\"'#][^\n\"'#]{2,}",
]



def _run_context_errors(content: str) -> list[str]:
    """Validate run/context.json against its contract, degrading safely.

    Returns [] when the contract or jsonschema is unavailable: a gate that cannot load its
    schema must not block legitimate work, and the renderer validates again downstream.
    """
    try:
        spec = json.loads(content)
    except (json.JSONDecodeError, ValueError) as e:
        return [f"not valid JSON: {e}"]

    # Three layouts put the contract in three places: installed (.kiro/adop/codegen/),
    # this repo (skills/onboard-workflow/scripts/codegen/), and upstream aws-samples
    # (contracts/v1/ at the repo root). Walk up looking for the schema instead of listing
    # paths, so the gate behaves identically wherever it is vendored.
    here = pathlib.Path(__file__).resolve().parent
    rel = ("contracts/v1/run_context.schema.json",
           "codegen/contracts/v1/run_context.schema.json",
           "adop/codegen/contracts/v1/run_context.schema.json",
           "skills/onboard-workflow/scripts/codegen/contracts/v1/run_context.schema.json")
    schema_path = None
    for base in (here, *here.parents):
        for r in rel:
            cand = base / r
            if cand.exists():
                schema_path = cand
                break
        if schema_path is not None:
            break

    if schema_path is None:
        return []

    try:
        import jsonschema
    except ImportError:
        return []

    try:
        schema = json.loads(schema_path.read_text())
    except (OSError, json.JSONDecodeError):
        return []

    validator = jsonschema.Draft202012Validator(schema)
    out = []
    for err in validator.iter_errors(spec):
        where = ".".join(str(x) for x in err.absolute_path) or "(root)"
        out.append(f"{where}: {err.message}")
    return out


def _validate(path: str, content: str) -> None:
    """Run every check against content and print the decision.

    Shared by both wirings. All four checks operate on content rather than on the
    file, which is what lets the pre-write path exist at all.
    """
    findings = []
    hard_block = False
    lower = path.lower()
    norm = lower.replace("\\", "/")

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

    # 2b) run/context.json must satisfy its contract (BLOCK).
    #
    # Every sub-agent is told to read this file and treat human_answers as authoritative
    # over its own prompt, and the SessionStart hook restores the orchestrator's place from
    # it. Both trusted it blindly: a context.json with `current_phase: 4` (the schema wants
    # the string "4") and a human_answers missing its required keys was written and read back
    # without complaint. An instruction to validate is not enforcement, so validate here --
    # at the write, where it can still be stopped.
    if norm.endswith("/run/context.json") or norm.endswith("run/context.json"):
        errors = _run_context_errors(content)
        if errors:
            hard_block = True
            findings.append(
                "run/context.json does not satisfy run_context.schema.json:\n  - "
                + "\n  - ".join(errors)
                + "\nFix the file before continuing. Sub-agents treat human_answers as "
                  "authoritative, so an invalid context silently misleads every agent that "
                  "reads it."
            )

    # 3) Airflow DAG best-practice nudges (WARN, non-blocking).
    if "/dags/" in norm and lower.endswith(".py"):
        if "retries" not in content:
            findings.append("DAG has no 'retries' configured (recommend retries=3 + backoff).")
        if "DAG(" not in content and "with DAG" not in content:
            findings.append("File under dags/ does not define a DAG object.")

    # 4) Glue ETL lineage invariant nudge (WARN).
    if "/scripts/" in norm and lower.endswith(".py"):
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
            print(json.dumps({"systemMessage": reason}))
        return

    print("{}")


def main():
    payload = _read_payload()
    path = _edited_path(payload)

    # Only inspect files inside a workload.
    if "workloads/" not in path.replace("\\", "/"):
        print("{}")
        return

    # Prefer the pending content from the payload. Every check operates on content,
    # so they can all run BEFORE the write -- which is what restores enforcement on
    # Kiro, where PostToolUse cannot block. Falling back to disk keeps the PostToolUse
    # wiring useful for content arriving by routes with no tool_input (a bash heredoc,
    # say), where advisory is the best available.
    ti = payload.get("tool_input") or {}
    pending = next((ti[k] for k in ("text", "content", "new_str", "new_string")
                    if isinstance(ti.get(k), str)), None)
    if pending is not None:
        _validate(path, pending)
        return

    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
    except Exception:
        print("{}")
        return

    _validate(path, content)


if __name__ == "__main__":
    sys.exit(main())
