"""Kiro adapter tests.

Two layers:

* the packaged snapshot under `adapters/kiro/` still runs standalone;
* the live `.kiro/` surface satisfies Kiro's config schemas and exit contract.

The second layer exists because the first one cannot see the bugs that matter. The
original tests invoked the gate scripts directly and asserted `returncode == 0` plus a
deny decision on STDOUT -- the *upstream* ADOP contract. Kiro denies on **exit 2**, and
the translation is done by `adop-hook.sh`, which nothing exercised. A gate could stop
blocking entirely and the suite stayed green.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
KIRO = ROOT / ".kiro"
LAUNCHER = KIRO / "hooks" / "adop-hook.sh"

# Trigger names Kiro accepts in a standalone `.kiro/hooks/*.json`, across the IDE and
# CLI surfaces. PascalCase exactly; the camelCase spellings are the agent-config form.
VALID_TRIGGERS = {
    "PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionStart", "AgentSpawn",
    "Stop", "PreTaskExec", "PostTaskExec",
    "PostFileCreate", "PostFileSave", "PostFileDelete",
}

# Tool-name spellings a PreToolUse/PostToolUse matcher may legitimately target: Kiro's
# canonical CLI names, their documented aliases, and the IDE camelCase forms. A matcher
# alternative outside this set is a leftover from another harness and will never fire.
KNOWN_TOOL_NAMES = {
    "fs_read", "read", "fsRead", "readFile",
    "fs_write", "write", "fsWrite",
    "str_replace", "strReplace", "fs_append", "fsAppend", "insert",
    "fs_list", "list_directory", "listDirectory",
    "delete_file", "deleteFile",
    "execute_bash", "shell", "executeBash",
    "grep_search", "file_search", "grepSearch", "fileSearch",
    "use_aws", "aws", "subagent", "subAgent", "spawn_agent", "spawnAgent",
    "knowledge", "web_fetch", "web_search", "*", "@builtin",
}

# Fields Kiro's agent schema accepts. Anything else is a validation error.
VALID_AGENT_FIELDS = {
    "name", "description", "prompt", "mcpServers", "tools", "excludedTools",
    "toolAliases", "allowedTools", "permissions", "toolsSettings", "resources",
    "hooks", "includeMcpJson", "includePowers", "model", "keyboardShortcut",
    "welcomeMessage",
}

VALID_CAPABILITIES = {
    "fs_read", "fs_write", "shell", "web_fetch", "web_search", "mcp", "subagent", "all",
}

VALID_INCLUSION = {"always", "fileMatch", "manual", "auto"}


def _run(path: str, payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, path],
        cwd=ROOT,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


def _via_launcher(script: str, payload: dict) -> subprocess.CompletedProcess[str]:
    """Invoke a gate the way Kiro does: through the launcher, reading its exit code."""
    return subprocess.run(
        [str(LAUNCHER), script],
        cwd=ROOT,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


def _write_payload(path: str, text: str, event: str = "preToolUse") -> dict:
    return {
        "hook_event_name": event,
        "tool_name": "fs_write",
        "tool_input": {"path": path, "text": text},
    }


def _hooks() -> list[dict]:
    return json.loads((KIRO / "hooks" / "adop-gates.json").read_text())["hooks"]


def _front_matter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    assert end != -1, f"{path.name}: unterminated front-matter"
    return yaml.safe_load(text[3:end]) or {}


# --------------------------------------------------------------------------------------
# Packaged snapshot still works standalone
# --------------------------------------------------------------------------------------

def test_packaged_kiro_capture_is_standalone(tmp_path):
    """The snapshot's capture hook imports and runs without the full checkout.

    Uses a workload that does not exist so nothing is appended. The previous version of
    this test passed `unknown_workload`, which made the hook create
    `adapters/kiro/workloads/unknown_workload/.requirements_pending/requirements.jsonl`
    and append one record on every run -- committed test output that grew with the suite.
    """
    result = _run(
        "adapters/kiro/.kiro/hooks/capture_user_turn.py",
        {"workload_name": f"pytest_{tmp_path.name}"[:40], "prompt": "hello"},
    )
    assert result.returncode == 0, result.stderr
    leaked = ROOT / "adapters" / "kiro" / "workloads" / f"pytest_{tmp_path.name}"[:40]
    if leaked.exists():
        shutil.rmtree(leaked)


def test_kiro_renderer_lists_templates():
    result = subprocess.run(
        [sys.executable, "adapters/kiro/.kiro/adop/render.py", "--list"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "silver_transform" in result.stdout


def test_live_kiro_renderer_lists_templates():
    """The clone-ready surface renders too -- it is the path the codegen gate names."""
    result = subprocess.run(
        [sys.executable, ".kiro/adop/render.py", "--list"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "silver_transform" in result.stdout


# --------------------------------------------------------------------------------------
# Hook config schema
# --------------------------------------------------------------------------------------

def test_hook_config_shape():
    config = json.loads((KIRO / "hooks" / "adop-gates.json").read_text())
    assert config["version"] == "v1"
    assert isinstance(config["hooks"], list) and config["hooks"]


@pytest.mark.parametrize("hook", _hooks(), ids=lambda h: h["name"])
def test_hook_trigger_and_action_are_valid(hook):
    assert hook["trigger"] in VALID_TRIGGERS, (
        f"{hook['name']}: unknown trigger {hook['trigger']!r}"
    )
    action = hook["action"]
    assert action["type"] in {"command", "agent"}
    if action["type"] == "command":
        assert action["command"]
    else:
        assert action.get("prompt"), "an agent action requires a prompt"


@pytest.mark.parametrize("hook", _hooks(), ids=lambda h: h["name"])
def test_hook_script_exists(hook):
    command = hook["action"].get("command", "")
    for token in command.split():
        if token.startswith(".kiro/"):
            assert (ROOT / token).is_file(), f"{hook['name']}: missing {token}"
        elif token.endswith(".py"):
            assert (KIRO / "hooks" / token).is_file(), f"{hook['name']}: missing gate {token}"


@pytest.mark.parametrize("hook", _hooks(), ids=lambda h: h["name"])
def test_tool_matchers_target_real_kiro_tools(hook):
    """A matcher alternative copied from another harness never fires.

    For PreToolUse/PostToolUse the matcher is tested against the TOOL NAME, so
    `apply_patch` (Codex), `Write`/`Edit`/`MultiEdit` (Claude) or a Q tool name here
    would silently disable the gate.
    """
    if hook["trigger"] not in {"PreToolUse", "PostToolUse"}:
        return
    matcher = hook.get("matcher")
    if not matcher:
        return
    unknown = [part for part in matcher.split("|") if part not in KNOWN_TOOL_NAMES]
    assert not unknown, f"{hook['name']}: matcher targets non-Kiro tool names {unknown}"


def test_write_gates_cover_every_write_tool_spelling():
    """Every content-bearing write tool must reach the blocking gates.

    `fs_write` alone is not enough: an edit arriving as `str_replace` or `fs_append`
    would bypass the credential, codegen and artifact gates entirely.
    """
    required = {"fs_write", "str_replace", "fs_append"}
    blocking = {
        "adop-block-credentials",
        "adop-enforce-template-codegen",
        "adop-validate-artifacts",
        "adop-auditor-write-scope",
    }
    for hook in _hooks():
        if hook["name"] not in blocking:
            continue
        covered = set(hook.get("matcher", "").split("|"))
        assert required <= covered, (
            f"{hook['name']}: matcher misses {sorted(required - covered)}"
        )


def test_phase_gate_targets_the_subagent_tool():
    hook = next(h for h in _hooks() if h["name"] == "adop-phase-1-gate")
    assert "subagent" in hook["matcher"].split("|")


# --------------------------------------------------------------------------------------
# Exit contract, through the launcher -- this is what Kiro actually observes
# --------------------------------------------------------------------------------------

def test_launcher_denies_credentials_with_exit_2():
    result = _via_launcher(
        "block_credentials.py",
        _write_payload("workloads/demo/config/source.yaml", "password: hunter22\n"),
    )
    assert result.returncode == 2, f"gate failed open: rc={result.returncode}"
    assert "credential" in result.stderr.lower()


def test_launcher_inspects_kiro_native_payload_keys():
    """Kiro sends path/text, the shared gates read file_path/content.

    Without the launcher's normalisation the gate sees an empty body and allows a write
    carrying an AWS key -- exit 0, no complaint, no sign anything was wrong.
    """
    result = _via_launcher(
        "block_credentials.py",
        _write_payload("workloads/demo/config/s.yaml", "aws_secret_access_key: AKIAIOSFODNN7EXAMPLE\n"),
    )
    assert result.returncode == 2


def test_launcher_inspects_str_replace_payload():
    result = _via_launcher(
        "block_credentials.py",
        {
            "hook_event_name": "preToolUse",
            "tool_name": "str_replace",
            "tool_input": {"path": "workloads/demo/c.yaml", "new_str": "api_key: abcdef123456"},
        },
    )
    assert result.returncode == 2


def test_launcher_denies_generated_artifact_write_with_exit_2():
    result = _via_launcher(
        "enforce_template_codegen.py",
        _write_payload("workloads/demo/dags/x.py", "print(1)"),
    )
    assert result.returncode == 2
    assert "render" in result.stderr.lower()


def test_codegen_gate_leaves_config_writable():
    """Specs live in config/ and must stay writable; only the renderer's output is closed."""
    result = _via_launcher(
        "enforce_template_codegen.py",
        _write_payload("workloads/demo/config/silver.yaml", "zone: silver\n"),
    )
    assert result.returncode == 0, result.stderr


def test_launcher_denies_bad_python_with_exit_2():
    result = _via_launcher(
        "validate_artifacts.py",
        _write_payload("workloads/demo/scripts/x.py", "def ("),
    )
    assert result.returncode == 2
    assert "syntax" in result.stderr.lower()


def test_launcher_forwards_advisory_findings():
    """Non-blocking findings must reach the agent, not vanish on an exit-0 path."""
    result = _via_launcher(
        "validate_artifacts.py",
        _write_payload("workloads/demo/dags/ok.py", "with DAG() as d:\n    pass\n", "postToolUse"),
    )
    assert result.returncode == 0
    assert "retries" in result.stdout


def test_launcher_handles_path_only_file_event():
    """PostFileSave carries a bare path and no tool_input; the gate must still run."""
    result = _via_launcher(
        "validate_artifacts.py",
        {"hook_event_name": "postFileSave", "path": "workloads/customer_orders/config/semantic.yaml"},
    )
    assert result.returncode in (0, 2)


def test_launcher_fails_closed_on_gating_event(tmp_path):
    """A gate that cannot deliver a verdict must not resolve to allow."""
    crasher = KIRO / "hooks" / "_pytest_crash.py"
    crasher.write_text("import sys\nsys.stderr.write('boom\\n')\nsys.exit(1)\n")
    try:
        gating = _via_launcher("_pytest_crash.py", _write_payload("workloads/d/x.py", "x"))
        assert gating.returncode == 2, "PreToolUse must fail closed"
        advisory = _via_launcher("_pytest_crash.py", {"hook_event_name": "userPromptSubmit", "prompt": "hi"})
        assert advisory.returncode == 0, "a broken capture hook must not block the user"
    finally:
        crasher.unlink(missing_ok=True)


def test_launcher_does_not_require_jq():
    """The launcher must not depend on a binary that may be absent; see its docstring."""
    assert "jq" not in LAUNCHER.read_text()
    result = subprocess.run(
        [str(LAUNCHER), "block_credentials.py"],
        cwd=ROOT,
        input=json.dumps(_write_payload("workloads/demo/config/s.yaml", "password: hunter22\n")),
        text=True, capture_output=True, check=False,
        env={"PATH": "/usr/bin:/bin", "HOME": str(ROOT)},
    )
    assert result.returncode == 2


# --------------------------------------------------------------------------------------
# Phase 1 gate: the hook and the driver must not disagree
# --------------------------------------------------------------------------------------

def test_phase_gate_denies_missing_discovery():
    result = _run(
        "adapters/kiro/.kiro/hooks/phase_gate.py",
        {"tool_name": "subagent", "tool_input": {"workload_name": "missing_workload"}},
    )
    assert result.returncode == 0
    assert '"permissionDecision": "deny"' in result.stdout


@pytest.mark.parametrize(
    "workload",
    sorted(p.parent.parent.name for p in ROOT.glob("workloads/*/run/context.json")),
)
def test_phase_gate_agrees_with_the_driver(workload):
    """The gate is implemented twice. Prove the copies still agree.

    They did not: the driver was taught that `ontology_opt_in: false` is a valid answer
    and the hook was not, so the hook blocked a workload `kiro_workflow.py gate` passed.
    A boolean opt-out deadlocked the run with no way forward.
    """
    driver = subprocess.run(
        [sys.executable, "scripts/kiro_workflow.py", "gate", "--workload", workload],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    hook = _via_launcher(
        "phase_gate.py",
        {
            "hook_event_name": "preToolUse",
            "tool_name": "subagent",
            "tool_input": {"workload_name": workload},
        },
    )
    driver_blocks = driver.returncode != 0
    hook_blocks = hook.returncode == 2
    assert driver_blocks == hook_blocks, (
        f"{workload}: driver blocks={driver_blocks} but hook blocks={hook_blocks}\n"
        f"driver: {driver.stdout}\nhook: {hook.stderr}"
    )


# --------------------------------------------------------------------------------------
# Auditor write scope
# --------------------------------------------------------------------------------------

def test_kiro_auditor_write_scope_denies_artifact_write():
    result = _run(
        "adapters/kiro/.kiro/hooks/auditor_write_gate.py",
        {
            "agent_name": "requirements-auditor",
            "tool_input": {"path": "workloads/demo/config/source.yaml"},
        },
    )
    assert result.returncode == 0
    assert '"permissionDecision": "deny"' in result.stdout


def test_auditor_deny_message_lists_each_path_once():
    result = _run(
        ".kiro/hooks/auditor_write_gate.py",
        {
            "agent_name": "requirements-auditor",
            "tool_input": {
                "path": "workloads/demo/config/source.yaml",
                "file_path": "workloads/demo/config/source.yaml",
            },
        },
    )
    reason = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert reason.count("workloads/demo/config/source.yaml") == 1


def test_auditor_outputs_are_permitted():
    result = _run(
        ".kiro/hooks/auditor_write_gate.py",
        {
            "agent_name": "requirements-auditor",
            "tool_input": {"path": "workloads/demo/run/requirements_audit.json"},
        },
    )
    assert json.loads(result.stdout) == {}


def test_auditor_agent_enforces_its_own_write_scope():
    """The hook cannot see which agent is calling, so the agent definition must enforce it."""
    agent = json.loads((KIRO / "agents" / "requirements-auditor.json").read_text())
    rules = agent["permissions"]["rules"]
    deny = [r for r in rules if r["capability"] == "fs_write" and r["effect"] == "deny"]
    assert deny, "auditor has no fs_write deny rule"
    excluded = set(deny[0].get("exclude", []))
    assert any("requirements_audit.json" in path for path in excluded)
    assert any("decisions.jsonl" in path for path in excluded)
    assert any("trace_events.jsonl" in path for path in excluded)

    gate_suffixes = re.findall(
        r'"(/[^"]+\.(?:json|jsonl))"',
        (KIRO / "hooks" / "auditor_write_gate.py").read_text(),
    )
    for suffix in gate_suffixes:
        assert any(path.endswith(suffix.lstrip("/")) for path in excluded), (
            f"{suffix} is allowed by the hook but not by permissions.rules"
        )


def test_auditor_has_no_aws_mcp_or_network():
    """AGENTS.md and manifest.yaml declare the auditor evidence-only."""
    agent = json.loads((KIRO / "agents" / "requirements-auditor.json").read_text())
    denied = {
        rule["capability"]
        for rule in agent["permissions"]["rules"]
        if rule["effect"] == "deny"
    }
    assert {"mcp", "web_fetch", "web_search", "subagent"} <= denied
    assert agent["includeMcpJson"] is False
    shell_deny = [
        rule for rule in agent["permissions"]["rules"]
        if rule["capability"] == "shell" and rule["effect"] == "deny"
    ]
    assert shell_deny, "auditor shell is unrestricted"
    assert any(pattern.startswith("aws ") for pattern in shell_deny[0]["match"])


# --------------------------------------------------------------------------------------
# Agent definitions
# --------------------------------------------------------------------------------------

AGENT_FILES = sorted((KIRO / "agents").glob("*.json"))
SUB_AGENTS = [p for p in AGENT_FILES if p.stem != "requirements-auditor"]


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_fields_are_in_the_schema(path):
    agent = json.loads(path.read_text())
    unknown = sorted(set(agent) - VALID_AGENT_FIELDS)
    assert not unknown, f"{path.stem}: fields outside Kiro's agent schema: {unknown}"
    for field in ("name", "description", "prompt", "tools"):
        assert agent.get(field), f"{path.stem}: missing required field {field}"


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_tools_are_real_kiro_tools(path):
    """`glob` and `grep` are Claude Code tool names and restrict nothing in Kiro."""
    agent = json.loads(path.read_text())
    for field in ("tools", "allowedTools"):
        for tool in agent.get(field, []):
            if tool.startswith("@"):
                continue
            assert tool in KNOWN_TOOL_NAMES, f"{path.stem}: {field} has non-Kiro tool {tool!r}"


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_permission_rules_are_well_formed(path):
    agent = json.loads(path.read_text())
    for rule in agent["permissions"]["rules"]:
        assert rule["capability"] in VALID_CAPABILITIES, rule
        assert rule["effect"] in {"allow", "ask", "deny"}, rule
        assert isinstance(rule["match"], list) and rule["match"], rule


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_resources_resolve(path):
    """18 of 21 `resources` entries pointed at a `skills/` directory that does not exist."""
    agent = json.loads(path.read_text())
    assert agent.get("resources"), f"{path.stem}: no resources"
    for resource in agent["resources"]:
        assert isinstance(resource, str), resource
        target = resource.split("://", 1)[1]
        if any(ch in target for ch in "*?"):
            assert list(ROOT.glob(target)), f"{path.stem}: {resource} matches nothing"
        else:
            assert (ROOT / target).exists(), f"{path.stem}: {resource} does not exist"


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_agents_load_steering_explicitly(path):
    """Kiro does not auto-include steering into a custom agent's context."""
    agent = json.loads(path.read_text())
    assert any(
        ".kiro/steering" in resource for resource in agent["resources"]
    ), f"{path.stem}: never loads .kiro/steering, so it cannot see the discovery gate"


@pytest.mark.parametrize("path", SUB_AGENTS, ids=lambda p: p.stem)
def test_sub_agents_have_no_mcp_and_cannot_spawn_peers(path):
    """invariant sub-agent-no-mcp, enforced by the harness rather than by the prompt."""
    agent = json.loads(path.read_text())
    denied = {r["capability"] for r in agent["permissions"]["rules"] if r["effect"] == "deny"}
    assert {"mcp", "subagent", "shell"} <= denied, f"{path.stem}: denies only {denied}"
    assert agent["includeMcpJson"] is False
    assert not agent.get("mcpServers")


@pytest.mark.parametrize("path", SUB_AGENTS, ids=lambda p: p.stem)
def test_sub_agents_cannot_hand_write_generated_artifacts(path):
    agent = json.loads(path.read_text())
    denied = [
        pattern
        for rule in agent["permissions"]["rules"]
        if rule["capability"] == "fs_write" and rule["effect"] == "deny"
        for pattern in rule["match"]
    ]
    for directory in ("scripts", "dags", "sql"):
        assert any(f"/{directory}/" in pattern for pattern in denied), (
            f"{path.stem}: nothing denies writes to workloads/*/{directory}/"
        )


# --------------------------------------------------------------------------------------
# Steering
# --------------------------------------------------------------------------------------

STEERING_FILES = sorted((KIRO / "steering").glob("*.md"))


@pytest.mark.parametrize("path", STEERING_FILES, ids=lambda p: p.stem)
def test_steering_front_matter_is_valid(path):
    """`paths:` is Claude Code's key. Kiro reads `inclusion` + `fileMatchPattern`.

    An unrecognised key falls through to always-included, so a file meant to load
    conditionally quietly loads on every single interaction instead.
    """
    front = _front_matter(path)
    if front is None:
        return
    assert "paths" not in front, f"{path.name}: `paths:` is Claude's key, not Kiro's"
    inclusion = front.get("inclusion")
    assert inclusion in VALID_INCLUSION, f"{path.name}: inclusion={inclusion!r}"
    if inclusion == "fileMatch":
        pattern = front.get("fileMatchPattern")
        assert pattern, f"{path.name}: fileMatch without fileMatchPattern"
        assert isinstance(pattern, (str, list))
    if inclusion == "auto":
        assert front.get("name"), f"{path.name}: auto without name"
        assert front.get("description"), f"{path.name}: auto without description"


@pytest.mark.parametrize("path", STEERING_FILES, ids=lambda p: p.stem)
def test_steering_file_references_resolve(path):
    for reference in re.findall(r"#\[\[file:([^\]]+)\]\]", path.read_text()):
        assert (ROOT / reference).exists(), f"{path.name}: dangling #[[file:{reference}]]"


@pytest.mark.parametrize("path", STEERING_FILES, ids=lambda p: p.stem)
def test_steering_does_not_cite_other_harnesses(path):
    """Steering that names a Claude or Codex construct sends the Kiro user nowhere."""
    text = path.read_text()
    for leak in (
        "`AskUserQuestion`", "`SendMessage`", "`Agent` tool",
        "$command-onboard-workflow", "$command-devops-workflow",
        ".claude/", ".codex/skills/command-",
    ):
        assert leak not in text, f"{path.name}: references {leak}"


def test_steering_documents_the_gates_it_claims_to():
    """01-human-gate-examples described a gate the code does not implement.

    It said `enforce_template_codegen.py` covers `config/` and is conditional on a
    `.discovery_complete` marker. The script covers only scripts/dags/sql, does so
    unconditionally, and documents config/ as deliberately writable.
    """
    text = (KIRO / "steering" / "01-human-gate-examples.md").read_text()
    gate = (KIRO / "hooks" / "enforce_template_codegen.py").read_text()
    assert "config,scripts,dags,sql" not in text
    assert "(scripts|dags|sql)" in gate
    assert "unconditional" in text.lower()


# --------------------------------------------------------------------------------------
# MCP
# --------------------------------------------------------------------------------------

def test_kiro_mcp_profiles_are_valid():
    active = json.loads((KIRO / "settings" / "mcp.json").read_text())
    sys.path.insert(0, str(ROOT / "scripts"))
    from mcp_demo import active_profile_mode

    if active_profile_mode() != "demo":
        assert list(active["mcpServers"]) == ["aws-mcp"]
    else:
        assert active == json.loads((ROOT / ".mcp.json").read_text())

    optional = json.loads((KIRO / "settings" / "mcp.optional.json").read_text())
    servers = optional["mcpServers"]
    for name in ("snowflake-native", "databricks-native", "teradata"):
        assert servers[name].get("disabled") is True, f"{name} must ship disabled"


def test_kiro_mcp_covers_the_canonical_registry():
    registry = yaml.safe_load((ROOT / "tool-registry" / "servers.yaml").read_text())
    canonical = {server["name"] for server in registry["servers"]}
    available = set(json.loads((KIRO / "settings" / "mcp.json").read_text())["mcpServers"])
    available |= set(json.loads((KIRO / "settings" / "mcp.optional.json").read_text())["mcpServers"])
    assert canonical <= available, f"missing canonical servers: {sorted(canonical - available)}"


def test_kiro_config_has_no_hardcoded_identifiers():
    """AGENTS.md security rules: no secrets, no account IDs, no bucket names in source."""
    forbidden = re.compile(
        r"AKIA[0-9A-Z]{16}|(?<![\w.])\d{12}(?![\w.])|vpc-[0-9a-f]{8}|subnet-[0-9a-f]{8}"
    )
    for path in sorted(KIRO.rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".md", ".py", ".sh"}:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "EXAMPLE" in line or "AWS::AccountId" in line:
                continue
            match = forbidden.search(line)
            assert not match, f"{path.relative_to(ROOT)}:{number}: {match.group(0)}"
