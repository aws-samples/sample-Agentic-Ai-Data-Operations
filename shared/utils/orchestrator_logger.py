"""
Orchestrator-level logging for pipeline execution.

Provides visual phase boundaries, a structured pipeline summary,
and three-surface trace events (operational/cognitive/contextual)
via AgentTracer integration.

Trace logs are written to: workloads/{workload}/logs/{datetime}_{workload}.jsonl
This path is gitignored (workloads/*/logs/).

Usage:
    from shared.utils.orchestrator_logger import OrchestratorLogger

    logger = OrchestratorLogger("customer_master", "run-abc123")
    logger.phase_start(3, "Metadata Agent")
    # ... run agent ...
    logger.phase_complete(3, "success", artifacts=[...], test_results={...})
    logger.link_sub_agent_trace(agent_output_dict, "Metadata Agent", phase=3)
    logger.pipeline_summary()

    # Trace is auto-written to workloads/customer_master/logs/20260323_103000_customer_master.jsonl
    # Or flush manually: logger.tracer.flush_to_file("custom/path.jsonl")
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.logging.agent_tracer import AgentTracer


def _default_trace_path(workload_name: str) -> str:
    """Generate default trace output path under workloads/{name}/logs/."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = Path("workloads") / workload_name / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir / f"{ts}_{workload_name}.jsonl")


class OrchestratorLogger:
    """Consistent logging across the entire pipeline run.

    Preserves all original console output while also emitting structured
    trace events via AgentTracer for post-run analysis.

    Trace output defaults to workloads/{workload}/logs/{datetime}_{workload}.jsonl
    """

    def __init__(self, workload_name: str, run_id: str, *,
                 trace_output_path: Optional[str] = None):
        self.workload = workload_name
        self.run_id = run_id
        self.start_time = datetime.now(timezone.utc)
        self.phase_log: List[Dict] = []

        # Default trace path: workloads/{name}/logs/{datetime}_{name}.jsonl
        output_path = trace_output_path or _default_trace_path(workload_name)
        self.trace_output_path = output_path

        # Layer 1 tracer — emits structured events alongside console output
        self.tracer = AgentTracer(
            run_id=run_id,
            workload_name=workload_name,
            output_path=output_path,
        )

        # Emit pipeline start contextual event
        self.tracer.contextual_event(
            "pipeline_start",
            agent_name="orchestrator",
            payload={"workload": workload_name, "run_id": run_id},
        )

    def phase_start(self, phase: int, agent: str):
        entry = {
            "phase": phase,
            "agent": agent,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }
        self.phase_log.append(entry)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(
            f"\n"
            f"================================================================\n"
            f"  PHASE {phase}: {agent}\n"
            f"  {now}\n"
            f"================================================================"
        )

        # Trace event
        self.tracer.operational_event(
            "phase_start", agent_name=agent, phase=phase, status="running",
        )

    def phase_complete(
        self,
        phase: int,
        status: str,
        artifacts: Optional[List[str]] = None,
        test_results: Optional[Dict] = None,
    ):
        artifacts = artifacts or []
        test_results = test_results or {}

        if self.phase_log:
            current = self.phase_log[-1]
            current["status"] = status
            current["completed_at"] = datetime.now(timezone.utc).isoformat()
            current["artifacts"] = artifacts
            current["tests"] = test_results

        passed = test_results.get("passed", 0)
        total = test_results.get("total", 0)
        icon = "PASS" if status == "success" else "FAIL"
        print(
            f"  PHASE {phase} COMPLETE: {icon} | "
            f"Artifacts: {len(artifacts)}, Tests: {passed}/{total} passed\n"
            f"----------------------------------------------------------------"
        )

        # Trace event
        self.tracer.operational_event(
            "phase_complete", agent_name=self.phase_log[-1]["agent"] if self.phase_log else "",
            phase=phase, status=status,
            payload={"artifacts_count": len(artifacts),
                     "tests_passed": passed, "tests_total": total},
        )

    def phase_retry(self, phase: int, attempt: int, reason: str):
        print(
            f"  PHASE {phase} RETRY (attempt {attempt}): {reason}\n"
            f"----------------------------------------------------------------"
        )

        self.tracer.operational_event(
            "phase_retry", phase=phase, status="retry",
            payload={"attempt": attempt, "reason": reason},
        )

    def phase_escalate(self, phase: int, reason: str):
        print(
            f"  PHASE {phase} ESCALATED TO HUMAN: {reason}\n"
            f"================================================================"
        )

        self.tracer.operational_event(
            "phase_escalate", phase=phase, status="escalated",
            payload={"reason": reason},
        )

    def link_sub_agent_trace(self, agent_output_dict: Dict[str, Any],
                             agent_name: str = "",
                             phase: Optional[int] = None):
        """Import cognitive decisions from a sub-agent's AgentOutput (Layer 3 link)."""
        self.tracer.ingest_agent_decisions(
            agent_output_dict, agent_name=agent_name, phase=phase,
        )

    def test_gate(self, phase: int, agent_name: str, passed: bool,
                  details: Optional[Dict] = None):
        """Record a test gate result."""
        self.tracer.operational_event(
            "test_gate_pass" if passed else "test_gate_fail",
            agent_name=agent_name, phase=phase,
            status="success" if passed else "failed",
            payload=details or {},
        )

    def pipeline_summary(self):
        """Final summary after all phases complete."""
        total_artifacts = sum(len(p.get("artifacts", [])) for p in self.phase_log)
        total_tests = sum(p.get("tests", {}).get("total", 0) for p in self.phase_log)
        passed_tests = sum(
            p.get("tests", {}).get("passed", 0) for p in self.phase_log
        )
        failed_phases = [p for p in self.phase_log if p["status"] != "success"]
        duration = datetime.now(timezone.utc) - self.start_time

        overall = "SUCCESS" if not failed_phases else "FAILED"

        print(
            f"\n"
            f"================================================================\n"
            f"  PIPELINE EXECUTION SUMMARY\n"
            f"================================================================\n"
            f"  Workload:   {self.workload}\n"
            f"  Run ID:     {self.run_id}\n"
            f"  Duration:   {duration}\n"
            f"  Status:     {overall}\n"
            f"  Phases:     {len(self.phase_log)}\n"
            f"  Artifacts:  {total_artifacts}\n"
            f"  Tests:      {passed_tests}/{total_tests} passed\n"
            f"================================================================"
        )
        if failed_phases:
            print("  FAILED PHASES:")
            for p in failed_phases:
                print(f"    - Phase {p['phase']}: {p['agent']} ({p['status']})")
            print("================================================================")

        # Trace event
        self.tracer.contextual_event(
            "pipeline_complete",
            agent_name="orchestrator",
            payload={
                "status": overall,
                "phases": len(self.phase_log),
                "artifacts": total_artifacts,
                "tests_passed": passed_tests,
                "tests_total": total_tests,
                "duration_seconds": duration.total_seconds(),
            },
        )

    def to_json(self) -> str:
        """Export the full run log as JSON for archival."""
        return json.dumps(
            {
                "workload": self.workload,
                "run_id": self.run_id,
                "started_at": self.start_time.isoformat(),
                "phases": self.phase_log,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
