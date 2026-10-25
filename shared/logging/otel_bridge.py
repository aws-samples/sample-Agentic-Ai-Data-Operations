"""Optional native OpenTelemetry bridge for ADOP tracing.

ADOP's JSONL trace remains the durable audit surface.  When the ``otel`` extra
is installed and ``ADOP_OTEL_ENABLED=true``, this module also creates native
OpenTelemetry spans and exports them over OTLP/HTTP.

The bridge imports OpenTelemetry lazily so Glue jobs and local development do
not require telemetry dependencies just to produce the mandatory JSONL trace.
"""

from __future__ import annotations

import json
import os
import warnings
import atexit
from typing import Any, Dict, Optional


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _attribute_value(value: Any) -> Any:
    """Convert nested payload values to OpenTelemetry attribute-safe values."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple)) and all(
        isinstance(item, (str, bool, int, float)) for item in value
    ):
        return list(value)
    return json.dumps(value, default=str, sort_keys=True)


class OpenTelemetryBridge:
    """Create native OTel spans without making OTel a hard dependency."""

    def __init__(
        self,
        *,
        run_id: str,
        workload_name: str,
        enabled: Optional[bool] = None,
        endpoint: Optional[str] = None,
    ):
        self.requested = (
            _truthy(os.environ.get("ADOP_OTEL_ENABLED", "false"))
            if enabled is None
            else enabled
        )
        self.available = False
        self.error: Optional[str] = None
        self.trace_id: Optional[str] = None
        self.root_span_id: Optional[str] = None
        self._provider = None
        self._tracer = None
        self._root_span = None
        self._span_stack: list[Any] = []

        if not self.requested:
            return

        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as exc:
            self.error = (
                "OpenTelemetry is enabled but not installed; install "
                "agentic-data-onboarding[otel]"
            )
            warnings.warn(self.error, RuntimeWarning, stacklevel=2)
            return

        try:
            exporter_endpoint = endpoint or os.environ.get("ADOP_OTEL_ENDPOINT")
            exporter = (
                OTLPSpanExporter(endpoint=exporter_endpoint)
                if exporter_endpoint
                else OTLPSpanExporter()
            )
            resource = Resource.create(
                {
                    "service.name": os.environ.get(
                        "OTEL_SERVICE_NAME", "adop-data-onboarding"
                    ),
                    "service.namespace": "adop",
                    "service.version": os.environ.get(
                        "ADOP_VERSION", "development"
                    ),
                    "adop.run_id": run_id,
                    "adop.workload": workload_name,
                }
            )
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            tracer = provider.get_tracer("adop", "1.0.0")
            root_span = tracer.start_span(
                "adop.run",
                attributes={
                    "adop.run_id": run_id,
                    "adop.workload": workload_name,
                },
            )
            context = root_span.get_span_context()
            self._provider = provider
            self._tracer = tracer
            self._root_span = root_span
            self.trace_id = f"{context.trace_id:032x}"
            self.root_span_id = f"{context.span_id:016x}"
            self.available = True
            atexit.register(self.close)
        except Exception as exc:  # exporter configuration must not lose JSONL
            self.error = f"OpenTelemetry exporter unavailable: {exc}"
            warnings.warn(self.error, RuntimeWarning, stacklevel=2)

    @property
    def current_span_id(self) -> Optional[str]:
        if self._span_stack:
            context = self._span_stack[-1].get_span_context()
            return f"{context.span_id:016x}"
        return self.root_span_id

    def start_span(self, name: str, attributes: Dict[str, Any]):
        if not self.available:
            return None
        from opentelemetry import trace

        parent = self._span_stack[-1] if self._span_stack else self._root_span
        parent_context = trace.set_span_in_context(parent)
        span = self._tracer.start_span(
            name,
            context=parent_context,
            attributes={
                key: _attribute_value(value)
                for key, value in attributes.items()
                if value is not None
            },
        )
        self._span_stack.append(span)
        return span

    def end_span(self, span, *, error: Optional[BaseException] = None):
        if not self.available or span is None:
            return
        from opentelemetry.trace import Status, StatusCode

        if self._span_stack and self._span_stack[-1] is span:
            self._span_stack.pop()
        elif span in self._span_stack:
            self._span_stack.remove(span)

        if error is not None:
            span.record_exception(error)
            span.set_status(Status(StatusCode.ERROR, str(error)))
        span.end()

    def event(
        self,
        event_type: str,
        *,
        attributes: Dict[str, Any],
        error: Optional[BaseException] = None,
    ):
        if not self.available:
            return
        from opentelemetry.trace import Status, StatusCode

        span = self._span_stack[-1] if self._span_stack else self._root_span
        span.add_event(
            event_type,
            attributes={
                key: _attribute_value(value)
                for key, value in attributes.items()
                if value is not None
            },
        )
        if error is not None:
            span.record_exception(error)
        if error is not None or attributes.get("adop.status") in {"failed", "error"}:
            span.set_status(
                Status(
                    StatusCode.ERROR,
                    str(error or attributes.get("adop.status")),
                )
            )

    def close(self):
        if not self.available:
            return
        while self._span_stack:
            self.end_span(self._span_stack[-1])
        if self._root_span is not None:
            self._root_span.end()
        if self._provider is not None:
            self._provider.shutdown()
        self.available = False
