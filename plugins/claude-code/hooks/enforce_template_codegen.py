#!/usr/bin/env python3
"""PreToolUse hook: artifacts under workloads/*/{scripts,dags,sql}/ come only from the renderer.

This is what turns "deterministic" from a claim into a property. `CLAUDE.md:137` states that
all artifacts under those directories MUST be produced by the renderer and that free-form
generation is forbidden; without a hook, nothing stops an agent writing PySpark directly, and
the plugin's own predecessor claimed determinism in three places while shipping no enforcement
at all.

## Stricter than the repository's version, on purpose

The repo's `.claude/hooks/enforce_template_codegen.py` allows a write when
`ADOP_RENDERER_TOKEN` is set in the environment:

    if is_protected_path(file_path) and not token:   # line 80

Anything able to `export` that variable is therefore able to write a hand-authored artifact —
including the agent the hook is meant to constrain. This version has no bypass, because it does
not need one: the vendored renderer writes through `_atomic_write()` directly to disk, not
through the `Write` tool, so a legitimate render never reaches a PreToolUse hook. Removing the
exception costs nothing and closes the hole.

## It stands down inside an ADOP checkout

Hooks are not namespaced, so this would otherwise fire alongside the repository's own and deny
the same write twice. See `_stand_down.py`.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stand_down import stand_down_if_project_owns  # noqa: E402

PROTECTED = re.compile(r"workloads/[^/]+/(scripts|dags|sql)/")

# template_id -> the spec the renderer reads it from, so the deny message can name the
# next action instead of only the prohibition.
BY_DIRECTORY = {
    "scripts": "silver_transform (or bronze_ingestion / gold_aggregate)",
    "dags": "airflow_dag",
    "sql": "iceberg_ddl",
}


def target_paths(event: dict) -> list[str]:
    ti = event.get("tool_input") or {}
    paths = []
    if "file_path" in ti:
        paths.append(ti["file_path"])
    # MultiEdit carries an edits array; each entry may name its own file
    for edit in ti.get("edits") or []:
        if isinstance(edit, dict) and "file_path" in edit:
            paths.append(edit["file_path"])
    return [p for p in paths if isinstance(p, str)]


def deny_reason(path: str) -> str:
    m = PROTECTED.search(path)
    kind = m.group(1) if m else "scripts"
    workload = path.split("workloads/", 1)[1].split("/", 1)[0] if "workloads/" in path else "{name}"
    return (
        f"Refusing to write {path} directly.\n\n"
        f"Artifacts under workloads/*/{kind}/ come only from the renderer — free-form "
        f"generation is forbidden, because a hand-written artifact has no spec_hash and the "
        f"drift validator cannot tell it from a rendered one.\n\n"
        f"Write the spec to workloads/{workload}/config/ and render it:\n\n"
        f'    python3 "$CLAUDE_PLUGIN_ROOT/scripts/adop_render.py" \\\n'
        f"        --workload workloads/{workload} \\\n"
        f"        --template {BY_DIRECTORY.get(kind, 'silver_transform')} \\\n"
        f"        --out {path}\n\n"
        f"`adop_render.py --list` shows every template with its spec file and contract. "
        f"If the renderer reports MissingSlotError, extend the spec — never the template.\n\n"
        f"config/*.yaml is not protected by this hook: write specs there directly. But "
        f"check_discovery_gate.py does guard config/ until the workload has a "
        f"config/source.yaml or a .discovery_complete marker, so on a brand-new workload the "
        f"discovery questions come first. Hooks are not namespaced — both fire on one Write."
    )


def main() -> int:
    # The project's own hook takes precedence; two denials of the same write are noise.
    if stand_down_if_project_owns("enforce_template_codegen.py"):
        print("{}")
        return 0

    try:
        event = json.load(sys.stdin)
    except Exception:
        print("{}")
        return 0

    for path in target_paths(event):
        if PROTECTED.search(path):
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": deny_reason(path),
                }
            }))
            return 0

    print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
