"""
Unit tests for the deep agent logging system.

Tests:
  - AgentTracer initialization and field defaults
  - Three event methods (operational, cognitive, contextual)
  - JSONL output format
  - TraceContext span lifecycle
  - trace_viewer CLI commands
  - AgentOutput.add_decision() helper
  - Orchestrator <-> sub-agent trace linking
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.logging.agent_tracer import AgentTracer, TraceContext
from shared.logging.trace_viewer import (
    export_cognitive_map,
    export_markdown,
    filter_events,
    load_events,
    show_summary,
    show_decisions,
    show_failures,
    show_timeline,
)
from shared.templates.agent_output_schema import AgentOutput


# ── AgentTracer ──────────────────────────────────────────────────────


class TestAgentTracerInit:
    def test_basic_init(self):
        t = AgentTracer(run_id="run-001", workload_name="test_wl")
        assert t.run_id == "run-001"
        assert t.workload_name == "test_wl"
        assert t.trace_id  # auto-generated
        assert t.events == []
        assert t.current_span_id is None

    def test_custom_trace_id(self):
        t = AgentTracer(run_id="r", workload_name="w", trace_id="custom-123")
        assert t.trace_id == "custom-123"


class TestOperationalEvents:
    def test_emit_operational(self):
        t = AgentTracer(run_id="run-001", workload_name="wl")
        t.operational_event("phase_start", agent_name="Metadata Agent",
                            phase=3, status="running")
        assert len(t.events) == 1
        e = t.events[0]
        assert e["surface"] == "operational"
        assert e["event_type"] == "phase_start"
        assert e["agent_name"] == "Metadata Agent"
        assert e["phase"] == 3
        assert e["run_id"] == "run-001"
        assert e["workload_name"] == "wl"
        assert "timestamp" in e

    def test_operational_with_payload(self):
        t = AgentTracer(run_id="r", workload_name="w")
        t.operational_event("rows_processed", payload={"rows_in": 100, "rows_out": 95})
        assert t.events[0]["payload"]["rows_in"] == 100

    def test_operational_with_duration(self):
        t = AgentTracer(run_id="r", workload_name="w")
        t.operational_event("phase_complete", duration_ms=1234.5)
        assert t.events[0]["duration_ms"] == 1234.5


class TestCognitiveEvents:
    def test_emit_cognitive(self):
        t = AgentTracer(run_id="r", workload_name="w")
        t.cognitive_event("schema_inference", agent_name="Metadata Agent",
                          phase=3, payload={"reasoning": "types match CSV header"})
        e = t.events[0]
        assert e["surface"] == "cognitive"
        assert e["event_type"] == "schema_inference"
        assert e["payload"]["reasoning"] == "types match CSV header"


class TestContextualEvents:
    def test_emit_contextual(self):
        t = AgentTracer(run_id="r", workload_name="w")
        t.contextual_event("pipeline_start", data_zone="bronze",
                           payload={"config": "source.yaml"})
        e = t.events[0]
        assert e["surface"] == "contextual"
        assert e["data_zone"] == "bronze"


# ── TraceContext (spans) ─────────────────────────────────────────────


class TestTraceContext:
    def test_span_lifecycle(self):
        t = AgentTracer(run_id="r", workload_name="w")
        with t.span("phase_3", agent_name="Metadata Agent", phase=3) as ctx:
            assert ctx.span_id
            assert t.current_span_id == ctx.span_id
            assert ctx.end_time is None

        # After exiting: span is closed, stack is empty
        assert t.current_span_id is None
        assert ctx.end_time is not None
        assert ctx.duration_ms is not None
        assert ctx.duration_ms >= 0

    def test_nested_spans(self):
        t = AgentTracer(run_id="r", workload_name="w")
        with t.span("pipeline") as outer:
            with t.span("phase_3") as inner:
                assert inner.parent_span_id == outer.span_id
                assert t.current_span_id == inner.span_id
            assert t.current_span_id == outer.span_id
        assert t.current_span_id is None

    def test_span_emits_start_and_end_events(self):
        t = AgentTracer(run_id="r", workload_name="w")
        with t.span("test_phase", phase=1):
            pass
        types = [e["event_type"] for e in t.events]
        assert "test_phase_start" in types
        assert "test_phase_end" in types

    def test_span_end_has_duration(self):
        t = AgentTracer(run_id="r", workload_name="w")
        with t.span("test_phase"):
            pass
        end_event = [e for e in t.events if e["event_type"] == "test_phase_end"][0]
        assert end_event["duration_ms"] is not None
        assert end_event["duration_ms"] >= 0


# ── JSONL output ─────────────────────────────────────────────────────


class TestJSONLOutput:
    def test_flush_to_file(self, tmp_path):
        t = AgentTracer(run_id="r", workload_name="w")
        t.operational_event("e1")
        t.cognitive_event("e2")
        t.contextual_event("e3")

        out = tmp_path / "trace.jsonl"
        t.flush_to_file(str(out))

        lines = out.read_text().strip().split("\n")
        assert len(lines) == 3
        for line in lines:
            parsed = json.loads(line)
            assert "run_id" in parsed
            assert "surface" in parsed

    def test_streaming_output(self, tmp_path):
        out = tmp_path / "stream.jsonl"
        t = AgentTracer(run_id="r", workload_name="w", output_path=str(out))
        t.operational_event("test")

        # File written immediately
        assert out.exists()
        lines = out.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_valid_json_per_line(self, tmp_path):
        t = AgentTracer(run_id="r", workload_name="w")
        t.operational_event("e1", payload={"key": "value with \"quotes\""})
        t.cognitive_event("e2", payload={"list": [1, 2, 3]})

        out = tmp_path / "trace.jsonl"
        t.flush_to_file(str(out))

        for line in out.read_text().strip().split("\n"):
            json.loads(line)  # Should not raise


# ── AgentOutput.add_decision ─────────────────────────────────────────


class TestAgentOutputDecisions:
    def _make_output(self):
        return AgentOutput(
            agent_name="Metadata Agent",
            agent_type="metadata",
            workload_name="test",
            run_id="run-001",
            started_at="2026-03-23T10:00:00Z",
            completed_at="2026-03-23T10:05:00Z",
            status="success",
        )

    def test_decisions_default_empty(self):
        o = self._make_output()
        assert o.decisions == []

    def test_add_decision_basic(self):
        o = self._make_output()
        d = o.add_decision(
            category="schema_inference",
            reasoning="CSV header suggests string types for name columns",
            choice="string for company_name",
        )
        assert len(o.decisions) == 1
        assert d["decision_id"] == "d-001"
        assert d["category"] == "schema_inference"
        assert d["confidence"] == "high"

    def test_add_decision_with_alternatives(self):
        o = self._make_output()
        d = o.add_decision(
            category="transformation_choice",
            reasoning="Null rate is 2%, below threshold",
            choice="fill_with_default",
            alternatives=["drop_rows", "fill_with_median"],
            rejection_reasons={"drop_rows": "would lose 2% of data",
                               "fill_with_median": "not applicable to categorical"},
            confidence="medium",
        )
        assert d["alternatives_considered"] == ["drop_rows", "fill_with_median"]
        assert d["confidence"] == "medium"

    def test_multiple_decisions_sequential_ids(self):
        o = self._make_output()
        o.add_decision("c1", "r1", "ch1")
        o.add_decision("c2", "r2", "ch2")
        o.add_decision("c3", "r3", "ch3")
        assert [d["decision_id"] for d in o.decisions] == ["d-001", "d-002", "d-003"]

    def test_decisions_in_serialization(self):
        o = self._make_output()
        o.add_decision("test", "reason", "choice")
        d = o.to_dict()
        assert "decisions" in d
        assert len(d["decisions"]) == 1

    def test_decisions_roundtrip(self):
        o = self._make_output()
        o.add_decision("schema_inference", "reason", "choice")
        j = o.to_json()
        o2 = AgentOutput.from_json(j)
        assert len(o2.decisions) == 1
        assert o2.decisions[0]["category"] == "schema_inference"


# ── Orchestrator <-> sub-agent linking ───────────────────────────────


class TestTraceLink:
    def test_ingest_agent_decisions(self):
        t = AgentTracer(run_id="r", workload_name="w")
        agent_output = {
            "decisions": [
                {
                    "decision_id": "d-001",
                    "category": "schema_inference",
                    "reasoning": "All values are numeric",
                    "choice_made": "decimal(10,2)",
                    "confidence": "high",
                },
                {
                    "decision_id": "d-002",
                    "category": "pii_classification",
                    "reasoning": "Column name matches email pattern",
                    "choice_made": "PII:EMAIL",
                    "confidence": "high",
                },
            ]
        }
        t.ingest_agent_decisions(agent_output, agent_name="Metadata Agent", phase=3)
        cognitive = [e for e in t.events if e["surface"] == "cognitive"]
        assert len(cognitive) == 2
        assert cognitive[0]["event_type"] == "schema_inference"
        assert cognitive[1]["event_type"] == "pii_classification"

    def test_ingest_empty_decisions(self):
        t = AgentTracer(run_id="r", workload_name="w")
        t.ingest_agent_decisions({"decisions": []})
        assert len(t.events) == 0

    def test_ingest_no_decisions_key(self):
        t = AgentTracer(run_id="r", workload_name="w")
        t.ingest_agent_decisions({})
        assert len(t.events) == 0


# ── trace_viewer functions ───────────────────────────────────────────


@pytest.fixture
def sample_events():
    return [
        {"timestamp": "2026-03-23T10:00:00Z", "run_id": "run-001",
         "trace_id": "t1", "span_id": "s1", "parent_span_id": None,
         "surface": "contextual", "event_type": "pipeline_start",
         "agent_name": "orchestrator", "workload_name": "test_wl",
         "phase": None, "data_zone": "", "status": "",
         "duration_ms": None, "payload": {}},
        {"timestamp": "2026-03-23T10:01:00Z", "run_id": "run-001",
         "trace_id": "t1", "span_id": "s2", "parent_span_id": "s1",
         "surface": "operational", "event_type": "phase_start",
         "agent_name": "Metadata Agent", "workload_name": "test_wl",
         "phase": 3, "data_zone": "", "status": "running",
         "duration_ms": None, "payload": {}},
        {"timestamp": "2026-03-23T10:02:00Z", "run_id": "run-001",
         "trace_id": "t1", "span_id": "s3", "parent_span_id": "s2",
         "surface": "cognitive", "event_type": "schema_inference",
         "agent_name": "Metadata Agent", "workload_name": "test_wl",
         "phase": 3, "data_zone": "", "status": "",
         "duration_ms": None, "payload": {
             "reasoning": "Numeric columns detected",
             "choice_made": "decimal(10,2)",
             "confidence": "high",
             "alternatives_considered": ["float", "integer"],
         }},
        {"timestamp": "2026-03-23T10:03:00Z", "run_id": "run-001",
         "trace_id": "t1", "span_id": "s2", "parent_span_id": "s1",
         "surface": "operational", "event_type": "phase_complete",
         "agent_name": "Metadata Agent", "workload_name": "test_wl",
         "phase": 3, "data_zone": "", "status": "success",
         "duration_ms": 120000, "payload": {}},
        {"timestamp": "2026-03-23T10:04:00Z", "run_id": "run-001",
         "trace_id": "t1", "span_id": "s4", "parent_span_id": "s1",
         "surface": "operational", "event_type": "test_gate_pass",
         "agent_name": "Metadata Agent", "workload_name": "test_wl",
         "phase": 3, "data_zone": "", "status": "success",
         "duration_ms": 5000, "payload": {"passed": 43, "failed": 0}},
    ]


@pytest.fixture
def sample_jsonl(tmp_path, sample_events):
    p = tmp_path / "trace_events.jsonl"
    with open(p, "w") as f:
        for e in sample_events:
            f.write(json.dumps(e) + "\n")
    return p


class TestTraceViewerLoad:
    def test_load_from_file(self, sample_jsonl):
        events = load_events(str(sample_jsonl))
        assert len(events) == 5

    def test_load_from_directory(self, sample_jsonl):
        events = load_events(str(sample_jsonl.parent))
        assert len(events) == 5

    def test_filter_by_agent(self, sample_events):
        filtered = filter_events(sample_events, agent="Metadata")
        assert all("Metadata" in e["agent_name"] for e in filtered)
        assert len(filtered) == 4

    def test_filter_by_phase(self, sample_events):
        filtered = filter_events(sample_events, phase=3)
        assert all(e["phase"] == 3 for e in filtered)
        assert len(filtered) == 4


class TestTraceViewerSummary:
    def test_summary_prints(self, sample_events, capsys):
        show_summary(sample_events)
        output = capsys.readouterr().out
        assert "run-001" in output
        assert "test_wl" in output
        assert "5" in output  # event count

    def test_summary_empty(self, capsys):
        show_summary([])
        assert "No events" in capsys.readouterr().out


class TestTraceViewerDecisions:
    def test_decisions_prints(self, sample_events, capsys):
        show_decisions(sample_events)
        output = capsys.readouterr().out
        assert "schema_inference" in output
        assert "Numeric columns" in output

    def test_decisions_none(self, capsys):
        show_decisions([{"surface": "operational", "event_type": "test"}])
        assert "No cognitive" in capsys.readouterr().out


class TestTraceViewerTimeline:
    def test_timeline_prints(self, sample_events, capsys):
        show_timeline(sample_events)
        output = capsys.readouterr().out
        assert "pipeline_start" in output
        assert "phase_start" in output


class TestTraceViewerFailures:
    def test_no_failures(self, sample_events, capsys):
        show_failures(sample_events)
        assert "No failures" in capsys.readouterr().out

    def test_with_failures(self, capsys):
        events = [{"surface": "operational", "event_type": "phase_fail",
                    "status": "failed", "agent_name": "Quality Agent",
                    "phase": 4, "timestamp": "2026-01-01T00:00:00Z",
                    "payload": {"reason": "score below threshold"}}]
        show_failures(events)
        output = capsys.readouterr().out
        assert "score below threshold" in output


class TestTraceViewerExport:
    def test_export_markdown(self, sample_events):
        md = export_markdown(sample_events)
        assert "# Agent Log" in md
        assert "run-001" in md
        assert "Phase 3" in md
        assert "schema_inference" in md or "phase_start" in md

    def test_export_markdown_to_file(self, sample_events, tmp_path):
        out = tmp_path / "agent_log.md"
        export_markdown(sample_events, str(out))
        assert out.exists()
        content = out.read_text()
        assert "# Agent Log" in content

    def test_export_cognitive_map(self, sample_events):
        tree = export_cognitive_map(sample_events)
        assert tree["run_id"] == "run-001"
        assert tree["total_decisions"] == 1
        assert "Metadata Agent" in tree["agents"]
        assert tree["agents"]["Metadata Agent"]["count"] == 1

    def test_export_cognitive_map_to_file(self, sample_events, tmp_path):
        out = tmp_path / "map.json"
        export_cognitive_map(sample_events, str(out))
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["total_decisions"] == 1


# ── OrchestratorLogger integration ──────────────────────────────────


class TestOrchestratorLoggerTracer:
    def test_has_tracer(self, tmp_path):
        from shared.utils.orchestrator_logger import OrchestratorLogger
        out = tmp_path / "trace.jsonl"
        logger = OrchestratorLogger("test", "run-001",
                                    trace_output_path=str(out))
        assert logger.tracer is not None
        assert logger.tracer.run_id == "run-001"
        # pipeline_start contextual event emitted on init
        assert len(logger.tracer.events) == 1
        assert logger.tracer.events[0]["event_type"] == "pipeline_start"

    def test_phase_emits_trace_events(self, tmp_path):
        from shared.utils.orchestrator_logger import OrchestratorLogger
        out = tmp_path / "trace.jsonl"
        logger = OrchestratorLogger("test", "run-002",
                                    trace_output_path=str(out))
        logger.phase_start(3, "Metadata Agent")
        logger.phase_complete(3, "success", test_results={"passed": 10, "total": 10})
        # 1 pipeline_start + 1 phase_start + 1 phase_complete = 3
        assert len(logger.tracer.events) == 3
        types = [e["event_type"] for e in logger.tracer.events]
        assert "phase_start" in types
        assert "phase_complete" in types

    def test_link_sub_agent_trace(self, tmp_path):
        from shared.utils.orchestrator_logger import OrchestratorLogger
        out = tmp_path / "trace.jsonl"
        logger = OrchestratorLogger("test", "run-003",
                                    trace_output_path=str(out))
        agent_output = {
            "decisions": [{
                "category": "schema_inference",
                "reasoning": "test",
                "choice_made": "string",
                "confidence": "high",
            }]
        }
        logger.link_sub_agent_trace(agent_output, "Metadata Agent", phase=3)
        cognitive = [e for e in logger.tracer.events if e["surface"] == "cognitive"]
        assert len(cognitive) == 1

    def test_test_gate(self, tmp_path):
        from shared.utils.orchestrator_logger import OrchestratorLogger
        out = tmp_path / "trace.jsonl"
        logger = OrchestratorLogger("test", "run-004",
                                    trace_output_path=str(out))
        logger.test_gate(3, "Metadata Agent", True, {"passed": 43, "failed": 0})
        gate_events = [e for e in logger.tracer.events
                       if "test_gate" in e["event_type"]]
        assert len(gate_events) == 1
        assert gate_events[0]["status"] == "success"

    def test_pipeline_summary_emits_complete(self, tmp_path, capsys):
        from shared.utils.orchestrator_logger import OrchestratorLogger
        out = tmp_path / "trace.jsonl"
        logger = OrchestratorLogger("test", "run-005",
                                    trace_output_path=str(out))
        logger.phase_start(1, "Test Agent")
        logger.phase_complete(1, "success")
        logger.pipeline_summary()
        complete = [e for e in logger.tracer.events
                    if e["event_type"] == "pipeline_complete"]
        assert len(complete) == 1
        assert complete[0]["payload"]["status"] == "SUCCESS"

    def test_trace_output_to_file(self, tmp_path):
        from shared.utils.orchestrator_logger import OrchestratorLogger
        out = tmp_path / "trace.jsonl"
        logger = OrchestratorLogger("test", "run-006",
                                    trace_output_path=str(out))
        logger.phase_start(1, "Agent")
        logger.phase_complete(1, "success")

        assert out.exists()
        lines = out.read_text().strip().split("\n")
        assert len(lines) >= 3  # pipeline_start + phase_start + phase_complete

    def test_default_trace_path(self, tmp_path, monkeypatch):
        """Test that default trace goes to workloads/{name}/logs/."""
        from shared.utils.orchestrator_logger import OrchestratorLogger
        monkeypatch.chdir(tmp_path)
        logger = OrchestratorLogger("my_workload", "run-007")
        assert "workloads/my_workload/logs/" in logger.trace_output_path
        assert "my_workload.jsonl" in logger.trace_output_path
        assert Path(logger.trace_output_path).parent.exists()
