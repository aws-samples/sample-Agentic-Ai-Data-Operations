#!/usr/bin/env python3
"""ADOP enforce-template-codegen hook (deterministic codegen, non-negotiable).

PreToolUse on Write/Edit/MultiEdit. Denies any direct write to generated artifact
directories — workloads/*/scripts/, dags/, sql/ — so those files can only be
produced by .kiro/adop/adop_render.py from a schema-validated spec.

Why this is unconditional
-------------------------
Upstream gated the equivalent hook on an ADOP_RENDERER_TOKEN env var being set,
which the renderer set around its write. That gate does not hold: anything able to
run `export ADOP_RENDERER_TOKEN=x` — including the agent being constrained — could
unlock it. It also was not needed. The renderer writes with os.replace rather than
the Write tool, so it never triggers a PreToolUse hook and never needs an
exception. Removing the token makes the rule enforceable rather than advisory.

What is NOT blocked
-------------------
config/ (specs live there and must be writable), tests/, memory/, README and other
documentation. Only the three generated directories are protected.

Reads the PreToolUse payload from stdin. Emits a JSON object on stdout:
  {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                          "permissionDecision": "deny",
                          "permissionDecisionReason": "..."}}   -> blocks the call
  {}                                                            -> allow
"""
import json
import re
import sys

# workloads/<name>/{scripts,dags,sql}/... — the renderer's exclusive territory.
PROTECTED = re.compile(r"workloads/[^/]+/(scripts|dags|sql)/")

# template_id to reach for, by artifact location. Keeps the denial actionable
# instead of merely refusing.
SUGGESTED_TEMPLATE = {
    "dags": "airflow_dag",
    "sql": "iceberg_ddl",
    "scripts": "silver_transform / gold_aggregate / bronze_ingestion / quality_check",
}


def _read_payload() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def _target_paths(tool_input: dict) -> list[str]:
    """Every path this tool call would write to."""
    paths = []

    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            paths.append(value)
            break

    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict) and isinstance(edit.get("file_path"), str):
                paths.append(edit["file_path"])

    return paths


def _deny(path: str, kind: str) -> None:
    template = SUGGESTED_TEMPLATE.get(kind, "the matching template")
    reason = (
        f"BLOCKED: '{path}' is a generated artifact. Render it instead of writing it:\n\n"
        f"  .kiro/adop/render.sh --workload workloads/<name> \\\n"
        f"      --template {template} --out {path}\n"
        f"  .kiro/adop/render.sh --list   # templates and required spec slots\n\n"
        f"Write or edit the spec in workloads/<name>/config/ first, then render. Artifacts "
        f"under workloads/*/{{scripts,dags,sql}}/ must come from the renderer so every "
        f"pipeline stays reproducible from its spec. To add a field that has nowhere to "
        f"live, extend the contract in .kiro/adop/codegen/contracts/v1/ and bump the "
        f"template version - do not hand-edit the output.\n\n"
        f"A transformation-agent is installed and can author the spec for you."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    print(reason, file=sys.stderr)


def main() -> None:
    payload = _read_payload()
    tool_input = payload.get("tool_input") or {}

    for path in _target_paths(tool_input):
        match = PROTECTED.search(path.replace("\\", "/"))
        if match:
            _deny(path, match.group(1))
            return

    print("{}")


if __name__ == "__main__":
    main()
