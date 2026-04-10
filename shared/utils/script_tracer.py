"""
Lightweight tracing utility for ETL scripts.

Provides a simple interface for scripts in workloads/*/scripts/ to emit
trace events without boilerplate. Works standalone or within Airflow DAGs.

The tracer picks up context from environment variables (set by DAG template)
or uses sensible defaults for local execution.

Environment Variables (optional):
    TRACE_RUN_ID      - Pipeline run identifier (default: auto-generated)
    TRACE_WORKLOAD    - Workload name (default: inferred from script path)
    TRACE_OUTPUT_PATH - Output file path (default: workloads/{name}/logs/)
    TRACE_PHASE       - Current phase number (default: 4)
    TRACE_DATA_ZONE   - Current data zone (default: inferred from script name)

Usage:
    from shared.utils.script_tracer import ScriptTracer

    # Option 1: Context manager (recommended)
    with ScriptTracer.for_script(__file__) as tracer:
        tracer.log_start(rows_in=1000)
        # ... do work ...
        tracer.log_transform("deduplicate", rows_in=1000, rows_out=950)
        tracer.log_complete(rows_out=950, status="success")

    # Option 2: Manual control
    tracer = ScriptTracer.for_script(__file__)
    tracer.log_start(rows_in=1000)
    # ... do work ...
    tracer.log_complete(rows_out=950, status="success")
    tracer.close()

    # Option 3: As decorator
    @ScriptTracer.traced(__file__)
    def run_transform():
        ...
"""

import functools
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from shared.logging.agent_tracer import AgentTracer


def _infer_workload_from_path(script_path: str) -> str:
    """Infer workload name from script path.

    Expects: workloads/{workload_name}/scripts/...
    Returns: workload_name or 'unknown'
    """
    parts = Path(script_path).resolve().parts
    try:
        idx = parts.index("workloads")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return "unknown"


def _infer_data_zone(script_path: str) -> str:
    """Infer data zone from script name.

    bronze_to_silver.py -> silver
    silver_to_gold.py -> gold
    quality_check.py -> (current zone, unknown)
    """
    name = Path(script_path).stem.lower()
    if "silver" in name and "gold" not in name:
        return "silver"
    elif "gold" in name:
        return "gold"
    elif "bronze" in name:
        return "bronze"
    return ""


def _infer_agent_name(script_path: str) -> str:
    """Infer agent name from script location.

    transform/ -> Transformation Agent
    quality/ -> Quality Agent
    governance/ -> Governance Agent
    """
    parent = Path(script_path).parent.name.lower()
    mapping = {
        "transform": "Transformation Agent",
        "quality": "Quality Agent",
        "governance": "Governance Agent",
        "bronze": "Ingestion Agent",
        "silver": "Transformation Agent",
        "gold": "Aggregation Agent",
        "access": "Access Control Agent",
        "quicksight": "Visualization Agent",
    }
    return mapping.get(parent, "ETL Script")


def _default_trace_path(workload_name: str) -> str:
    """Generate default trace output path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = Path("workloads") / workload_name / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir / f"{ts}_{workload_name}_script.jsonl")


class ScriptTracer:
    """Lightweight tracer for ETL scripts.

    Wraps AgentTracer with sensible defaults and a simpler interface
    for common ETL operations (transform, quality check, data movement).
    """

    def __init__(
        self,
        script_path: str,
        run_id: Optional[str] = None,
        workload_name: Optional[str] = None,
        output_path: Optional[str] = None,
        phase: Optional[int] = None,
        data_zone: Optional[str] = None,
        agent_name: Optional[str] = None,
    ):
        # Resolve from environment or infer from script path
        self.script_path = script_path
        self.script_name = Path(script_path).stem

        self.run_id = run_id or os.environ.get(
            "TRACE_RUN_ID", f"local-{uuid.uuid4().hex[:8]}"
        )
        self.workload_name = workload_name or os.environ.get(
            "TRACE_WORKLOAD", _infer_workload_from_path(script_path)
        )
        self.phase = phase or int(os.environ.get("TRACE_PHASE", "4"))
        self.data_zone = data_zone or os.environ.get(
            "TRACE_DATA_ZONE", _infer_data_zone(script_path)
        )
        self.agent_name = agent_name or _infer_agent_name(script_path)

        # Output path
        self.output_path = output_path or os.environ.get(
            "TRACE_OUTPUT_PATH", _default_trace_path(self.workload_name)
        )

        # Create the underlying tracer
        self._tracer = AgentTracer(
            run_id=self.run_id,
            workload_name=self.workload_name,
            output_path=self.output_path,
        )

        # Track timing
        self._start_time: Optional[datetime] = None
        self._span_active = False

    @classmethod
    def for_script(cls, script_path: str, **kwargs) -> "ScriptTracer":
        """Factory method to create a tracer for a script.

        Usage:
            tracer = ScriptTracer.for_script(__file__)
        """
        return cls(script_path, **kwargs)

    def __enter__(self) -> "ScriptTracer":
        """Start tracing span on context entry."""
        self._start_span()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """End tracing span on context exit."""
        if exc_type is not None:
            self.log_error(str(exc_val))
        self._end_span()

    def _start_span(self) -> None:
        """Internal: start a span for this script."""
        self._start_time = datetime.now(timezone.utc)
        self._tracer.operational_event(
            f"{self.script_name}_start",
            agent_name=self.agent_name,
            phase=self.phase,
            data_zone=self.data_zone,
            status="running",
            payload={"script": self.script_name},
        )
        self._span_active = True

    def _end_span(self) -> None:
        """Internal: end the span for this script."""
        if not self._span_active:
            return

        duration_ms = None
        if self._start_time:
            delta = datetime.now(timezone.utc) - self._start_time
            duration_ms = delta.total_seconds() * 1000

        self._tracer.operational_event(
            f"{self.script_name}_end",
            agent_name=self.agent_name,
            phase=self.phase,
            data_zone=self.data_zone,
            status="complete",
            duration_ms=duration_ms,
        )
        self._span_active = False

    def close(self) -> None:
        """Manually close the tracer (if not using context manager)."""
        self._end_span()

    # -------------------------------------------------------------------------
    # High-level logging methods for ETL operations
    # -------------------------------------------------------------------------

    def log_start(self, **payload) -> None:
        """Log the start of script execution with optional metadata."""
        if not self._span_active:
            self._start_span()

        self._tracer.operational_event(
            "script_start",
            agent_name=self.agent_name,
            phase=self.phase,
            data_zone=self.data_zone,
            status="running",
            payload={"script": self.script_name, **payload},
        )

    def log_complete(self, status: str = "success", **payload) -> None:
        """Log successful completion with metrics."""
        self._tracer.operational_event(
            "script_complete",
            agent_name=self.agent_name,
            phase=self.phase,
            data_zone=self.data_zone,
            status=status,
            payload={"script": self.script_name, **payload},
        )

    def log_error(self, error_message: str, **payload) -> None:
        """Log an error during script execution."""
        self._tracer.operational_event(
            "script_error",
            agent_name=self.agent_name,
            phase=self.phase,
            data_zone=self.data_zone,
            status="failed",
            payload={"script": self.script_name, "error": error_message, **payload},
        )

    def log_transform(self, transform_name: str, **payload) -> None:
        """Log a specific transformation step.

        Example:
            tracer.log_transform("deduplicate", rows_in=1000, rows_out=950)
            tracer.log_transform("pii_masking", columns_masked=["email", "phone"])
        """
        self._tracer.operational_event(
            f"transform_{transform_name}",
            agent_name=self.agent_name,
            phase=self.phase,
            data_zone=self.data_zone,
            payload=payload,
        )

    def log_quality_check(self, check_name: str, passed: bool, **payload) -> None:
        """Log a quality check result.

        Example:
            tracer.log_quality_check("completeness", passed=True, score=0.95)
            tracer.log_quality_check("uniqueness", passed=False, duplicates=12)
        """
        self._tracer.operational_event(
            f"quality_{check_name}",
            agent_name=self.agent_name,
            phase=self.phase,
            data_zone=self.data_zone,
            status="pass" if passed else "fail",
            payload=payload,
        )

    def log_rows(self, rows_in: int, rows_out: int, quarantined: int = 0) -> None:
        """Log row counts for a transformation step."""
        self._tracer.operational_event(
            "rows_processed",
            agent_name=self.agent_name,
            phase=self.phase,
            data_zone=self.data_zone,
            payload={
                "rows_in": rows_in,
                "rows_out": rows_out,
                "quarantined": quarantined,
                "pass_rate": round(rows_out / rows_in, 4) if rows_in > 0 else 0,
            },
        )

    def log_decision(
        self,
        category: str,
        choice: str,
        reasoning: str = "",
        confidence: str = "high",
        **context,
    ) -> None:
        """Log a cognitive decision (why something was done).

        Example:
            tracer.log_decision(
                category="schema_inference",
                choice="order_id as primary key",
                reasoning="Only column with 100% uniqueness",
                confidence="high"
            )
        """
        self._tracer.cognitive_event(
            f"decision_{category}",
            agent_name=self.agent_name,
            phase=self.phase,
            payload={
                "category": category,
                "choice_made": choice,
                "reasoning": reasoning,
                "confidence": confidence,
                **context,
            },
        )

    # -------------------------------------------------------------------------
    # Decorator for traced functions
    # -------------------------------------------------------------------------

    @staticmethod
    def traced(script_path: str, **tracer_kwargs) -> Callable:
        """Decorator to automatically trace a function.

        Usage:
            @ScriptTracer.traced(__file__)
            def run_transform():
                ...
        """

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                with ScriptTracer.for_script(script_path, **tracer_kwargs) as tracer:
                    # Inject tracer into kwargs if function accepts it
                    import inspect

                    sig = inspect.signature(func)
                    if "tracer" in sig.parameters:
                        kwargs["tracer"] = tracer
                    return func(*args, **kwargs)

            return wrapper

        return decorator


# -----------------------------------------------------------------------------
# Convenience function for one-liner usage
# -----------------------------------------------------------------------------


def get_tracer(script_path: str, **kwargs) -> ScriptTracer:
    """Convenience function to get a tracer for a script.

    Usage:
        from shared.utils.script_tracer import get_tracer
        tracer = get_tracer(__file__)
    """
    return ScriptTracer.for_script(script_path, **kwargs)
