#!/usr/bin/env python3
"""SessionStart hook — inject in-flight run state so a resumed or compacted
orchestrator recovers its place from disk instead of re-asking the human.

Reads every `workloads/*/run/context.json` and reports the most recently started
run that has not reached Phase 5, plus how far its sub-agents got. Read-only.

Input:  hook JSON on stdin (unused; SessionStart carries no tool payload).
Output: `hookSpecificOutput.additionalContext` on stdout, or nothing at all when
        there is no in-flight run — a session with no active workload should not
        pay for this context.

Never blocks and never raises: a malformed context.json is reported as a warning
so the orchestrator revalidates it, rather than failing session startup.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Phase 5 is deploy. Once a run is there, run/context.json is history, not state.
TERMINAL_PHASES = {"5", "5.9", "5.10", "5.11", "complete"}

MAX_DECISIONS = 5


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
        return None, f"{path.relative_to(PROJECT_ROOT)} is not valid JSON ({exc.msg})"
    except OSError as exc:
        return None, f"{path.relative_to(PROJECT_ROOT)} could not be read ({exc.strerror})"
    if not isinstance(data, dict):
        return None, f"{path.relative_to(PROJECT_ROOT)} is not a JSON object"
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
            lines.append(f"  recent decisions ({run_dir.relative_to(PROJECT_ROOT)}/decisions.jsonl):")
            lines.extend(f"    - {d}" for d in tail)

        lines.append(
            f"  Read {run_dir.relative_to(PROJECT_ROOT)}/context.json before generating anything."
        )

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
    try:
        main()
    except Exception as exc:  # never break session startup
        print(f"inject_run_context: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(0)
