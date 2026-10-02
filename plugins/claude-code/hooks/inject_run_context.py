#!/usr/bin/env python3
"""SessionStart hook — inject in-flight run state so a resumed or compacted
orchestrator recovers its place from disk instead of re-asking the human.

Translation of `.claude/hooks/inject_run_context.py`. The logic is unchanged; one
thing had to change, and it is the thing that makes a plugin a plugin:

    repo:    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    plugin:  PROJECT_ROOT = Path(os.getcwd())

`__file__` here resolves inside ~/.claude/plugins/cache/<marketplace>/adop/<version>/,
which is a copy of the plugin and contains no `workloads/`. Deriving the project root
from the hook's own location would make this hook scan the install cache, find nothing,
and stay silent forever — the failure would look exactly like "no in-flight run", which
is the same indistinguishable-silence bug this plugin's test suite exists to catch.
The working directory is the user's project, so that is what it reads.

Why the plugin needs this at all: the plugin ships
`skills/pipeline-conventions/` carrying `.claude/rules/11-shared-run-context.md`,
which instructs agents to read `run/context.json` and treat `human_answers` as
authoritative. Without this hook nothing surfaces that file at session start, so after
a compaction the orchestrator re-asks the human — the precise failure the rule exists
to prevent. Shipping the rule without the hook ships the instruction without the
mechanism.

Input:  hook JSON on stdin (unused; SessionStart carries no tool payload).
Output: `hookSpecificOutput.additionalContext` on stdout, or nothing at all when
        there is no in-flight run — a session with no active workload should not
        pay for this context.

Never blocks and never raises: a malformed context.json is reported as a warning
so the orchestrator revalidates it, rather than failing session startup.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stand_down import stand_down_if_project_owns  # noqa: E402

PROJECT_ROOT = Path(os.getcwd())

# Phase 5 is deploy. Once a run is there, run/context.json is history, not state.
TERMINAL_PHASES = {"5", "5.9", "5.10", "5.11", "complete"}

MAX_DECISIONS = 5


def _rel(path: Path) -> str:
    """Path relative to the project, falling back to the name.

    The repo original calls `relative_to(PROJECT_ROOT)` bare. Here PROJECT_ROOT is the
    working directory, which a symlinked or `cd`-ed invocation can put outside the
    path's ancestry, and `relative_to` raises ValueError on that. A display-only string
    must never be the thing that takes down session startup.
    """
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


def _emit(context: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        },
        sys.stdout,
    )


def _load(path: Path) -> tuple[dict | None, str | None]:
    """Return (context, warning). Exactly one is None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"{_rel(path)} is not valid JSON ({exc.msg})"
    except OSError as exc:
        return None, f"{_rel(path)} could not be read ({exc.strerror})"
    if not isinstance(data, dict):
        return None, f"{_rel(path)} is not a JSON object"
    return data, None


def _last_completed(ctx: dict) -> str:
    """Describe the furthest sub-agent step recorded in previous_phases."""
    phases = [p for p in ctx.get("previous_phases", []) if isinstance(p, dict)]
    if not phases:
        return "no sub-agent has completed yet"
    latest = max(phases, key=lambda p: (str(p.get("phase", "")), str(p.get("completed_at", ""))))
    return (
        f"Step {latest.get('phase', '?')} ({latest.get('agent', '?')}) "
        f"-> {latest.get('status', '?')}"
    )


def _decision_tail(run_dir: Path) -> list[str]:
    """Last few decision subjects from decisions.jsonl, newest last."""
    path = run_dir / "decisions.jsonl"
    if not path.exists():
        return []
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(d, dict):
                agent = d.get("agent") or d.get("category") or "agent"
                choice = d.get("choice_made") or d.get("decision_text") or ""
                out.append(f"{agent}: {choice}"[:110])
    except OSError:
        return []
    return out[-MAX_DECISIONS:]


def _answered_keys(ctx: dict) -> list[str]:
    answers = ctx.get("human_answers")
    if not isinstance(answers, dict):
        return []
    return sorted(k for k in answers if k != "recorded_at")


def main() -> None:
    sys.stdin.read()  # drain; SessionStart payload is not needed

    runs, warnings = [], []
    for path in sorted(PROJECT_ROOT.glob("workloads/*/run/context.json")):
        ctx, warning = _load(path)
        if warning:
            warnings.append(warning)
            continue
        if str(ctx.get("current_phase", "")) in TERMINAL_PHASES:
            continue
        runs.append((ctx, path.parent))

    if not runs and not warnings:
        return  # no in-flight run — stay silent

    lines = []

    if runs:
        # Most recently started run wins; ISO-8601 sorts lexicographically.
        ctx, run_dir = max(runs, key=lambda r: str(r[0].get("started_at", "")))
        workload = ctx.get("workload_name", run_dir.parent.name)

        lines.append("IN-FLIGHT ADOP RUN (from disk, not from this conversation):")
        lines.append(f"  workload:   {workload}")
        lines.append(f"  run_id:     {ctx.get('run_id', 'unknown')}")
        lines.append(f"  started_at: {ctx.get('started_at', 'unknown')}")
        if ctx.get("current_phase"):
            lines.append(f"  phase:      {ctx['current_phase']}")
        lines.append(f"  progress:   {_last_completed(ctx)}")

        answered = _answered_keys(ctx)
        if answered:
            lines.append(f"  human_answers on file: {', '.join(answered)}")
            lines.append(
                "  Those answers are AUTHORITATIVE. Do not re-ask the human for them, and do"
            )
            lines.append("  not override them with a value paraphrased from this conversation.")
        else:
            lines.append(
                "  human_answers is empty — the Phase 1 gate is NOT satisfied. Ask before building."
            )

        tail = _decision_tail(run_dir)
        if tail:
            lines.append(f"  recent decisions ({_rel(run_dir)}/decisions.jsonl):")
            lines.extend(f"    - {d}" for d in tail)

        lines.append(f"  Read {_rel(run_dir)}/context.json before generating anything.")

        if len(runs) > 1:
            others = ", ".join(
                str(c.get("workload_name", d.parent.name)) for c, d in runs if d != run_dir
            )
            lines.append(f"  Other in-flight runs: {others}")

    if warnings:
        if lines:
            lines.append("")
        lines.append("WARNING - unreadable run context:")
        lines.extend(f"  - {w}" for w in warnings)
        lines.append(
            "  Validate with shared.codegen.spec_loader.load_spec(path, 'run_context')"
            " before trusting it."
        )

    _emit("\n".join(lines))


if __name__ == "__main__":
    # Hooks are NOT namespaced — every match fires. Inside an ADOP checkout the
    # project's own copy already does this, so stand down rather than emit the
    # same block twice.
    if stand_down_if_project_owns("inject_run_context.py"):
        raise SystemExit(0)
    try:
        main()
    except Exception as exc:  # never break session startup
        print(f"inject_run_context: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(0)
