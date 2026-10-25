# ADOP OpenTelemetry

ADOP always writes its append-only `trace_events.jsonl` audit trace. Native
OpenTelemetry export is optional and adds OTLP spans without replacing that
local audit record.

Install the telemetry extra:

```bash
pip install -e '.[otel]'
```

Enable OTLP/HTTP export:

```bash
export ADOP_OTEL_ENABLED=true
export ADOP_OTEL_ENDPOINT=http://adot-collector.internal:4318/v1/traces
export OTEL_SERVICE_NAME=adop-data-onboarding
```

The repository includes an AWS ADOT Collector configuration at
`config/observability/adot-collector.yaml`. Deploy it as a private ECS,
EKS, or EC2 collector service and route its OTLP/HTTP listener to ADOP.
The collector receives OTLP and exports to AWS X-Ray; the collector's task
role, not the pipeline code, owns the X-Ray permissions.

The example runtime environment is in
`config/observability/adop-otel.env.example`. Do not commit collector
credentials or public endpoints to workload configuration.

The exporter can also use standard OpenTelemetry environment variables
supported by the OTLP HTTP exporter. ADOP adds these resource attributes:

- `adop.run_id`
- `adop.workload`
- `service.name`
- `service.namespace`
- `service.version`

ADOP trace IDs are 32 hexadecimal characters and span IDs are 16 hexadecimal
characters. Each JSONL event is also emitted as an OpenTelemetry span event,
while `AgentTracer.span(...)` creates a native child span.

If the extra is not installed, or exporter setup fails, ADOP keeps writing the
mandatory JSONL trace and emits a runtime warning. It does not silently claim
that OTLP export succeeded.
