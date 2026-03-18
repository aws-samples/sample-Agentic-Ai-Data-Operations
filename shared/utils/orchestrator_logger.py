"""
Orchestrator-level logging for pipeline execution.

Provides visual phase boundaries and a structured pipeline summary
so operators can quickly scan console output to understand what happened.

Usage:
    from shared.utils.orchestrator_logger import OrchestratorLogger

    logger = OrchestratorLogger("customer_master", "run-abc123")
    logger.phase_start(3, "Metadata Agent")
    # ... run agent ...
    logger.phase_complete(3, "success", artifacts=[...], test_results={...})
    logger.pipeline_summary()
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional


class OrchestratorLogger:
    """Consistent logging across the entire pipeline run."""

    def __init__(self, workload_name: str, run_id: str):
        self.workload = workload_name
        self.run_id = run_id
        self.start_time = datetime.now(timezone.utc)
        self.phase_log: List[Dict] = []

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

    def phase_retry(self, phase: int, attempt: int, reason: str):
        print(
            f"  PHASE {phase} RETRY (attempt {attempt}): {reason}\n"
            f"----------------------------------------------------------------"
        )

    def phase_escalate(self, phase: int, reason: str):
        print(
            f"  PHASE {phase} ESCALATED TO HUMAN: {reason}\n"
            f"================================================================"
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
