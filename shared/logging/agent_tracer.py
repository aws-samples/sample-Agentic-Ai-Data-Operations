"""
Three-surface event tracer for the Agentic Data Onboarding platform.

Captures operational, cognitive, and contextual events across three layers:
  Layer 1 — Orchestrator (phase transitions, test gates, retries)
  Layer 2 — Generated Scripts (row counts, transforms, quality scores)
  Layer 3 — LLM Self-Reporting (decisions array from AgentOutput)
  Layer 4 — Conversation Flow (questions, user answers, discoveries, tool calls)

All events share a run_id and use parent_span_id to form a trace tree.
Events carry a monotonic sequence_number for total ordering.
Question/answer pairs share a thread_id for linkage.

Output: one JSON object per line (JSONL), compatible with jq, CloudWatch, Splunk.

Usage:
    from shared.logging.agent_tracer import AgentTracer, TraceContext

    tracer = AgentTracer(run_id="run-abc123", workload_name="financial_portfolios")

    with tracer.span("phase_4_metadata", agent_name="Metadata Agent", phase=4) as ctx:
        tracer.operational_event("phase_start", agent_name="Metadata Agent", phase=4)
        # ... do work ...
        tracer.cognitive_event("schema_inference", agent_name="Metadata Agent",
                               phase=4, payload={"reasoning": "..."})
        tracer.operational_event("phase_complete", agent_name="Metadata Agent",
                                 phase=4, status="success")

    # Conversation flow capture:
    thread_id = AgentTracer.new_thread_id()
    tracer.question_asked("What is the PK?", options=["claim_id", "auto"],
                          agent_name="Discovery", phase=1, thread_id=thread_id)
    tracer.user_responded("claim_id", selected_options=["claim_id"],
                          agent_name="Discovery", phase=1, thread_id=thread_id)
"""

import json
import os
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


VALID_SURFACES = {"operational", "cognitive", "contextual"}

CONVERSATION_EVENT_TYPES = {
    "question_asked",
    "user_responded",
    "discovery_presented",
    "tool_called",
    "decision_made",
}


class TraceContext:
    """Represents a span in the trace tree."""

    def __init__(self, span_id: str, parent_span_id: Optional[str], name: str,
                 start_time: datetime):
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.name = name
        self.start_time = start_time
        self.end_time: Optional[datetime] = None

    @property
    def duration_ms(self) -> Optional[float]:
        if self.end_time is None:
            return None
        delta = self.end_time - self.start_time
        return delta.total_seconds() * 1000

    def close(self):
        self.end_time = datetime.now(timezone.utc)


class AgentTracer:
    """Emits structured trace events to JSONL output.

    ~15 fields per event (OTel-compatible, slimmed from full spec):
        timestamp, run_id, trace_id, span_id, parent_span_id,
        surface, event_type, agent_name, workload_name, phase,
        data_zone, status, duration_ms, payload
    """

    def __init__(self, run_id: str, workload_name: str, *,
                 trace_id: Optional[str] = None,
                 output_path: Optional[str] = None,
                 write_to_stdout: bool = False):
        self.run_id = run_id
        self.workload_name = workload_name
        self.trace_id = trace_id or str(uuid.uuid4())[:12]
        self.write_to_stdout = write_to_stdout

        # Output destination
        if output_path:
            self._output_path = Path(output_path)
        else:
            self._output_path = None

        # Active span stack
        self._span_stack: List[TraceContext] = []
        self._events: List[Dict[str, Any]] = []

        # Monotonic counter for total event ordering
        self._sequence_counter: int = 0

    @property
    def current_span_id(self) -> Optional[str]:
        return self._span_stack[-1].span_id if self._span_stack else None

    @property
    def events(self) -> List[Dict[str, Any]]:
        return list(self._events)

    def _emit(self, surface: str, event_type: str, *,
              agent_name: str = "", phase: Optional[int] = None,
              data_zone: str = "", status: str = "",
              duration_ms: Optional[float] = None,
              span_id: Optional[str] = None,
              parent_span_id: Optional[str] = None,
              thread_id: Optional[str] = None,
              payload: Optional[Dict[str, Any]] = None):
        """Core emit method — builds and writes one trace event."""
        self._sequence_counter += 1
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "span_id": span_id or self.current_span_id or str(uuid.uuid4())[:8],
            "parent_span_id": parent_span_id or (
                self._span_stack[-2].span_id if len(self._span_stack) > 1
                else None
            ),
            "sequence_number": self._sequence_counter,
            "thread_id": thread_id,
            "surface": surface,
            "event_type": event_type,
            "agent_name": agent_name,
            "workload_name": self.workload_name,
            "phase": phase,
            "data_zone": data_zone,
            "status": status,
            "duration_ms": duration_ms,
            "payload": payload or {},
        }

        self._events.append(event)
        line = json.dumps(event, default=str)

        if self.write_to_stdout:
            print(line, file=sys.stdout)

        if self._output_path:
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._output_path, "a") as f:
                f.write(line + "\n")

    def operational_event(self, event_type: str, *, agent_name: str = "",
                          phase: Optional[int] = None, data_zone: str = "",
                          status: str = "", duration_ms: Optional[float] = None,
                          payload: Optional[Dict[str, Any]] = None):
        """Layer 1 & 2: what happened (phase transitions, row counts, test gates)."""
        self._emit("operational", event_type, agent_name=agent_name, phase=phase,
                    data_zone=data_zone, status=status, duration_ms=duration_ms,
                    payload=payload)

    def cognitive_event(self, event_type: str, *, agent_name: str = "",
                        phase: Optional[int] = None,
                        payload: Optional[Dict[str, Any]] = None):
        """Layer 3: why it happened (LLM self-reported decisions)."""
        self._emit("cognitive", event_type, agent_name=agent_name, phase=phase,
                    payload=payload)

    def contextual_event(self, event_type: str, *, agent_name: str = "",
                         phase: Optional[int] = None, data_zone: str = "",
                         payload: Optional[Dict[str, Any]] = None):
        """Metadata about the environment/context surrounding an event."""
        self._emit("contextual", event_type, agent_name=agent_name, phase=phase,
                    data_zone=data_zone, payload=payload)

    @contextmanager
    def span(self, name: str, *, agent_name: str = "",
             phase: Optional[int] = None, data_zone: str = ""):
        """Context manager for span lifecycle."""
        span_id = str(uuid.uuid4())[:8]
        parent_id = self.current_span_id
        ctx = TraceContext(
            span_id=span_id,
            parent_span_id=parent_id,
            name=name,
            start_time=datetime.now(timezone.utc),
        )
        self._span_stack.append(ctx)

        self._emit("operational", f"{name}_start", agent_name=agent_name,
                    phase=phase, data_zone=data_zone, status="running",
                    span_id=span_id, parent_span_id=parent_id)
        try:
            yield ctx
        finally:
            ctx.close()
            self._span_stack.pop()
            self._emit("operational", f"{name}_end", agent_name=agent_name,
                        phase=phase, data_zone=data_zone, status="complete",
                        duration_ms=ctx.duration_ms,
                        span_id=span_id, parent_span_id=parent_id)

    def ingest_agent_decisions(self, agent_output_dict: Dict[str, Any],
                               agent_name: str = "",
                               phase: Optional[int] = None):
        """Import decisions from an AgentOutput.decisions array (Layer 3 link)."""
        decisions = agent_output_dict.get("decisions", [])
        for decision in decisions:
            self.cognitive_event(
                decision.get("category", "decision_made"),
                agent_name=agent_name,
                phase=phase,
                payload=decision,
            )

    def flush_to_file(self, path: str):
        """Write all buffered events to a JSONL file."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            for event in self._events:
                f.write(json.dumps(event, default=str) + "\n")

    def format_exchange(
        self,
        query: str,
        summary: str,
        status: str = "OK",
        tokens: str = "",
        latency: str = "",
        agent_name: str = "",
    ) -> str:
        """Render a query/response exchange as ASCII art for trace logs."""
        from shared.utils.ascii_display import exchange_block
        return exchange_block(
            question=query,
            summary=summary,
            status=status,
            source=agent_name or "agent",
            user=self.workload_name,
            ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            tokens=tokens,
            latency=latency,
        )

    def log_exchange(
        self,
        query: str,
        summary: str,
        status: str = "OK",
        agent_name: str = "",
        phase: Optional[int] = None,
        tokens: str = "",
        latency: str = "",
    ):
        """Log a query/response exchange as both ASCII display and trace event."""
        ascii_art = self.format_exchange(
            query=query, summary=summary, status=status,
            tokens=tokens, latency=latency, agent_name=agent_name,
        )
        if self.write_to_stdout:
            print(ascii_art, file=sys.stdout)

        self.operational_event(
            "exchange",
            agent_name=agent_name,
            phase=phase,
            status=status,
            payload={
                "query": query,
                "summary": summary,
                "ascii_display": ascii_art,
                "tokens": tokens,
                "latency": latency,
            },
        )

    # ── Conversation Flow Capture ──────────────────────────────────────

    @staticmethod
    def new_thread_id() -> str:
        """Generate a short thread ID for linking question→answer pairs."""
        return f"thr-{uuid.uuid4().hex[:8]}"

    def conversation_event(
        self,
        event_type: str,
        *,
        agent_name: str = "",
        phase: Optional[int] = None,
        thread_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ):
        """Emit a conversation-flow event on the contextual surface."""
        self._emit(
            "contextual", event_type,
            agent_name=agent_name, phase=phase,
            thread_id=thread_id,
            payload=payload,
        )

    def question_asked(
        self,
        question_text: str,
        *,
        options: Optional[List[str]] = None,
        agent_name: str = "",
        phase: Optional[int] = None,
        thread_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Agent presents a question to the user."""
        payload = {
            "question_text": question_text,
            "options": options or [],
            "context": context or {},
        }
        self.conversation_event(
            "question_asked", agent_name=agent_name,
            phase=phase, thread_id=thread_id, payload=payload,
        )

    def user_responded(
        self,
        answer_text: str,
        *,
        selected_options: Optional[List[str]] = None,
        agent_name: str = "",
        phase: Optional[int] = None,
        thread_id: Optional[str] = None,
    ):
        """User provides an answer to a question."""
        payload = {
            "answer_text": answer_text,
            "selected_options": selected_options or [],
        }
        self.conversation_event(
            "user_responded", agent_name=agent_name,
            phase=phase, thread_id=thread_id, payload=payload,
        )

    def discovery_presented(
        self,
        title: str,
        findings: List[str],
        *,
        agent_name: str = "",
        phase: Optional[int] = None,
        data_source: str = "",
    ):
        """Agent presents auto-discovered findings to the user."""
        payload = {
            "title": title,
            "findings": findings,
            "data_source": data_source,
        }
        self.conversation_event(
            "discovery_presented", agent_name=agent_name,
            phase=phase, payload=payload,
        )

    def tool_called(
        self,
        tool_name: str,
        params: Dict[str, Any],
        *,
        result_summary: str = "",
        agent_name: str = "",
        phase: Optional[int] = None,
        duration_ms: Optional[float] = None,
    ):
        """Agent invokes a tool or MCP server."""
        payload = {
            "tool_name": tool_name,
            "params": params,
            "result_summary": result_summary,
        }
        self._emit(
            "contextual", "tool_called",
            agent_name=agent_name, phase=phase,
            duration_ms=duration_ms,
            payload=payload,
        )

    def decision_made(
        self,
        decision_text: str,
        *,
        triggered_by_thread: Optional[str] = None,
        reasoning: str = "",
        agent_name: str = "",
        phase: Optional[int] = None,
    ):
        """Agent makes a decision influenced by user input."""
        payload = {
            "decision_text": decision_text,
            "triggered_by_thread": triggered_by_thread,
            "reasoning": reasoning,
        }
        self.conversation_event(
            "decision_made", agent_name=agent_name,
            phase=phase, payload=payload,
        )
