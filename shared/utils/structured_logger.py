"""
Structured JSON logger for pipeline scripts.

Emits one JSON object per line to stderr, making logs parseable by
CloudWatch, Splunk, Datadog, or any log aggregation tool.

Usage:
    from shared.utils.structured_logger import StructuredLogger

    log = StructuredLogger("Transformation Agent", "customer_master", "run-abc123")
    log.info("Starting Bronze to Silver transform", rows=50000)
    log.warn("3 records quarantined", reason="null primary key")
    log.error("Quality gate failed", score=0.72, threshold=0.80)
    log.phase_boundary(4, "complete")
"""

import json
import sys
from datetime import datetime, timezone
from typing import Any

from shared.logging.otel_bridge import OpenTelemetryBridge


class StructuredLogger:
    """JSON-line logger with agent/workload context on every entry."""

    def __init__(
        self,
        agent: str,
        workload: str,
        run_id: str,
        *,
        otel_enabled: bool | None = None,
        otel_endpoint: str | None = None,
    ):
        self.context = {
            "agent": agent,
            "workload": workload,
            "run_id": run_id,
        }
        self._otel = OpenTelemetryBridge(
            run_id=run_id,
            workload_name=workload,
            enabled=otel_enabled,
            endpoint=otel_endpoint,
        )

    def log(self, level: str, message: str, **extra: Any):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            **self.context,
            "message": message,
            **extra,
        }
        print(json.dumps(entry, default=str), file=sys.stderr)
        self._otel.event(
            "structured_log",
            attributes={
                "adop.agent": self.context["agent"],
                "adop.workload": self.context["workload"],
                "adop.run_id": self.context["run_id"],
                "log.level": level,
                "log.message": message,
                "adop.fields": extra,
            },
        )

    def info(self, msg: str, **extra: Any):
        self.log("INFO", msg, **extra)

    def warn(self, msg: str, **extra: Any):
        self.log("WARN", msg, **extra)

    def error(self, msg: str, **extra: Any):
        self.log("ERROR", msg, **extra)

    def debug(self, msg: str, **extra: Any):
        self.log("DEBUG", msg, **extra)

    def phase_boundary(self, phase: int, status: str):
        """Emit a clear phase transition marker."""
        self.log("PHASE", f"Phase {phase}: {status}", phase=phase, status=status)

    def artifact_created(self, path: str, checksum: str):
        """Log when an artifact is written."""
        self.log("ARTIFACT", f"Created {path}", path=path, checksum=checksum)

    def test_result(self, suite: str, passed: int, failed: int):
        """Log test execution results."""
        self.log(
            "TEST",
            f"{suite}: {passed} passed, {failed} failed",
            suite=suite,
            passed=passed,
            failed=failed,
        )

    def close(self):
        """Flush optional native OTel output; JSON stderr logging is unaffected."""
        self._otel.close()
