"""Enforce the Cedar policies in shared/policies/ on every agent tool call.

One engine for Claude Code, Codex and Kiro. Each platform's PreToolUse hook
(`cedar_gate.py`, byte-identical per platform) pipes the hook payload here.

Strands runtime: `runtimes/strands/adop_strands/cedar_hook.py` calls `decide()`
in-process from a Strands `BeforeToolCallEvent` hook, with the agent's name as
the explicit principal.

Pipeline per tool call:

1. **Principal.** Claude Code and Codex put `agent_type` in the hook input
   inside a subagent and omit it in the main conversation. Kiro has no such
   field, so each Kiro agent declares its own hook with `--principal <id>`.
   ADOP agent names map to their Cedar principal; any other agent is
   `general`; no agent at all is `onboarding` in the main conversation.
2. **Requests.** The call is translated into Cedar requests:
   file writes -> `WriteFile` on a `WorkloadFile` whose `fileType` is
   classified from the path; MCP / AWS tools and `aws` CLI commands ->
   `InvokeTool` on an `McpTool`; written content -> `PassSecurityCheck`
   SEC-001 with `secretPatternFound`. Reads are not evaluated: every
   principal is permitted `ReadFile`.
3. **Decision.** Evaluated with cedarpy against every static policy in
   shared/policies/ (templates excluded). Any deny denies the call.

Mode comes from shared/policies/enforcement.json, which agents cannot edit
(global_protection.cedar). `audit` logs every decision and blocks nothing;
`enforce` blocks denies. A missing or unreadable mode file, a missing cedarpy
or an evaluation error is treated as `enforce` + deny: the gate fails closed.

Known limit: shell commands are inspected for `aws` CLI calls and for writes
to policy files or the deploy gate. Other files written through a shell
(for example by the codegen renderer) are not seen as WriteFile.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
POLICIES_DIR = ROOT / "shared" / "policies"
MODE_FILE = POLICIES_DIR / "enforcement.json"
DECISION_LOG = ROOT / "logs" / "cedar_decisions.jsonl"
NS = "DataOnboarding"

# Agent names as the platforms report them -> Cedar principal id.
AGENT_PRINCIPALS = {
    "metadata-agent": "metadata",
    "transformation-agent": "transformation",
    "quality-agent": "quality",
    "dag-agent": "dag",
    "ontology-agent": "ontology_staging",
    "requirements-auditor": "requirements_auditor",
    "iac-agent": "iac",
    # Strands runtime / Amazon Q CLI agent names (.amazonq/cli-agents/adop-*.json)
    "adop-build-metadata": "metadata",
    "adop-build-transform": "transformation",
    "adop-build-quality": "quality",
    "adop-build-dag": "dag",
    "adop-build-ontology": "ontology_staging",
    "adop-requirements-auditor": "requirements_auditor",
    "adop-devops": "iac",
    "adop-router": "router",
    "adop-orchestrator": "onboarding",
}
KNOWN_PRINCIPALS = set(AGENT_PRINCIPALS.values()) | {"onboarding", "router", "general"}

_WRITE_TOOLS = {
    "write", "edit", "multiedit", "notebookedit",            # Claude Code
    "fs_write", "fswrite", "str_replace", "strreplace",       # Kiro
    "fs_append", "fsappend", "insert", "delete_file", "deletefile",
}
_PATCH_TOOLS = {"apply_patch"}                                # Codex
_RENDER_TOOLS = {"render_artifact"}                           # Strands runtime
_SHELL_TOOLS = {"bash", "shell", "exec_command", "execute_bash", "executebash",
                "local_shell", "execute_pwsh"}
_GENERIC_AWS_TOOLS = re.compile(r"(?:^|[_/.@-])(call_aws|run_script|use_aws|useaws|aws)$")

_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_]\w*)\1.*?^\s*\2\s*$", re.S | re.M)
_AWS_CLI = re.compile(
    r"(?:\A|[\n;&|(]|\$\()\s*(?:[A-Za-z_]\w*=\S*\s+)*aws\s+([a-z0-9-]+)\s+([a-z0-9-]+)"
)
_PROTECTED_PATH = re.compile(r"\S*shared/policies\b\S*|\S*deploy_gate\.json")
_SHELL_WRITE = re.compile(
    r">{1,2}|\btee\b|\bsed\s+-i|\b(?:cp|mv|rm|install|ln|touch|truncate|chmod|chown|rsync|dd)\b"
    r"|\bgit\s+(?:checkout|restore|apply|rm|mv|reset|stash|clean)\b"
    r"|write_text|write_bytes|\.write\(|open\([^)]*['\"][wax]|shutil\.|os\.(?:remove|rename|replace|unlink)"
)
_SECRET = re.compile(
    r"(?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}"
    r"|-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
    r"|aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}"
    r"|(?i:password|passwd|secret|api[_-]?key|auth[_-]?token)\s*[=:]\s*['\"][^'\"\s]{8,}['\"]"
)


# ── principal ───────────────────────────────────────────────────────────────


def resolve_principal(event: Dict[str, Any], explicit: Optional[str] = None) -> Tuple[str, str]:
    """Return (principal_id, execution_context)."""
    if explicit:
        pid = AGENT_PRINCIPALS.get(explicit.strip(), explicit.strip())
        return (pid if pid in KNOWN_PRINCIPALS else "general",
                "main_conversation" if pid == "onboarding" else "sub_agent")
    agent = str(event.get("agent_type") or event.get("agentType") or "").strip()
    if not agent:
        return "onboarding", "main_conversation"
    name = agent.rsplit(":", 1)[-1]          # plugin agents: "adop:metadata-agent"
    return AGENT_PRINCIPALS.get(name, "general"), "sub_agent"


# ── resources ───────────────────────────────────────────────────────────────


def _relative(raw: str, cwd: Path) -> str:
    path = Path(raw)
    if not path.is_absolute():
        path = cwd / path
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def classify_path(rel: str) -> Tuple[str, str]:
    """Return (fileType, workload) for a repo-relative path."""
    rel = rel.removeprefix("./")
    if rel.endswith("deploy_gate.json"):
        return "deploy_gate", ""
    if rel == "shared/policies" or rel.startswith("shared/policies/"):  # the only live policies
        return "policy", ""
    if rel.startswith("logs/"):
        return "log", ""
    parts = rel.split("/")
    if len(parts) >= 3 and parts[0] == "workloads":
        workload, section = parts[1], parts[2]
        rest = "/".join(parts[3:])
        mapping = {"config": "config", "scripts": "script", "dags": "dag", "sql": "sql",
                   "tests": "test", "iac": "iac", ".handoffs": "handoff", "logs": "log"}
        if section in mapping:
            return mapping[section], workload
        if section == "run":
            if rest == "decisions.jsonl":
                return "decisions", workload
            if rest == "requirements_audit.json":
                return "audit", workload
            return "run_state", workload
        if section in (".discovery_complete",):
            return "run_state", workload
        return "other", workload
    return "other", ""


def _patch_paths(text: str) -> List[str]:
    return re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", text, re.M) + \
        re.findall(r"^\*\*\* Move to: (.+)$", text, re.M)


def _written_content(tool_input: Dict[str, Any]) -> str:
    chunks = [tool_input.get(k) for k in ("content", "new_string", "text", "new_str", "file_text",
                                          "new_source", "patch", "input")]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            chunks.append(edit.get("new_string"))
    return "\n".join(str(c) for c in chunks if c)


def _mcp_parts(name: str) -> Optional[Tuple[str, str]]:
    if name.startswith("mcp__"):
        rest = name[len("mcp__"):]
        if "__" in rest:
            server, tool = rest.rsplit("__", 1)
            if server.startswith("plugin_"):
                server = server.split("_", 2)[-1]
            return server.replace("_", "-"), tool
    if name.startswith("@") and "/" in name:            # Kiro: @server/tool
        server, tool = name[1:].split("/", 1)
        return server, tool
    return None


def build_requests(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    tool_name = str(event.get("tool_name") or event.get("toolName") or "")
    tool_input = event.get("tool_input") or event.get("toolInput") or {}
    if not isinstance(tool_input, dict):
        tool_input = {"input": tool_input}
    cwd = Path(event.get("cwd") or ROOT)
    lowered = tool_name.strip().lower()
    requests: List[Dict[str, Any]] = []

    def write(raw_path: str, content: str = "") -> None:
        rel = _relative(raw_path, cwd)
        file_type, workload = classify_path(rel)
        requests.append({"action": "WriteFile", "resource": ("WorkloadFile", rel),
                         "attrs": {"fileType": file_type, "zone": ""}, "workload": workload,
                         "path": rel})
        if content:
            requests.append({"action": "PassSecurityCheck", "resource": ("PipelineStep", rel),
                             "attrs": {"stepNumber": 0, "stepName": "agent_file_write",
                                       "sourceZone": "", "targetZone": ""},
                             "context": {"guardrailCode": "SEC-001",
                                         "secretPatternFound": bool(_SECRET.search(content)),
                                         "filePath": rel},
                             "workload": workload, "path": rel})

    def invoke(server: str, tool: str) -> None:
        requests.append({"action": "InvokeTool", "resource": ("McpTool", f"{server}/{tool}"),
                         "attrs": {"serverName": server, "toolName": tool}, "workload": ""})

    if lowered in _WRITE_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path")
        if path:
            write(str(path), _written_content(tool_input))
    elif lowered in _RENDER_TOOLS:
        # The renderer writes the artifact; govern its output path like a write.
        if tool_input.get("output_path"):
            write(str(tool_input["output_path"]))
    elif lowered in _PATCH_TOOLS:
        patch = str(tool_input.get("patch") or tool_input.get("input") or tool_input.get("command") or "")
        added = "\n".join(l[1:] for l in patch.splitlines() if l.startswith("+"))
        for path in _patch_paths(patch):
            write(path.strip(), added)
    elif lowered in _SHELL_TOOLS:
        command = tool_input.get("command") or ""
        if isinstance(command, list):
            command = " ".join(str(c) for c in command)
        command = str(command)
        for service, operation in _AWS_CLI.findall(_HEREDOC.sub("\n", command)):
            invoke("aws-cli", f"{service}:{operation}")
        if _SHELL_WRITE.search(command):
            for raw in dict.fromkeys(m.strip("'\"") for m in _PROTECTED_PATH.findall(command)):
                write(raw)
    elif lowered.startswith("aws_ro_"):
        # Strands Phase 3 read-only AWS tools (runtimes/strands/adop_strands/aws_readonly.py)
        invoke("aws-readonly", lowered)
    else:
        parts = _mcp_parts(tool_name)
        if parts:
            invoke(*parts)
        elif _GENERIC_AWS_TOOLS.search(lowered):
            service = str(tool_input.get("service_name") or tool_input.get("serviceName") or "")
            operation = str(tool_input.get("operation_name") or tool_input.get("operationName") or "")
            invoke("aws", f"{service}:{operation}" if service else lowered)
    return requests


# ── evaluation ──────────────────────────────────────────────────────────────


def load_mode() -> str:
    try:
        mode = json.loads(MODE_FILE.read_text(encoding="utf-8")).get("mode")
    except (OSError, json.JSONDecodeError, AttributeError):
        return "enforce"
    return mode if mode in ("audit", "enforce") else "enforce"


def load_policies() -> str:
    files = [p for p in sorted(POLICIES_DIR.rglob("*.cedar")) if "templates" not in p.parts]
    return "\n\n".join(p.read_text(encoding="utf-8") for p in files)


def _entity(etype: str, eid: str, attrs: Dict[str, Any]) -> Dict[str, Any]:
    return {"uid": {"type": f"{NS}::{etype}", "id": eid}, "attrs": attrs, "parents": []}


def evaluate(principal: str, context_kind: str, requests: Iterable[Dict[str, Any]],
             workload_hint: str = "") -> List[Dict[str, Any]]:
    """Return one decision record per request. Raises if cedarpy is unavailable."""
    import cedarpy

    policies = load_policies()
    decisions = []
    for req in requests:
        workload = req.get("workload") or workload_hint
        etype, eid = req["resource"]
        entities = [
            _entity("AgentPrincipal", principal, {"agentType": principal,
                                                  "executionContext": context_kind,
                                                  "workloadName": workload}),
            _entity(etype, eid, req["attrs"]),
        ]
        result = cedarpy.is_authorized(
            {
                "principal": f'{NS}::AgentPrincipal::"{principal}"',
                "action": f'{NS}::Action::"{req["action"]}"',
                "resource": f'{NS}::{etype}::"{eid}"',
                "context": req.get("context", {}),
            },
            policies,
            entities,
        )
        allowed = str(result.decision).endswith("Allow")
        decisions.append({
            "action": req["action"], "resource": eid, "allowed": allowed,
            "attrs": req["attrs"], "context": req.get("context", {}),
            "policies": [str(r) for r in getattr(result.diagnostics, "reasons", [])],
            "errors": [str(e) for e in getattr(result.diagnostics, "errors", [])],
        })
    return decisions


def _log(record: Dict[str, Any]) -> None:
    try:
        DECISION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with DECISION_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        pass  # logging must never decide the outcome


def decide(event: Dict[str, Any], explicit_principal: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
    """Return (allow, reason, record). `allow` already accounts for the mode."""
    mode = load_mode()
    principal, context_kind = resolve_principal(event, explicit_principal)
    requests = build_requests(event)
    record: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode, "principal": principal, "execution_context": context_kind,
        "agent_type": event.get("agent_type", ""), "tool_name": event.get("tool_name", ""),
        "session_id": event.get("session_id", ""),
    }
    if not requests:
        return True, "", record

    try:
        decisions = evaluate(principal, context_kind, requests)
        denied = [d for d in decisions if not d["allowed"]]
        reason = "; ".join(
            f"{d['action']} {d['resource']}"
            + (f" (fileType={d['attrs'].get('fileType')})" if "fileType" in d["attrs"] else "")
            + (" (hardcoded secret)" if d["context"].get("secretPatternFound") else "")
            for d in denied
        )
    except Exception as exc:  # cedarpy missing or evaluation failure: fail closed
        decisions, denied = [], [{"error": f"{type(exc).__name__}: {exc}"}]
        reason = f"Cedar engine unavailable ({type(exc).__name__}: {exc})"
    record.update({"decisions": decisions, "denied": bool(denied), "reason": reason})
    _log(record)

    if not denied:
        return True, "", record
    if mode == "audit":
        return True, f"[audit] would deny: {reason}", record
    return False, (f"Cedar policy denies {principal} ({context_kind}): {reason}. "
                   "Policies: shared/policies/. Agents cannot change them."), record


def main(argv: List[str]) -> int:
    explicit = None
    if "--principal" in argv:
        index = argv.index("--principal")
        explicit = argv[index + 1] if index + 1 < len(argv) else None
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        event = {}
    allow, reason, _ = decide(event, explicit)
    if allow:
        return 0
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    print(reason, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
