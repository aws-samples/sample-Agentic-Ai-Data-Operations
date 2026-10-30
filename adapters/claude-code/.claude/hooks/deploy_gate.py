#!/usr/bin/env python3
"""Optionally deny Phase 5 deploy mutations until the requirements audit has passed.

One file, byte-identical in .claude/hooks, .codex/hooks and .kiro/hooks (and the
adapter copies); `scripts/sync_platforms.py check` enforces that.

The hook is disabled by default. Set `ADOP_DEPLOY_GATE=1` (also accepting
`true`, `yes` or `on`) to activate it for a session.

A tool call is a deploy mutation if it creates or changes Glue jobs/tables,
IAM role policies, Lake Formation grants/tags, starts a Glue job, or uploads a
DAG — whether through an MCP tool, the AWS CLI in a shell, or a generic AWS
tool (aws-mcp `call_aws`/`run_script`, Kiro `use_aws`). Everything else exits 0
immediately without importing anything.

For a deploy mutation the hook requires `run/deploy_gate.json`, written by
`python3 -m shared.utils.deployment_checks preflight` only after a passing,
current `run/requirements_audit.json`. The call must identify its workload,
and that workload's gate is checked.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

_MCP_DEPLOY_TOOLS = re.compile(
    r"(?:^|[_/.@-])(create_job|update_job|start_job_run|create_table|update_table|"
    r"put_role_policy|create_role|attach_role_policy|grant_permissions|"
    r"batch_grant_permissions|revoke_permissions|create_lf_tag|"
    r"add_lf_tags_to_resource|remove_lf_tags_from_resource|apply_column_security|"
    r"put_object|copy_object|delete_object|upload_part|complete_multipart_upload)$"
)
# Anchored at a command position so a deploy string merely *mentioned* in a
# shell command -- written into a file, grepped for, echoed -- is not a deploy.
_CLI_DEPLOY = re.compile(
    r"(?:\A|[\n;&|(]|\$\()\s*(?:[A-Za-z_][\w]*=\S*\s+)*"
    r"aws\s+(?:glue\s+(?:create-job|update-job|start-job-run|create-table|update-table)"
    r"|iam\s+(?:put-role-policy|create-role|attach-role-policy)"
    r"|lakeformation\s+(?:grant-permissions|batch-grant-permissions|revoke-permissions|"
    r"create-lf-tag|add-lf-tags-to-resource|remove-lf-tags-from-resource)"
    r"|s3\s+(?:cp|sync)\b[^\n;|&]*\bdags/"
    r"|s3api\s+(?:put-object|copy-object|delete-object|upload-part|complete-multipart-upload))"
)
# A heredoc body is data being written, never a command the shell will run.
_HEREDOC = re.compile(
    r"<<-?\s*(['\"]?)([A-Za-z_]\w*)\1.*?^\s*\2\s*$",
    re.DOTALL | re.MULTILINE,
)
_GENERIC_AWS_TOOLS = re.compile(r"(call_aws|run_script|use_aws|useaws)$")
_GENERIC_DEPLOY = re.compile(
    r"\b(?:create[_-]job|update[_-]job|start[_-]job[_-]run|create[_-]table|update[_-]table|"
    r"put[_-]role[_-]policy|create[_-]role|attach[_-]role[_-]policy|grant[_-]permissions|"
    r"batch[_-]grant[_-]permissions|revoke[_-]permissions|create[_-]lf[_-]tag|"
    r"add[_-]lf[_-]tags[_-]to[_-]resource|remove[_-]lf[_-]tags[_-]from[_-]resource|"
    r"put[_-]object|copy[_-]object|delete[_-]object|upload[_-]part|"
    r"complete[_-]multipart[_-]upload)\b",
    re.IGNORECASE,
)
_SHELL_TOOLS = {"bash", "shell", "exec_command", "execute_bash", "executebash", "local_shell"}
_DEPLOY_GATE_ENV = "ADOP_DEPLOY_GATE"


def _normalized_text(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
    # AWS MCP payloads commonly use camelCase operation names.
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text).lower()


def _embedded_commands(tool_input: Any) -> str:
    if not isinstance(tool_input, dict):
        return str(tool_input or "")
    values = []
    for key in ("command", "script", "cmd", "code"):
        value = tool_input.get(key)
        if isinstance(value, list):
            values.append(" ".join(str(part) for part in value))
        elif value is not None:
            values.append(str(value))
    return "\n".join(values)


def _deploy_operation(tool_name: str, tool_input: Any) -> Optional[str]:
    name = tool_name.strip().lower()
    text = _normalized_text(tool_input)
    if name in _SHELL_TOOLS:
        command = tool_input.get("command") if isinstance(tool_input, dict) else text
        if isinstance(command, list):
            command = " ".join(str(part) for part in command)
        match = _CLI_DEPLOY.search(_HEREDOC.sub("\n", str(command or "")))
        return match.group(0).strip() if match else None
    if _GENERIC_AWS_TOOLS.search(name):
        command_text = _embedded_commands(tool_input)
        match = (
            _GENERIC_DEPLOY.search(text)
            or _CLI_DEPLOY.search(_HEREDOC.sub("\n", command_text))
        )
        return f"{name}: {match.group(0)}" if match else None
    match = _MCP_DEPLOY_TOOLS.search(name)
    return name if match else None


def _project_root(event: dict) -> Optional[Path]:
    starts = [Path(event.get("cwd") or os.getcwd()).resolve(), Path(__file__).resolve()]
    for start in starts:
        for candidate in (start, *start.parents):
            if (candidate / "shared" / "utils" / "deployment_checks.py").is_file():
                return candidate
    return None


def _deny(reason: str) -> int:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    print(reason, file=sys.stderr)
    return 2


def _enabled() -> bool:
    return os.environ.get(_DEPLOY_GATE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    if not _enabled():
        return 0
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        return 0
    tool_name = str(event.get("tool_name") or event.get("toolName") or "")
    tool_input = event.get("tool_input") or event.get("toolInput") or {}
    operation = _deploy_operation(tool_name, tool_input)
    if not operation:
        return 0

    root = _project_root(event)
    if root is None:
        return _deny(
            f"Deploy call blocked ({operation}): cannot locate shared/utils/deployment_checks.py "
            "to verify the requirements audit."
        )
    sys.path.insert(0, str(root))
    try:
        from shared.utils.deployment_checks import deploy_gate_open
    except Exception as exc:  # a gate that cannot load must deny, never allow
        return _deny(
            f"Deploy call blocked ({operation}): cannot load the deploy gate "
            f"({type(exc).__name__}: {exc})."
        )

    workloads = sorted(p for p in (root / "workloads").glob("*") if (p / "run").is_dir())
    text = _normalized_text(tool_input)
    named = [w for w in workloads if w.name.lower() in text or w.name.replace("_", "-") in text]
    if not named:
        return _deny(
            f"Deploy call blocked ({operation}): cannot identify a workload in the tool input."
        )
    reasons = []
    for workload_dir in named:
        reason = deploy_gate_open(workload_dir)
        if reason is not None:
            reasons.append(f"{workload_dir.name}: {reason}")
    if not reasons:
        return 0
    detail = "; ".join(reasons)
    return _deny(
        f"Deploy call blocked ({operation}). The requirements audit must pass before "
        f"deployment. {detail}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
