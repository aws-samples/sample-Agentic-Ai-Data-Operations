#!/usr/bin/env python3
"""ADOP block-credentials hook (invariant: no-credentials-in-code).

PreToolUse on Write/Edit/MultiEdit. Inspects the content the model is ABOUT to
write and denies the tool call if it carries a hardcoded credential, so the
secret never reaches disk.

This exists separately from validate_artifacts.py because that hook is
PostToolUse: by the time it runs, the file has already been written, and a
"block" there only informs the model — it does not prevent the leak. For
syntax and best-practice findings that is fine; for a credential it is not.

validate_artifacts.py still carries the same credential check as defence in
depth, since content can reach disk by routes this hook does not see (a
heredoc via Bash, for example).

Scope: files under workloads/ only. The plugin's remit is ADOP-generated
artifacts, and a PreToolUse deny is disruptive — policing every file in the
user's repo would produce blocking false positives on things like .env.example
or test fixtures.

Reads the PreToolUse payload from stdin. Emits a JSON object on stdout:
  {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                          "permissionDecision": "deny",
                          "permissionDecisionReason": "..."}}   -> blocks the call
  {}                                                             -> allow
"""
import json
import re
import sys

# Credentials that must never be committed (invariant: no-credentials-in-code).
# Kept identical to validate_artifacts.py so the two layers agree.
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


def _read_payload() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def _target_path(tool_input: dict) -> str:
    return tool_input.get("file_path") or tool_input.get("path") or ""


def _pending_content(tool_input: dict) -> str:
    """Collect every piece of content this tool call would write.

    Write     -> content
    Edit      -> new_string
    MultiEdit -> edits[].new_string
    """
    parts = []

    for key in ("content", "new_string"):
        value = tool_input.get(key)
        if isinstance(value, str):
            parts.append(value)

    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
                parts.append(edit["new_string"])

    return "\n".join(parts)


def main() -> None:
    payload = _read_payload()
    tool_input = payload.get("tool_input") or {}

    path = _target_path(tool_input)
    if "workloads/" not in path.replace("\\", "/"):
        print("{}")
        return

    content = _pending_content(tool_input)
    if not content:
        print("{}")
        return

    for pattern in SECRET_PATTERNS:
        if re.search(pattern, content):
            reason = (
                f"BLOCKED: the content for '{path}' contains what looks like a hardcoded "
                "credential (invariant no-credentials-in-code). Resolve secrets at runtime "
                "via Secrets Manager or an Airflow Connection and reference them by ARN or "
                "connection id instead."
            )
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }))
            print(reason, file=sys.stderr)
            return

    print("{}")


if __name__ == "__main__":
    main()
