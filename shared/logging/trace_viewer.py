"""
CLI viewer for trace_events.jsonl files.

Commands:
    --summary     High-level run overview (phases, durations, pass/fail)
    --decisions   Show only cognitive surface events (agent reasoning)
    --timeline    Chronological event list with durations
    --agent NAME  Filter to specific agent
    --phase N     Filter to specific phase
    --failures    Show only errors, retries, escalations
    --export-md   Generate agent_log.md (human-readable run narrative)
    --export-map  Generate cognitive_map.json (decision tree)

Usage:
    python3 -m shared.logging.trace_viewer trace_events.jsonl --summary
    python3 -m shared.logging.trace_viewer docs/logging_examples/ --decisions
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_events(path: str) -> List[Dict[str, Any]]:
    """Load events from a JSONL file or find one in a directory."""
    p = Path(path)
    if p.is_dir():
        candidates = list(p.glob("trace_events.jsonl"))
        if not candidates:
            candidates = list(p.glob("*.jsonl"))
        if not candidates:
            print(f"No .jsonl files found in {p}", file=sys.stderr)
            sys.exit(1)
        p = candidates[0]

    events = []
    with open(p) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"Warning: invalid JSON on line {line_num}, skipping",
                      file=sys.stderr)
    return events


def filter_events(events: List[Dict], *, agent: Optional[str] = None,
                  phase: Optional[int] = None) -> List[Dict]:
    """Apply agent and phase filters."""
    filtered = events
    if agent:
        agent_lower = agent.lower()
        filtered = [e for e in filtered
                    if agent_lower in e.get("agent_name", "").lower()]
    if phase is not None:
        filtered = [e for e in filtered if e.get("phase") == phase]
    return filtered


def _try_color(text: str, color_code: str) -> str:
    """Apply ANSI color if stdout is a terminal."""
    if sys.stdout.isatty():
        return f"\033[{color_code}m{text}\033[0m"
    return text


def _green(t: str) -> str:
    return _try_color(t, "32")


def _red(t: str) -> str:
    return _try_color(t, "31")


def _yellow(t: str) -> str:
    return _try_color(t, "33")


def _cyan(t: str) -> str:
    return _try_color(t, "36")


def _bold(t: str) -> str:
    return _try_color(t, "1")


def show_summary(events: List[Dict]):
    """High-level run overview."""
    if not events:
        print("No events found.")
        return

    run_id = events[0].get("run_id", "unknown")
    workload = events[0].get("workload_name", "unknown")

    # Collect phases
    phases = defaultdict(lambda: {"status": "unknown", "duration_ms": None, "agent": ""})
    for e in events:
        p = e.get("phase")
        if p is None:
            continue
        if e.get("status") in ("success", "complete"):
            phases[p]["status"] = "success"
        elif e.get("status") == "failed":
            phases[p]["status"] = "failed"
        if e.get("duration_ms"):
            phases[p]["duration_ms"] = e["duration_ms"]
        if e.get("agent_name"):
            phases[p]["agent"] = e["agent_name"]

    # Count by surface
    surface_counts = defaultdict(int)
    for e in events:
        surface_counts[e.get("surface", "unknown")] += 1

    # Failures
    failures = [e for e in events if e.get("status") in ("failed", "error")]

    print(_bold("=== TRACE SUMMARY ==="))
    print(f"  Run ID:    {run_id}")
    print(f"  Workload:  {workload}")
    print(f"  Events:    {len(events)}")
    print(f"  Surfaces:  operational={surface_counts['operational']}, "
          f"cognitive={surface_counts['cognitive']}, "
          f"contextual={surface_counts['contextual']}")
    print()

    if phases:
        print(_bold("  Phases:"))
        for p_num in sorted(phases):
            p = phases[p_num]
            status_str = _green("PASS") if p["status"] == "success" else _red("FAIL")
            dur = f"{p['duration_ms']:.0f}ms" if p["duration_ms"] else "n/a"
            print(f"    Phase {p_num}: {status_str}  {p['agent']:<30s} ({dur})")
        print()

    if failures:
        print(_red(f"  Failures: {len(failures)}"))
        for f_evt in failures[:5]:
            print(f"    - {f_evt.get('event_type')}: "
                  f"{f_evt.get('payload', {}).get('reason', f_evt.get('agent_name', ''))}")
    else:
        print(_green("  No failures."))


def show_decisions(events: List[Dict]):
    """Show only cognitive surface events."""
    cognitive = [e for e in events if e.get("surface") == "cognitive"]
    if not cognitive:
        print("No cognitive events found.")
        return

    print(_bold(f"=== AGENT DECISIONS ({len(cognitive)}) ==="))
    for i, e in enumerate(cognitive, 1):
        payload = e.get("payload", {})
        print(f"\n  {_cyan(f'[{i}]')} {e.get('event_type', 'decision')}"
              f" — {e.get('agent_name', 'unknown')}"
              f" (phase {e.get('phase', '?')})")
        if payload.get("reasoning"):
            print(f"      Reasoning: {payload['reasoning']}")
        if payload.get("choice_made"):
            print(f"      Choice:    {payload['choice_made']}")
        if payload.get("alternatives_considered"):
            alts = payload["alternatives_considered"]
            print(f"      Alternatives: {', '.join(str(a) for a in alts)}")
        if payload.get("confidence"):
            conf = payload["confidence"]
            color = _green if conf == "high" else (_yellow if conf == "medium" else _red)
            print(f"      Confidence: {color(conf)}")


def show_timeline(events: List[Dict]):
    """Chronological event list."""
    print(_bold(f"=== TIMELINE ({len(events)} events) ==="))
    for e in events:
        ts = e.get("timestamp", "")[:19]
        surface = e.get("surface", "?")[:4]
        dur = f" ({e['duration_ms']:.0f}ms)" if e.get("duration_ms") else ""
        status = e.get("status", "")
        status_str = f" [{status}]" if status else ""

        surface_color = {"oper": _cyan, "cogn": _yellow, "cont": lambda x: x}
        color_fn = surface_color.get(surface, lambda x: x)

        print(f"  {ts}  {color_fn(surface):>4s}  "
              f"{e.get('event_type', ''):30s}"
              f"{status_str}{dur}")


def show_failures(events: List[Dict]):
    """Show only errors, retries, and escalations."""
    fail_types = {"failed", "error", "retry", "escalated"}
    failures = [e for e in events
                if e.get("status") in fail_types
                or "retry" in e.get("event_type", "").lower()
                or "escalat" in e.get("event_type", "").lower()
                or "fail" in e.get("event_type", "").lower()]

    if not failures:
        print(_green("No failures, retries, or escalations found."))
        return

    print(_red(_bold(f"=== FAILURES & RETRIES ({len(failures)}) ===")))
    for e in failures:
        print(f"\n  {e.get('timestamp', '')[:19]}  {e.get('event_type')}")
        print(f"    Agent: {e.get('agent_name', 'n/a')}, Phase: {e.get('phase', 'n/a')}")
        payload = e.get("payload", {})
        if payload:
            for k, v in payload.items():
                print(f"    {k}: {v}")


def export_markdown(events: List[Dict], output_path: Optional[str] = None) -> str:
    """Generate agent_log.md — human-readable run narrative."""
    if not events:
        return "# Agent Log\n\nNo events recorded.\n"

    run_id = events[0].get("run_id", "unknown")
    workload = events[0].get("workload_name", "unknown")

    lines = [
        f"# Agent Log: {workload}",
        f"",
        f"**Run ID**: `{run_id}`  ",
        f"**Events**: {len(events)}  ",
        f"**Generated**: {datetime.utcnow().isoformat()}Z",
        "",
        "---",
        "",
    ]

    # Group by phase
    by_phase: Dict[Optional[int], List[Dict]] = defaultdict(list)
    for e in events:
        by_phase[e.get("phase")].append(e)

    for phase_num in sorted(by_phase, key=lambda x: (x is None, x)):
        phase_events = by_phase[phase_num]
        phase_label = f"Phase {phase_num}" if phase_num is not None else "General"
        agents = {e.get("agent_name") for e in phase_events if e.get("agent_name")}
        agent_str = ", ".join(sorted(agents)) if agents else "orchestrator"

        lines.append(f"## {phase_label} ({agent_str})")
        lines.append("")

        for e in phase_events:
            surface_badge = {"operational": "OP", "cognitive": "COG",
                             "contextual": "CTX"}.get(e.get("surface", ""), "?")
            status = f" [{e['status']}]" if e.get("status") else ""
            dur = f" ({e['duration_ms']:.0f}ms)" if e.get("duration_ms") else ""
            lines.append(f"- `[{surface_badge}]` **{e.get('event_type', '')}**"
                         f"{status}{dur}")

            payload = e.get("payload", {})
            if payload.get("reasoning"):
                lines.append(f"  - Reasoning: {payload['reasoning']}")
            if payload.get("choice_made"):
                lines.append(f"  - Choice: {payload['choice_made']}")

        lines.append("")

    md = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(md)
        print(f"Exported: {output_path}")

    return md


def export_cognitive_map(events: List[Dict],
                         output_path: Optional[str] = None) -> Dict:
    """Generate cognitive_map.json — decision tree from cognitive events."""
    cognitive = [e for e in events if e.get("surface") == "cognitive"]

    tree: Dict[str, Any] = {
        "run_id": events[0].get("run_id", "unknown") if events else "unknown",
        "workload_name": events[0].get("workload_name", "unknown") if events else "unknown",
        "total_decisions": len(cognitive),
        "agents": {},
    }

    for e in cognitive:
        agent = e.get("agent_name", "unknown")
        if agent not in tree["agents"]:
            tree["agents"][agent] = {"decisions": [], "count": 0}

        payload = e.get("payload", {})
        tree["agents"][agent]["decisions"].append({
            "decision_id": payload.get("decision_id", f"d-{tree['agents'][agent]['count'] + 1:03d}"),
            "category": e.get("event_type", payload.get("category", "unknown")),
            "choice_made": payload.get("choice_made", ""),
            "reasoning": payload.get("reasoning", ""),
            "alternatives_considered": payload.get("alternatives_considered", []),
            "confidence": payload.get("confidence", ""),
            "phase": e.get("phase"),
        })
        tree["agents"][agent]["count"] += 1

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(tree, f, indent=2)
        print(f"Exported: {output_path}")

    return tree


def main():
    parser = argparse.ArgumentParser(
        description="Trace viewer for agent pipeline runs",
        prog="python3 -m shared.logging.trace_viewer",
    )
    parser.add_argument("path", help="Path to trace_events.jsonl or directory")
    parser.add_argument("--summary", action="store_true",
                        help="High-level run overview")
    parser.add_argument("--decisions", action="store_true",
                        help="Show cognitive surface events (agent reasoning)")
    parser.add_argument("--timeline", action="store_true",
                        help="Chronological event list")
    parser.add_argument("--agent", type=str, default=None,
                        help="Filter to specific agent name")
    parser.add_argument("--phase", type=int, default=None,
                        help="Filter to specific phase number")
    parser.add_argument("--failures", action="store_true",
                        help="Show only errors, retries, escalations")
    parser.add_argument("--export-md", type=str, default=None, nargs="?",
                        const="agent_log.md",
                        help="Generate agent_log.md (default: agent_log.md)")
    parser.add_argument("--export-map", type=str, default=None, nargs="?",
                        const="cognitive_map.json",
                        help="Generate cognitive_map.json")

    args = parser.parse_args()

    events = load_events(args.path)
    events = filter_events(events, agent=args.agent, phase=args.phase)

    if not any([args.summary, args.decisions, args.timeline, args.failures,
                args.export_md is not None, args.export_map is not None]):
        # Default: show summary
        show_summary(events)
        return

    if args.summary:
        show_summary(events)
    if args.decisions:
        show_decisions(events)
    if args.timeline:
        show_timeline(events)
    if args.failures:
        show_failures(events)
    if args.export_md is not None:
        md = export_markdown(events, args.export_md)
        if not args.export_md or args.export_md == "agent_log.md":
            print(md)
    if args.export_map is not None:
        tree = export_cognitive_map(events, args.export_map)
        if not args.export_map or args.export_map == "cognitive_map.json":
            print(json.dumps(tree, indent=2))


if __name__ == "__main__":
    main()
