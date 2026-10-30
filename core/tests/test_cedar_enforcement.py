"""Cedar policy enforcement on Claude Code, Codex and Kiro.

Every case runs the real hook (`.claude/hooks/cedar_gate.py`, identical on all
three platforms) against the real policies with the real Cedar engine
(cedarpy). Decisions are read from the engine directly so the tests hold in
both `audit` and `enforce` mode; the mode itself is tested separately.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "cedar_gate.py"
ENGINE = ROOT / "shared" / "utils" / "cedar_gate.py"
FAKE_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"  # split so no file in the repo holds a key-shaped string


def _cedar_python() -> str:
    for candidate in (sys.executable, str(ROOT / ".venv" / "bin" / "python")):
        probe = subprocess.run([candidate, "-c", "import cedarpy"], capture_output=True, check=False)
        if probe.returncode == 0:
            return candidate
    pytest.fail("cedarpy is a required dependency (pyproject.toml); install it into .venv")


def _decide(event: dict, principal: str | None = None, mode: str = "enforce",
            python: str | None = None, block_cedarpy: bool = False) -> dict:
    """Run the engine in-process under a cedarpy Python with an isolated mode file."""
    script = f"""
import json, sys, tempfile
from pathlib import Path
if {block_cedarpy!r}:
    sys.modules["cedarpy"] = None
sys.path.insert(0, {str(ROOT)!r})
import shared.utils.cedar_gate as g
tmp = Path(tempfile.mkdtemp())
g.MODE_FILE = tmp / "enforcement.json"
g.MODE_FILE.write_text(json.dumps({{"mode": {mode!r}}}))
g.DECISION_LOG = tmp / "decisions.jsonl"
allow, reason, record = g.decide(json.loads(sys.stdin.read()), {principal!r})
print(json.dumps({{"allow": allow, "reason": reason, "record": record}}))
"""
    result = subprocess.run([python or _cedar_python(), "-c", script], input=json.dumps(event),
                            text=True, capture_output=True, check=False, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _write(path: str, agent: str | None = None, content: str = "x: 1\n") -> dict:
    event = {"tool_name": "Write", "cwd": str(ROOT),
             "tool_input": {"file_path": path, "content": content}}
    if agent:
        event["agent_type"] = agent
    return event


# ── the policy set itself ───────────────────────────────────────────────────


def test_every_live_policy_validates_against_the_schema() -> None:
    script = f"""
import cedarpy, pathlib, sys
root = pathlib.Path({str(ROOT)!r}) / "shared" / "policies"
schema = (root / "schema.cedarschema").read_text()
bad = []
for p in sorted(root.rglob("*.cedar")):
    if "templates" in p.parts:
        continue
    v = cedarpy.validate_policies(p.read_text(), schema)
    if not v.validation_passed:
        bad.append(f"{{p}}: {{list(v.errors)[:2]}}")
print("\\n".join(bad)); sys.exit(1 if bad else 0)
"""
    result = subprocess.run([_cedar_python(), "-c", script], text=True, capture_output=True,
                            check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_agent_has_a_policy() -> None:
    names = {p.stem for p in (ROOT / "shared/policies/agent_authorization").glob("*.cedar")}
    for required in ("metadata_agent", "transformation_agent", "quality_agent", "dag_agent",
                     "ontology_staging_agent", "requirements_auditor_agent", "iac_agent",
                     "onboarding_agent", "general_agent", "global_protection"):
        assert required in names, f"missing shared/policies/agent_authorization/{required}.cedar"


# ── each ADOP agent may write exactly its documented outputs ────────────────

W = "workloads/orders"


@pytest.mark.parametrize(
    "agent,path",
    [
        ("metadata-agent", f"{W}/config/source.yaml"),
        ("metadata-agent", f"{W}/tests/unit/test_metadata.py"),
        ("transformation-agent", f"{W}/config/transformations.yaml"),
        ("transformation-agent", f"{W}/scripts/transform/silver.py"),
        ("transformation-agent", f"{W}/sql/silver/orders.sql"),
        ("transformation-agent", f"{W}/tests/unit/test_transformations.py"),
        ("quality-agent", f"{W}/config/quality_rules.yaml"),
        ("quality-agent", f"{W}/scripts/quality/check.py"),
        ("dag-agent", f"{W}/dags/orders_dag.py"),
        ("dag-agent", f"{W}/config/dag_spec.json"),
        ("ontology-agent", f"{W}/config/ontology.ttl"),
        ("iac-agent", f"{W}/iac/terraform/main.tf"),
        ("iac-agent", f"{W}/iac/policies/permits.cedar"),
        ("requirements-auditor", f"{W}/run/requirements_audit.json"),
        ("requirements-auditor", "logs/trace_events.jsonl"),
        ("metadata-agent", f"{W}/run/decisions.jsonl"),
        ("dag-agent", f"{W}/.handoffs/dag.json"),
    ],
)
def test_agent_may_write_its_documented_outputs(agent: str, path: str) -> None:
    out = _decide(_write(path, agent))
    assert out["allow"], out["reason"]


@pytest.mark.parametrize(
    "agent,path",
    [
        ("metadata-agent", f"{W}/dags/orders_dag.py"),
        ("metadata-agent", f"{W}/scripts/transform/x.py"),
        ("transformation-agent", f"{W}/dags/orders_dag.py"),
        ("quality-agent", f"{W}/sql/x.sql"),
        ("dag-agent", f"{W}/scripts/transform/x.py"),
        ("requirements-auditor", f"{W}/config/source.yaml"),
        ("requirements-auditor", f"{W}/scripts/quality/check.py"),
        ("iac-agent", f"{W}/config/source.yaml"),
        # Sub-agents must not forge orchestrator-owned run state.
        ("metadata-agent", f"{W}/run/context.json"),
        ("transformation-agent", f"{W}/run/discovery_complete.json"),
        ("quality-agent", f"{W}/run/requirements_audit.json"),
    ],
)
def test_agent_is_denied_outside_its_outputs(agent: str, path: str) -> None:
    out = _decide(_write(path, agent))
    assert not out["allow"], f"{agent} was allowed to write {path}"


# ── policy files and the deploy gate: nobody, including the main conversation ─


@pytest.mark.parametrize("agent", [None, "metadata-agent", "Explore", "general-purpose", "iac-agent"])
@pytest.mark.parametrize(
    "path",
    [
        "shared/policies/agent_authorization/dag_agent.cedar",
        "shared/policies/guardrails/default_permit.cedar",
        "shared/policies/enforcement.json",
        "shared/policies/schema.cedarschema",
        f"{W}/run/deploy_gate.json",
    ],
)
def test_nobody_may_write_policies_or_the_deploy_gate(agent: str | None, path: str) -> None:
    out = _decide(_write(path, agent))
    assert not out["allow"], f"{agent or 'main conversation'} was allowed to write {path}"


@pytest.mark.parametrize(
    "command",
    [
        "sed -i 's/forbid/permit/' shared/policies/guardrails/default_permit.cedar",
        "echo 'permit(principal,action,resource);' >> shared/policies/global.cedar",
        "rm shared/policies/agent_authorization/global_protection.cedar",
        "git checkout HEAD~5 -- shared/policies/",
        "python3 -c \"open('shared/policies/enforcement.json','w').write('{}')\"",
        "cp /tmp/x.json workloads/orders/run/deploy_gate.json",
    ],
)
def test_shell_writes_to_policies_are_denied(command: str) -> None:
    out = _decide({"tool_name": "Bash", "cwd": str(ROOT), "tool_input": {"command": command}})
    assert not out["allow"], command


@pytest.mark.parametrize(
    "command",
    ["cat shared/policies/agent_authorization/dag_agent.cedar",
     "grep -rn forbid shared/policies/",
     "python3 -m pytest core/tests -q"],
)
def test_reading_policies_from_a_shell_is_allowed(command: str) -> None:
    out = _decide({"tool_name": "Bash", "cwd": str(ROOT), "tool_input": {"command": command}})
    assert out["allow"], out["reason"]


# ── general agents (human decision: write workloads/, never policies) ───────


@pytest.mark.parametrize("agent", ["Explore", "general-purpose", "some-plugin:helper"])
def test_general_agents_may_write_workloads(agent: str) -> None:
    for path in (f"{W}/config/notes.yaml", f"{W}/tests/unit/test_x.py", f"{W}/README.md"):
        out = _decide(_write(path, agent))
        assert out["allow"], f"{agent} {path}: {out['reason']}"
        assert out["record"]["principal"] == "general"


def test_general_agents_may_not_forge_gate_records() -> None:
    for path in (f"{W}/run/discovery_complete.json", f"{W}/run/context.json",
                 f"{W}/run/requirements_audit.json"):
        assert not _decide(_write(path, "general-purpose"))["allow"], path


# ── AWS / MCP ───────────────────────────────────────────────────────────────


def test_sub_agents_cannot_reach_aws_through_the_cli() -> None:
    event = {"tool_name": "Bash", "agent_type": "transformation-agent", "cwd": str(ROOT),
             "tool_input": {"command": "aws" + " s3 cp s3://bucket/data.csv ."}}
    assert not _decide(event)["allow"]


def test_main_conversation_may_use_aws() -> None:
    event = {"tool_name": "Bash", "cwd": str(ROOT),
             "tool_input": {"command": "aws" + " glue get-table --database-name d --name t"}}
    assert _decide(event)["allow"]


def test_ontology_agent_gets_only_its_granted_tool() -> None:
    allowed = {"tool_name": "mcp__glue-athena__get_table", "agent_type": "ontology-agent",
               "cwd": str(ROOT), "tool_input": {}}
    denied = dict(allowed, tool_name="mcp__iam__put_role_policy")
    assert _decide(allowed)["allow"]
    assert not _decide(denied)["allow"]


@pytest.mark.parametrize("agent", ["metadata-agent", "quality-agent", "dag-agent", "iac-agent"])
def test_sub_agents_cannot_invoke_mcp_tools(agent: str) -> None:
    event = {"tool_name": "mcp__lakeformation__grant_permissions", "agent_type": agent,
             "cwd": str(ROOT), "tool_input": {}}
    assert not _decide(event)["allow"]


def test_kiro_use_aws_by_a_sub_agent_is_denied() -> None:
    event = {"tool_name": "use_aws", "cwd": str(ROOT),
             "tool_input": {"service_name": "glue", "operation_name": "create-job"}}
    assert not _decide(event, principal="transformation")["allow"]


# ── SEC-001 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("agent", [None, "metadata-agent", "general-purpose"])
def test_sec_001_blocks_hardcoded_secrets_for_everyone(agent: str | None) -> None:
    out = _decide(_write(f"{W}/config/source.yaml", agent, content=f"key: {FAKE_KEY}\n"))
    assert not out["allow"]
    assert "hardcoded secret" in out["reason"]


def test_sec_001_allows_clean_content() -> None:
    assert _decide(_write(f"{W}/config/source.yaml", "metadata-agent", "region: ${AWS_REGION}\n"))["allow"]


# ── principals per platform ─────────────────────────────────────────────────


def test_principal_comes_from_agent_type_on_claude_and_codex() -> None:
    assert _decide(_write(f"{W}/config/a.yaml", "metadata-agent"))["record"]["principal"] == "metadata"
    assert _decide(_write(f"{W}/config/a.yaml", "adop:metadata-agent"))["record"]["principal"] == "metadata"
    main = _decide(_write(f"{W}/config/a.yaml"))["record"]
    assert (main["principal"], main["execution_context"]) == ("onboarding", "main_conversation")


def test_kiro_principal_comes_from_the_agent_hook_argument() -> None:
    event = _write(f"{W}/dags/x.py")  # Kiro sends no agent_type
    assert not _decide(event, principal="metadata")["allow"]
    assert _decide(event, principal="dag")["allow"]


def test_codex_apply_patch_is_evaluated_per_file() -> None:
    patch = ("*** Begin Patch\n*** Add File: workloads/orders/dags/x.py\n+print(1)\n"
             "*** Update File: workloads/orders/config/source.yaml\n+a: 1\n*** End Patch\n")
    event = {"tool_name": "apply_patch", "agent_type": "metadata-agent", "cwd": str(ROOT),
             "tool_input": {"patch": patch}}
    out = _decide(event)
    assert not out["allow"] and "dags/x.py" in out["reason"]


# ── modes and failing closed ────────────────────────────────────────────────


def test_audit_mode_logs_but_does_not_block() -> None:
    out = _decide(_write("shared/policies/x.cedar"), mode="audit")
    assert out["allow"]
    assert out["reason"].startswith("[audit] would deny")
    assert out["record"]["denied"] is True


def test_missing_cedarpy_fails_closed_in_enforce_mode() -> None:
    out = _decide(_write(f"{W}/config/source.yaml", "metadata-agent"), block_cedarpy=True)
    assert not out["allow"]
    assert "Cedar engine unavailable" in out["reason"]


def test_unknown_mode_is_treated_as_enforce() -> None:
    out = _decide(_write("shared/policies/x.cedar"), mode="off")
    assert not out["allow"]


def test_ungoverned_reads_never_reach_the_engine() -> None:
    event = {"tool_name": "Read", "tool_input": {"file_path": "shared/policies/schema.cedarschema"}}
    result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), text=True,
                            capture_output=True, check=False, cwd=ROOT)
    assert result.returncode == 0


def test_hook_denies_when_the_engine_cannot_be_found(tmp_path: Path) -> None:
    lone = tmp_path / "cedar_gate.py"
    lone.write_bytes(HOOK.read_bytes())
    event = {"tool_name": "Write", "cwd": str(tmp_path),
             "tool_input": {"file_path": "x.yaml", "content": "a"}}
    result = subprocess.run([sys.executable, str(lone)], input=json.dumps(event), text=True,
                            capture_output=True, check=False, cwd=tmp_path)
    assert result.returncode == 2


# ── wiring on each platform ─────────────────────────────────────────────────


def test_hook_is_identical_on_every_platform() -> None:
    expected = HOOK.read_bytes()
    for copy in (".codex/hooks/cedar_gate.py", ".kiro/hooks/cedar_gate.py",
                 "adapters/codex/.codex/hooks/cedar_gate.py",
                 "adapters/kiro/.kiro/hooks/cedar_gate.py",
                 "adapters/claude-code/.claude/hooks/cedar_gate.py"):
        assert (ROOT / copy).read_bytes() == expected, copy


def test_claude_and_codex_register_the_gate_on_every_tool() -> None:
    for relative in (".claude/settings.json", ".codex/hooks.json"):
        entries = json.loads((ROOT / relative).read_text())["hooks"]["PreToolUse"]
        gate = [e for e in entries if "cedar_gate.py" in str(e)]
        assert gate and "matcher" not in gate[0], relative


@pytest.mark.parametrize(
    "agent,principal",
    [("metadata-agent", "metadata"), ("transformation-agent", "transformation"),
     ("quality-agent", "quality"), ("dag-agent", "dag"), ("ontology-agent", "ontology_staging"),
     ("requirements-auditor", "requirements_auditor"), ("iac-agent", "iac")],
)
def test_each_kiro_agent_carries_its_own_principal(agent: str, principal: str) -> None:
    config = json.loads((ROOT / ".kiro" / "agents" / f"{agent}.json").read_text())
    hooks = [h for h in config.get("hooks", []) if "cedar_gate.py" in str(h)]
    assert hooks and hooks[0]["trigger"] == "PreToolUse"
    assert hooks[0]["action"]["command"].endswith(f"cedar_gate.py --principal {principal}")


def test_kiro_launcher_forwards_the_principal_and_fails_closed() -> None:
    launcher = ROOT / ".kiro" / "hooks" / "adop_launcher.py"
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "fs_write",
                          "tool_input": {"path": f"{ROOT}/{W}/dags/x.py", "text": "x"}})
    missing = subprocess.run([sys.executable, str(launcher), "no_such_gate.py"], input=payload,
                             text=True, capture_output=True, check=False, cwd=ROOT)
    assert missing.returncode == 2, "a missing gate must deny on PreToolUse"
    source = launcher.read_text()
    assert "*argv[2:]" in source
