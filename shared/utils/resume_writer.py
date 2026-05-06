"""
Hybrid RESUME.md writer for the Agentic Data Onboarding platform.

Scans `workloads/{name}/` and derives completion state from on-disk
signals (configs, scripts, ontology artifacts, deployment_summary.json).
Optionally enriches with timestamps from `logs/run_*/trace_events.jsonl`
or `logs/*.jsonl` when present.

Purpose: make an interrupted onboarding session recoverable. A human (or
a future Claude Code session) reads `workloads/{name}/RESUME.md` to know
which phases completed, what's blocking, and the exact prompt to paste
to resume.

Public API:
    write_resume_from_disk(workload_name, workload_root="workloads",
                           write_to_disk=True) -> str
    compute_workload_hash(workload_dir: Path) -> str

CLI:
    python3 -m shared.utils.resume_writer --workload claims
    python3 -m shared.utils.resume_writer --workload claims --dry-run
    python3 -m shared.utils.resume_writer --all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SMALL_FILE_THRESHOLD = 20  # bytes — files smaller than this are "suspect"


# ---------------------------------------------------------------------------
# Phase-scan results
# ---------------------------------------------------------------------------


@dataclass
class PhaseResult:
    key: str
    title: str
    done: bool
    evidence: str = ""
    mtime: Optional[float] = None


@dataclass
class TraceSummary:
    path: Path
    latest_ts: Optional[str] = None
    phases_seen: List[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Small readers / counters
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _file_nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def _file_suspect(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size < SMALL_FILE_THRESHOLD


def _semantic_has_entities(semantic_yaml: Path) -> Tuple[bool, str]:
    if not _file_nonempty(semantic_yaml):
        return False, "missing"
    text = _read_text(semantic_yaml)
    # Very light YAML probe — no PyYAML dep
    entities_match = re.search(r"^entities\s*:", text, re.MULTILINE)
    columns_match = re.search(r"^(columns|tables)\s*:", text, re.MULTILINE)
    # Also accept other common top-level shapes that indicate a populated semantic layer.
    other_match = re.search(r"^(measures|dimensions|fact_table|semantic)\s*:", text, re.MULTILINE)
    if not (entities_match or columns_match or other_match):
        return False, "semantic.yaml present but no entities/columns/tables/measures"
    # Count entities at top level (indent 2, line ending with colon under entities:),
    # stopping at the next top-level (no-indent) key.
    n_entities = 0
    if entities_match:
        block = text[entities_match.end():]
        m_end = re.search(r"^[A-Za-z_]\w*\s*:", block, re.MULTILINE)
        if m_end:
            block = block[:m_end.start()]
        n_entities = len(re.findall(r"^\s{2}[A-Za-z_]\w*\s*:\s*$", block, re.MULTILINE))
    n_cols = len(re.findall(r"^\s*-\s*name\s*:", text, re.MULTILINE))
    pieces = []
    if n_entities:
        pieces.append(f"{n_entities} entities")
    if n_cols:
        pieces.append(f"{n_cols} columns")
    return True, ", ".join(pieces) if pieces else "entities/columns defined"


def _count_rules(quality_yaml: Path) -> int:
    if not _file_nonempty(quality_yaml):
        return 0
    text = _read_text(quality_yaml)
    # Match `- rule_id:` or `- id:` under rules: list
    return len(re.findall(r"^\s*-\s*(?:rule_id|id)\s*:", text, re.MULTILINE))


def _extract_cron(schedule_yaml: Path) -> str:
    if not _file_nonempty(schedule_yaml):
        return ""
    text = _read_text(schedule_yaml)
    # Prefer explicit cron/schedule_interval keys with a non-empty value on the same line.
    # Strip trailing inline comments.
    for key in ("cron", "cron_expression", "schedule_interval"):
        m = re.search(
            rf"^\s*{key}\s*:\s*['\"]?([^'\"#\n]+?)['\"]?(?:\s*#.*)?$",
            text, re.MULTILINE,
        )
        if m and m.group(1).strip():
            return m.group(1).strip()
    return ""


def _count_test_files(tests_dir: Path, subdir: str) -> int:
    sub = tests_dir / subdir
    if not sub.is_dir():
        return 0
    return len(list(sub.glob("test_*.py")))


def _count_transform_scripts(transform_dir: Path) -> int:
    if not transform_dir.is_dir():
        return 0
    return len([p for p in transform_dir.glob("*.py") if p.name != "__init__.py"])


def _read_ontology_manifest(manifest_path: Path) -> Dict[str, int]:
    """
    Read counts from either the auto-generated ADOP manifest (int fields
    like `owl_class_count`) or a hand-authored manifest (list fields
    under `artifacts.ontology.classes` etc.).
    """
    if not _file_nonempty(manifest_path):
        return {}
    try:
        data = json.loads(_read_text(manifest_path))
    except Exception:
        return {}
    counts: Dict[str, int] = {}

    # Shape 1: auto-generated (flat int fields)
    for k in ("owl_class_count", "owl_datatype_property_count",
              "owl_object_property_count", "pii_flagged_count",
              "r2rml_triples_map_count"):
        if isinstance(data.get(k), int):
            counts[k] = data[k]

    # Shape 2: hand-authored (list fields under artifacts.ontology)
    ontology = (data.get("artifacts") or {}).get("ontology") or {}
    if "owl_class_count" not in counts and isinstance(ontology.get("classes"), list):
        counts["owl_class_count"] = len(ontology["classes"])
    if "owl_object_property_count" not in counts and isinstance(ontology.get("object_properties"), list):
        counts["owl_object_property_count"] = len(ontology["object_properties"])
    if "owl_datatype_property_count" not in counts and isinstance(ontology.get("data_properties_count"), int):
        counts["owl_datatype_property_count"] = ontology["data_properties_count"]

    return counts


def _has_account_topology(deployment_yaml: Path) -> Tuple[bool, str]:
    if not _file_nonempty(deployment_yaml):
        return False, ""
    text = _read_text(deployment_yaml)
    if not re.search(r"^account_topology\s*:", text, re.MULTILINE):
        return False, ""
    m = re.search(r"^\s*mode\s*:\s*['\"]?(single|multi)", text, re.MULTILINE)
    return True, (m.group(1) if m else "unknown")


# ---------------------------------------------------------------------------
# Trace parsing (tolerant)
# ---------------------------------------------------------------------------


def _find_latest_trace(logs_dir: Path) -> Optional[Path]:
    if not logs_dir.is_dir():
        return None
    candidates: List[Path] = []
    # Per-run traces (run_* subfolders)
    for run_dir in sorted(logs_dir.glob("run_*/")):
        t = run_dir / "trace_events.jsonl"
        if t.is_file():
            candidates.append(t)
    # Flat traces (including trace_events.jsonl at logs/ root, and dated *.jsonl)
    for p in sorted(logs_dir.glob("*.jsonl")):
        if p.is_file():
            candidates.append(p)
    if not candidates:
        return None
    # Pick most recent by mtime
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _parse_trace_safe(path: Path) -> Optional[TraceSummary]:
    try:
        summary = TraceSummary(path=path)
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                ts = ev.get("timestamp")
                if ts and (summary.latest_ts is None or ts > summary.latest_ts):
                    summary.latest_ts = ts
                phase = ev.get("phase")
                if isinstance(phase, int) and phase not in summary.phases_seen:
                    summary.phases_seen.append(phase)
        return summary
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------


def _scan_phases(workload_dir: Path) -> Tuple[Dict[str, PhaseResult], List[str]]:
    warnings: List[str] = []
    phases: Dict[str, PhaseResult] = {}

    config = workload_dir / "config"
    scripts = workload_dir / "scripts"
    dags = workload_dir / "dags"
    tests = workload_dir / "tests"

    src_yaml = config / "source.yaml"
    sem_yaml = config / "semantic.yaml"
    tr_yaml = config / "transformations.yaml"
    q_yaml = config / "quality_rules.yaml"
    sched_yaml = config / "schedule.yaml"
    dep_yaml = config / "deployment.yaml"
    ont_ttl = config / "ontology.ttl"
    map_ttl = config / "mappings.ttl"
    ont_manifest = config / "ontology_manifest.json"
    dep_summary = workload_dir / "deployment_summary.json"

    # Phase 1 — Discovery
    p1_done = _file_nonempty(src_yaml) and _file_nonempty(sem_yaml)
    p1_ev = "source.yaml + semantic.yaml" if p1_done else "missing source.yaml or semantic.yaml"
    phases["phase1_discovery"] = PhaseResult(
        "phase1_discovery", "Phase 1 — Discovery", p1_done, p1_ev,
        src_yaml.stat().st_mtime if src_yaml.exists() else None,
    )

    # Phase 4 — Metadata
    md_done, md_ev = _semantic_has_entities(sem_yaml)
    phases["phase4_metadata"] = PhaseResult(
        "phase4_metadata", "Phase 4 — Metadata Agent", md_done, md_ev,
        sem_yaml.stat().st_mtime if sem_yaml.exists() else None,
    )

    # Phase 4 — Transformation
    tr_scripts_n = _count_transform_scripts(scripts / "transform")
    tr_done = _file_nonempty(tr_yaml) and tr_scripts_n >= 1
    tr_ev = f"{tr_scripts_n} transform scripts + transformations.yaml" if tr_done else "missing transformations.yaml or transform scripts"
    phases["phase4_transformation"] = PhaseResult(
        "phase4_transformation", "Phase 4 — Transformation Agent", tr_done, tr_ev,
        tr_yaml.stat().st_mtime if tr_yaml.exists() else None,
    )

    # Phase 4 — Quality: look for any non-init Python in scripts/quality/
    q_dir = scripts / "quality"
    q_scripts = [p for p in q_dir.glob("*.py")
                 if p.name != "__init__.py"] if q_dir.is_dir() else []
    q_done = _file_nonempty(q_yaml) and len(q_scripts) >= 1
    n_rules = _count_rules(q_yaml)
    if q_done:
        q_ev = f"{n_rules} rules + {len(q_scripts)} quality script" + ("s" if len(q_scripts) != 1 else "")
    else:
        q_ev = "missing quality_rules.yaml or scripts/quality/*.py"
    phases["phase4_quality"] = PhaseResult(
        "phase4_quality", "Phase 4 — Quality Agent", q_done, q_ev,
        q_yaml.stat().st_mtime if q_yaml.exists() else None,
    )

    # Phase 4 — DAG
    workload_name = workload_dir.name
    dag_py = dags / f"{workload_name}_dag.py"
    dag_done = _file_nonempty(dag_py) and _file_nonempty(sched_yaml)
    cron = _extract_cron(sched_yaml)
    dag_ev = f"{workload_name}_dag.py + schedule `{cron}`" if dag_done else "missing DAG file or schedule.yaml"
    phases["phase4_dag"] = PhaseResult(
        "phase4_dag", "Phase 4 — DAG Agent", dag_done, dag_ev,
        dag_py.stat().st_mtime if dag_py.exists() else None,
    )

    # Phase 4 — Tests
    n_unit = _count_test_files(tests, "unit")
    n_int = _count_test_files(tests, "integration")
    tests_done = n_unit >= 1
    tests_ev = f"{n_unit} unit + {n_int} integration tests" if tests_done else "no unit tests found"
    phases["phase4_tests"] = PhaseResult(
        "phase4_tests", "Phase 4 — Tests", tests_done, tests_ev,
        (tests / "unit").stat().st_mtime if (tests / "unit").is_dir() else None,
    )

    # Phase 7 Step 8.5 — Ontology Staging
    ont_done = _file_nonempty(ont_ttl) and _file_nonempty(map_ttl) and _file_nonempty(ont_manifest)
    if ont_done:
        counts = _read_ontology_manifest(ont_manifest)
        pieces = []
        if "owl_class_count" in counts:
            pieces.append(f"{counts['owl_class_count']} classes")
        if "owl_datatype_property_count" in counts:
            pieces.append(f"{counts['owl_datatype_property_count']} datatype props")
        if "owl_object_property_count" in counts:
            pieces.append(f"{counts['owl_object_property_count']} object props")
        ont_ev = " / ".join(pieces) if pieces else "ontology.ttl + mappings.ttl + manifest"
    else:
        ont_ev = "missing ontology.ttl, mappings.ttl, or manifest"
    phases["phase7_step85_ontology"] = PhaseResult(
        "phase7_step85_ontology", "Phase 7 Step 8.5 — Ontology Staging", ont_done, ont_ev,
        ont_manifest.stat().st_mtime if ont_manifest.exists() else None,
    )

    # Phase 0 — Account Topology
    topo_done, topo_mode = _has_account_topology(dep_yaml)
    topo_ev = f"mode={topo_mode}" if topo_done else "not chosen (defaults to single)"
    phases["phase0_topology_chosen"] = PhaseResult(
        "phase0_topology_chosen", "Phase 0 — Account Topology", topo_done, topo_ev,
        dep_yaml.stat().st_mtime if dep_yaml.exists() else None,
    )

    # Phase 5 — Deploy started / complete
    # A trace exists means *some* orchestrator ran; it doesn't prove deploy.
    # Only flip Phase 5 started if the trace carries a phase==5 event, or if
    # run_* artefact directories exist (those are deploy-run folders per
    # workloads/*/logs/.gitignore convention).
    logs_dir = workload_dir / "logs"
    trace = _find_latest_trace(logs_dir)
    run_dirs = sorted(logs_dir.glob("run_*/")) if logs_dir.is_dir() else []
    trace_summary = _parse_trace_safe(trace) if trace else None
    trace_touched_phase5 = bool(trace_summary and 5 in trace_summary.phases_seen)
    p5_started = bool(run_dirs) or trace_touched_phase5
    if p5_started:
        if trace_summary is None and trace is not None:
            warnings.append(f"Trace file {trace} present but unparseable; falling back to mtime")
            ts_str = datetime.fromtimestamp(trace.stat().st_mtime, timezone.utc).isoformat()
        elif trace_summary:
            ts_str = trace_summary.latest_ts or datetime.fromtimestamp(trace.stat().st_mtime, timezone.utc).isoformat()
        else:
            ts_str = datetime.fromtimestamp(run_dirs[-1].stat().st_mtime, timezone.utc).isoformat()
        source = trace.name if trace_touched_phase5 else run_dirs[-1].name
        p5_started_ev = f"{'run folder' if not trace_touched_phase5 else 'trace'} {source}, last event {ts_str}"
    elif trace is not None:
        p5_started_ev = "trace present but no Phase 5 events (Phase 0-4 orchestrator only)"
    else:
        p5_started_ev = "no trace file in logs/"
    phases["phase5_deploy_started"] = PhaseResult(
        "phase5_deploy_started", "Phase 5 — Deploy started", p5_started, p5_started_ev,
        trace.stat().st_mtime if trace else None,
    )

    p5_done = _file_nonempty(dep_summary)
    p5_done_ev = "deployment_summary.json present" if p5_done else "not executed"
    phases["phase5_deploy_complete"] = PhaseResult(
        "phase5_deploy_complete", "Phase 5 — Deploy complete", p5_done, p5_done_ev,
        dep_summary.stat().st_mtime if dep_summary.exists() else None,
    )

    # Suspect-file warnings
    for path in (src_yaml, sem_yaml, tr_yaml, q_yaml, sched_yaml,
                 ont_ttl, map_ttl, ont_manifest, dep_yaml, dep_summary):
        if _file_suspect(path):
            warnings.append(f"{path.relative_to(workload_dir)} is present but smaller than {SMALL_FILE_THRESHOLD}B (suspect)")

    if not _file_nonempty(src_yaml):
        warnings.append("config/source.yaml missing — workload not yet onboarded")

    return phases, warnings


# ---------------------------------------------------------------------------
# Workload hash
# ---------------------------------------------------------------------------


def compute_workload_hash(workload_dir: Path) -> str:
    """SHA-256[:16] over sorted (rel_path, size, int(mtime)) tuples."""
    if not workload_dir.is_dir():
        raise FileNotFoundError(f"Not a directory: {workload_dir}")
    entries: List[Tuple[str, int, int]] = []
    skip_dir_names = {"__pycache__"}
    skip_files = {"RESUME.md", ".DS_Store"}
    for p in workload_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(workload_dir)
        # Exclusions
        parts = rel.parts
        if parts[0] == "logs" and len(parts) >= 2 and parts[1].startswith("run_"):
            continue
        if any(d in skip_dir_names for d in parts):
            continue
        if p.name in skip_files or p.name.endswith(".pyc"):
            continue
        st = p.stat()
        entries.append((str(rel), st.st_size, int(st.st_mtime)))
    entries.sort()
    h = hashlib.sha256()
    for rel, size, mtime in entries:
        h.update(f"{rel}|{size}|{mtime}\n".encode("utf-8"))
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Next-step prompt
# ---------------------------------------------------------------------------


def _build_next_step_prompt(workload_name: str, phases: Dict[str, PhaseResult], warnings: List[str]) -> str:
    p5_complete = phases["phase5_deploy_complete"].done
    p5_started = phases["phase5_deploy_started"].done
    topo_done = phases["phase0_topology_chosen"].done
    tests_done = phases["phase4_tests"].done
    phase4_all = all(phases[k].done for k in
                     ("phase4_metadata", "phase4_transformation", "phase4_quality", "phase4_dag"))
    p1_done = phases["phase1_discovery"].done

    if not p1_done:
        return (
            f"Start onboarding {workload_name}. Run prompts/data-onboarding-agent/"
            f"03-onboard-build-pipeline.md to fill out source.yaml + semantic.yaml "
            f"via the Phase 1 discovery template."
        )

    if not phase4_all:
        missing = [k for k in ("phase4_metadata", "phase4_transformation",
                               "phase4_quality", "phase4_dag") if not phases[k].done]
        return (
            f"Resume {workload_name} onboarding. Phase 1 is complete but Phase 4 "
            f"has gaps ({', '.join(missing)}). Re-run the Data Onboarding Agent "
            f"from Phase 4 so the missing sub-agents (Metadata, Transformation, "
            f"Quality, DAG) generate their artifacts with test gates."
        )

    if not tests_done:
        return (
            f"Resume {workload_name} onboarding. Artifacts complete but no unit "
            f"tests found. Re-run the relevant sub-agent (likely one that skipped "
            f"its test gate) before deploy."
        )

    if p5_complete:
        return (
            f"{workload_name} is deployed (deployment_summary.json present). "
            f"If you want a fresh run: decide whether to modify in place or "
            f"regenerate. Check workloads/{workload_name}/config/ against the "
            f"current source to spot drift."
        )

    if p5_started and not p5_complete:
        return (
            f"Deploy for {workload_name} started but did not complete. "
            f"Read the latest workloads/{workload_name}/logs/*.jsonl trace, find "
            f"the failed phase, and resume Phase 5 from that step. Run "
            f"`python shared/logging/trace_viewer.py workloads/{workload_name}/logs/...` "
            f"to inspect."
        )

    # Default: artifacts done, tests done, no deploy. Most common restart case.
    lines = [
        f"Resume workloads/{workload_name} onboarding. Artifacts complete "
        f"under workloads/{workload_name}/. No prior AWS deploy has run.",
        "",
        "Proceed with:",
        "",
        "1. Run Phase 0 health check (MCP servers + AWS resources).",
    ]
    if not topo_done:
        lines.append(
            f"2. Confirm account_topology for this workload "
            f"(default single). Write workloads/{workload_name}/config/deployment.yaml."
        )
        step = 3
    else:
        step = 2
    lines.append(f"{step}. Run `pytest workloads/{workload_name}/tests/unit/` — must pass before deploy.")
    lines.append(
        f"{step+1}. Dry-run `python workloads/{workload_name}/deploy_to_aws.py "
        f"--environment dev --region us-east-1 --dry-run` and show the "
        f"9-step deployment plan."
    )
    lines.append(f"{step+2}. Wait for my approval before any non-dry action.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def _render_resume_md(
    workload_name: str,
    phases: Dict[str, PhaseResult],
    warnings: List[str],
    workload_hash: str,
    source_label: str,
    trace_summary: Optional[TraceSummary] = None,
) -> str:
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    order = [
        "phase1_discovery",
        "phase4_metadata",
        "phase4_transformation",
        "phase4_quality",
        "phase4_dag",
        "phase4_tests",
        "phase7_step85_ontology",
        "phase0_topology_chosen",
        "phase5_deploy_started",
        "phase5_deploy_complete",
    ]

    lines = [
        f"# Resume: {workload_name}",
        "",
        f"Last updated: {now_iso} (auto-generated by shared/utils/resume_writer.py)",
        f"Source: {source_label}",
        f"Workload hash: {workload_hash}",
        "",
        "## Phases",
        "",
    ]
    for key in order:
        p = phases[key]
        mark = "x" if p.done else " "
        lines.append(f"- [{mark}] {p.title} — {p.evidence}")
    lines.append("")

    lines.append("## Warnings")
    lines.append("")
    if warnings:
        for w in warnings:
            lines.append(f"- {w}")
    else:
        lines.append("None detected.")
    lines.append("")

    lines.append("## Next step — paste into Claude Code")
    lines.append("")
    lines.append("```")
    lines.append(_build_next_step_prompt(workload_name, phases, warnings))
    lines.append("```")
    lines.append("")

    lines.append("## Links")
    lines.append("")
    lines.append(f"- Config:  workloads/{workload_name}/config/")
    lines.append(f"- Scripts: workloads/{workload_name}/scripts/")
    lines.append(f"- DAG:     workloads/{workload_name}/dags/{workload_name}_dag.py")
    lines.append(f"- Deploy:  workloads/{workload_name}/deploy_to_aws.py")
    lines.append(f"- Tests:   workloads/{workload_name}/tests/")
    lines.append(f"- README:  workloads/{workload_name}/README.md")
    lines.append("- Multi-account: docs/multi-account-deployment.md")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_resume_from_disk(
    workload_name: str,
    workload_root: str = "workloads",
    write_to_disk: bool = True,
) -> str:
    """
    Scan workloads/{workload_name}/, derive completion state, and return
    the RESUME.md content. If write_to_disk, also writes to
    workloads/{workload_name}/RESUME.md (overwriting).

    Raises:
        FileNotFoundError: if the workload directory does not exist.
    """
    workload_dir = Path(workload_root) / workload_name
    if not workload_dir.is_dir():
        raise FileNotFoundError(
            f"Workload directory not found: {workload_dir}"
        )

    phases, warnings = _scan_phases(workload_dir)
    workload_hash = compute_workload_hash(workload_dir)

    # Detect and parse trace (if present) purely to set the source label
    logs_dir = workload_dir / "logs"
    trace = _find_latest_trace(logs_dir)
    trace_summary = _parse_trace_safe(trace) if trace else None
    if trace_summary and trace_summary.latest_ts:
        source_label = "pull: trace + disk"
    else:
        source_label = "pull: disk-scan"

    content = _render_resume_md(
        workload_name=workload_name,
        phases=phases,
        warnings=warnings,
        workload_hash=workload_hash,
        source_label=source_label,
        trace_summary=trace_summary,
    )

    if write_to_disk:
        resume_path = workload_dir / "RESUME.md"
        resume_path.write_text(content, encoding="utf-8")

    return content


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _iter_workloads(workload_root: Path) -> List[str]:
    if not workload_root.is_dir():
        return []
    out = []
    for d in sorted(workload_root.iterdir()):
        if not d.is_dir():
            continue
        if (d / "config" / "source.yaml").is_file():
            out.append(d.name)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shared.utils.resume_writer",
        description="Scan a workload folder and write/update RESUME.md.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--workload", help="Workload name under workloads/")
    group.add_argument("--all", action="store_true",
                       help="Regenerate RESUME.md for every workloads/*/ with config/source.yaml")
    parser.add_argument("--workload-root", default="workloads",
                        help="Root directory containing workloads (default: workloads)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print RESUME.md content to stdout without writing")

    args = parser.parse_args(argv)
    root = Path(args.workload_root)

    if args.all:
        names = _iter_workloads(root)
        if not names:
            print(f"No workloads with config/source.yaml found in {root}", file=sys.stderr)
            return 1
        for name in names:
            content = write_resume_from_disk(name, args.workload_root,
                                             write_to_disk=not args.dry_run)
            if args.dry_run:
                print(f"--- {name} ---")
                print(content)
            else:
                print(f"Wrote {root}/{name}/RESUME.md")
        return 0

    # --workload
    content = write_resume_from_disk(args.workload, args.workload_root,
                                     write_to_disk=not args.dry_run)
    if args.dry_run:
        print(content)
    else:
        print(f"Wrote {root}/{args.workload}/RESUME.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
