"""Unit tests for ScriptTracer utility."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from shared.utils.script_tracer import ScriptTracer, get_tracer


class TestScriptTracer:
    """Tests for ScriptTracer class."""

    def test_for_script_creates_tracer(self):
        """for_script() should create a tracer with inferred settings."""
        tracer = ScriptTracer.for_script(__file__)
        assert tracer is not None
        assert tracer.workload_name == "unknown"  # not in workloads/ path
        assert tracer.script_name == "test_script_tracer"

    def test_infers_workload_from_path(self):
        """Should infer workload name from workloads/{name}/scripts/ path."""
        fake_path = "/project/workloads/sales_transactions/scripts/transform/bronze_to_silver.py"
        tracer = ScriptTracer.for_script(fake_path)
        assert tracer.workload_name == "sales_transactions"

    def test_infers_data_zone_from_script_name(self):
        """Should infer data zone from script name."""
        tracer = ScriptTracer.for_script("/path/bronze_to_silver.py")
        assert tracer.data_zone == "silver"

        tracer = ScriptTracer.for_script("/path/silver_to_gold.py")
        assert tracer.data_zone == "gold"

    def test_context_manager(self):
        """Should work as context manager."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            output_path = f.name

        try:
            with ScriptTracer.for_script(__file__, output_path=output_path) as tracer:
                tracer.log_start(rows_in=100)
                tracer.log_complete(rows_out=95)

            # Check trace file was written
            assert Path(output_path).exists()
            lines = Path(output_path).read_text().strip().split("\n")
            assert len(lines) >= 2  # At least start + end events

            # Parse and verify structure
            for line in lines:
                event = json.loads(line)
                assert "timestamp" in event
                assert "run_id" in event
                assert "event_type" in event
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_log_transform(self):
        """Should log transform events with payload."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            output_path = f.name

        try:
            tracer = ScriptTracer.for_script(__file__, output_path=output_path)
            tracer.log_transform("deduplicate", rows_in=1000, rows_out=950)
            tracer.close()

            lines = Path(output_path).read_text().strip().split("\n")
            # Find the transform event
            transform_events = [
                json.loads(l) for l in lines
                if "deduplicate" in json.loads(l).get("event_type", "")
            ]
            assert len(transform_events) >= 1
            assert transform_events[0]["payload"]["rows_in"] == 1000
            assert transform_events[0]["payload"]["rows_out"] == 950
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_log_quality_check(self):
        """Should log quality check events with pass/fail status."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            output_path = f.name

        try:
            tracer = ScriptTracer.for_script(__file__, output_path=output_path)
            tracer.log_quality_check("completeness", passed=True, score=0.95)
            tracer.log_quality_check("uniqueness", passed=False, duplicates=12)
            tracer.close()

            lines = Path(output_path).read_text().strip().split("\n")
            events = [json.loads(l) for l in lines]

            # Find quality events
            quality_events = [e for e in events if "quality_" in e.get("event_type", "")]
            assert len(quality_events) == 2

            completeness = next(e for e in quality_events if "completeness" in e["event_type"])
            assert completeness["status"] == "pass"
            assert completeness["payload"]["score"] == 0.95

            uniqueness = next(e for e in quality_events if "uniqueness" in e["event_type"])
            assert uniqueness["status"] == "fail"
            assert uniqueness["payload"]["duplicates"] == 12
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_log_rows(self):
        """Should log row counts with pass rate calculation."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            output_path = f.name

        try:
            tracer = ScriptTracer.for_script(__file__, output_path=output_path)
            tracer.log_rows(rows_in=1000, rows_out=950, quarantined=50)
            tracer.close()

            lines = Path(output_path).read_text().strip().split("\n")
            events = [json.loads(l) for l in lines]

            rows_event = next(e for e in events if e.get("event_type") == "rows_processed")
            assert rows_event["payload"]["rows_in"] == 1000
            assert rows_event["payload"]["rows_out"] == 950
            assert rows_event["payload"]["quarantined"] == 50
            assert rows_event["payload"]["pass_rate"] == 0.95
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_log_decision(self):
        """Should log cognitive decisions."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            output_path = f.name

        try:
            tracer = ScriptTracer.for_script(__file__, output_path=output_path)
            tracer.log_decision(
                category="schema_inference",
                choice="order_id as primary key",
                reasoning="100% uniqueness",
                confidence="high"
            )
            tracer.close()

            lines = Path(output_path).read_text().strip().split("\n")
            events = [json.loads(l) for l in lines]

            decision_event = next(
                e for e in events if "decision_" in e.get("event_type", "")
            )
            assert decision_event["surface"] == "cognitive"
            assert decision_event["payload"]["choice_made"] == "order_id as primary key"
            assert decision_event["payload"]["confidence"] == "high"
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_env_var_override(self):
        """Should use environment variables when set."""
        os.environ["TRACE_RUN_ID"] = "test-run-123"
        os.environ["TRACE_WORKLOAD"] = "env_workload"
        os.environ["TRACE_PHASE"] = "5"

        try:
            tracer = ScriptTracer.for_script(__file__)
            assert tracer.run_id == "test-run-123"
            assert tracer.workload_name == "env_workload"
            assert tracer.phase == 5
        finally:
            del os.environ["TRACE_RUN_ID"]
            del os.environ["TRACE_WORKLOAD"]
            del os.environ["TRACE_PHASE"]


class TestGetTracer:
    """Tests for get_tracer convenience function."""

    def test_get_tracer_returns_script_tracer(self):
        """get_tracer() should return a ScriptTracer instance."""
        tracer = get_tracer(__file__)
        assert isinstance(tracer, ScriptTracer)


class TestTracedDecorator:
    """Tests for @ScriptTracer.traced decorator."""

    def test_traced_decorator(self):
        """@traced decorator should wrap function with tracing."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            output_path = f.name

        try:
            @ScriptTracer.traced(__file__, output_path=output_path)
            def sample_transform():
                return {"result": "ok"}

            result = sample_transform()
            assert result == {"result": "ok"}

            # Check trace file was written
            assert Path(output_path).exists()
            lines = Path(output_path).read_text().strip().split("\n")
            assert len(lines) >= 2
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_traced_decorator_injects_tracer(self):
        """@traced decorator should inject tracer if function accepts it."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            output_path = f.name

        try:
            @ScriptTracer.traced(__file__, output_path=output_path)
            def transform_with_tracer(tracer: ScriptTracer = None):
                assert tracer is not None
                tracer.log_transform("test_step", value=42)
                return "done"

            result = transform_with_tracer()
            assert result == "done"

            lines = Path(output_path).read_text().strip().split("\n")
            events = [json.loads(l) for l in lines]
            test_events = [e for e in events if "test_step" in e.get("event_type", "")]
            assert len(test_events) == 1
        finally:
            Path(output_path).unlink(missing_ok=True)
