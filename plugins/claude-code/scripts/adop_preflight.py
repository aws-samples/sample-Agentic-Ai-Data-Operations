#!/usr/bin/env python3
"""Report what this machine can and cannot do with the ADOP plugin.

    python3 "$CLAUDE_PLUGIN_ROOT/scripts/adop_preflight.py"

## Why this exists

The plugin has two distinct capability tiers and they need very different things. Most of
ADOP — the discovery questions, the specs, rendering artifacts, checking drift — is entirely
local and needs no AWS account at all. Only source profiling and deployment need
credentials. Until now nothing told a user which tier they were in, and the command's Phase 0
health check is a prompt asking the model to look, not a deterministic test, so a missing
dependency surfaced as a confusing failure several minutes into a run.

Exit codes: 0 if the local tier works, 1 if something required for it is missing. A
degraded AWS tier is reported but never fails the check, because generating a pipeline
without an AWS account is a legitimate way to use this.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

OK, WARN, BAD = "  ok  ", " warn ", " MISS "


def line(status: str, name: str, detail: str = "") -> None:
    print(f"[{status}] {name:<34} {detail}")


def have(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def check_local() -> list[str]:
    """Everything needed to generate a pipeline. No AWS involved."""
    print("\nLOCAL TIER — discovery, specs, rendering, drift checking")
    print("-" * 74)
    missing = []

    v = sys.version_info
    if (v.major, v.minor) >= (3, 10):
        line(OK, "python >= 3.10", f"{v.major}.{v.minor}.{v.micro}")
    else:
        line(BAD, "python >= 3.10", f"found {v.major}.{v.minor} — the renderer needs 3.10+")
        missing.append("python>=3.10")

    for mod, why in (
        ("jinja2", "renders the artifact templates"),
        ("jsonschema", "validates a spec against its contract"),
        ("yaml", "reads the spec files"),
    ):
        if have(mod):
            line(OK, mod, why)
        else:
            line(BAD, mod, f"{why} — pip install {'pyyaml' if mod == 'yaml' else mod}")
            missing.append(mod)

    # The vendored library has to be intact, or the renderer fails in a way that looks
    # like a spec problem rather than an install problem.
    for rel, what in (
        ("lib/shared/codegen/renderer.py", "the renderer"),
        ("lib/shared/templates/VERSION", "template versions"),
        ("lib/contracts/v1", "the spec contracts"),
        ("scripts/adop_render.py", "the render CLI"),
    ):
        p = PLUGIN_ROOT / rel
        if p.exists():
            line(OK, rel.split("/")[-1], what)
        else:
            line(BAD, rel, f"{what} — the plugin install is incomplete")
            missing.append(rel)

    n = len(list((PLUGIN_ROOT / "lib" / "shared" / "templates").glob("*.j2")))
    line(OK if n >= 7 else WARN, "templates", f"{n} found (expected 7)")

    return missing


def check_aws() -> list[str]:
    """Only source profiling and deployment need any of this."""
    print("\nAWS TIER — profiling a real source, and deploying")
    print("-" * 74)
    gaps = []

    if have("boto3"):
        line(OK, "boto3", "AWS SDK")
    else:
        line(WARN, "boto3", "pip install boto3 — needed to profile a source or deploy")
        gaps.append("boto3")

    for tool in ("uv", "uvx"):
        if shutil.which(tool):
            line(OK, tool, "launches the MCP servers")
        else:
            line(WARN, tool, "the 13 MCP servers launch via uv/uvx — https://docs.astral.sh/uv/")
            gaps.append(tool)

    # Report what the credential chain would resolve, without requiring boto3.
    env_key = os.environ.get("AWS_ACCESS_KEY_ID")
    profile = os.environ.get("AWS_PROFILE")
    cfg = Path.home() / ".aws"
    if env_key:
        line(OK, "AWS credentials", "AWS_ACCESS_KEY_ID is set in the environment")
    elif profile:
        line(OK, "AWS credentials", f"AWS_PROFILE={profile}")
    elif (cfg / "credentials").is_file() or (cfg / "config").is_file():
        line(OK, "AWS credentials", "~/.aws present — the default chain applies")
    else:
        line(WARN, "AWS credentials", "none found; profiling and deploy will not work")
        gaps.append("credentials")

    if have("boto3"):
        try:
            import boto3  # noqa: PLC0415

            ident = boto3.client("sts").get_caller_identity()
            acct = ident.get("Account", "?")
            line(OK, "sts get-caller-identity", f"account {acct}")
        except Exception as e:
            line(WARN, "sts get-caller-identity", f"{type(e).__name__} — credentials not usable")
            gaps.append("sts")

    # Three of the nine uvx-installed servers are yanked from PyPI and cannot start.
    # Stated here so it is expected rather than alarming.
    line(WARN, "3 of 13 MCP servers", "core, lambda, cost-explorer are yanked from PyPI")

    return gaps


def check_context() -> None:
    print("\nCONTEXT — where you are matters")
    print("-" * 74)
    cwd = Path.cwd()
    project_hooks = cwd / ".claude" / "hooks"
    if project_hooks.is_dir():
        line(
            WARN,
            "inside a project with .claude/hooks",
            "the plugin's PreToolUse hooks will STAND DOWN here",
        )
        print(
            "        The project's own hooks take precedence, which is deliberate — but it\n"
            "        means you are testing the project's gate, not the plugin's. To exercise\n"
            "        the plugin, run from a directory without .claude/hooks/."
        )
    else:
        line(OK, "no competing project hooks", "the plugin's hooks will enforce")

    if (cwd / "workloads").is_dir():
        n = len([p for p in (cwd / "workloads").iterdir() if p.is_dir()])
        line(OK, "workloads/", f"{n} existing")
    else:
        line(OK, "workloads/", "will be created on first run")

    try:
        subprocess.run(["git", "rev-parse", "--git-dir"], cwd=cwd,
                       capture_output=True, check=True)
        line(OK, "git repository", "generated artifacts will be reviewable as a diff")
    except Exception:
        line(WARN, "git repository", "not a git repo — you will not see artifacts as a diff")


def main() -> int:
    print("=" * 74)
    print("ADOP plugin preflight")
    print(f"plugin: {PLUGIN_ROOT}")
    print(f"cwd:    {Path.cwd()}")
    print("=" * 74)

    missing = check_local()
    gaps = check_aws()
    check_context()

    print("\n" + "=" * 74)
    if missing:
        print("LOCAL TIER BLOCKED — cannot render a pipeline until these are installed:")
        print(f"    {' '.join(missing)}")
        print("\n    pip install jinja2 jsonschema pyyaml")
        return 1

    print("LOCAL TIER READY. You can run /adop:onboard-workflow now:")
    print("    - it will ask the Phase 1 discovery questions")
    print("    - sub-agents will write specs, validated against the contracts")
    print("    - the renderer will produce PySpark, SQL and a DAG with provenance headers")
    print("    - adop_check_drift.py will verify them")
    print("\n    No AWS account or test data is needed for any of that. Describe a source")
    print("    path that does not exist yet and the pipeline is still generated — the")
    print("    artifacts are code, and they run against real data later.")

    if gaps:
        print(f"\nAWS TIER DEGRADED — missing: {' '.join(sorted(set(gaps)))}")
        print("    Affects only: profiling a real source (Phase 3) and deploying (Phase 5).")
        print("    Everything above still works.")
    else:
        print("\nAWS TIER READY — profiling and deployment available.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
