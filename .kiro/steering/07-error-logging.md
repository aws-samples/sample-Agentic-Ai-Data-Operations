# Error Handling & Agent Logging Protocol

## Error Categories

| Category | Examples | Action |
|---|---|---|
| **Retryable** | Network timeout, API throttling, transient S3 errors | Retry with exponential backoff (max 3 attempts) |
| **Fixable** | Schema mismatch, missing config, quality below threshold | Ask the human for correction |
| **Fatal** | Invalid credentials, source permanently offline, data corruption | Halt pipeline, alert human immediately |

Never silently swallow errors. Log full context (agent, operation, input summary, error type) and escalate appropriately.

## Agent Logging Protocol

Every pipeline run produces a structured trace across three layers, linked by `run_id`:

| Layer | What | Source |
|-------|------|--------|
| **1. Orchestrator** | Phase transitions, test gates, retries | `OrchestratorLogger` + `AgentTracer` |
| **2. Generated Scripts** | Row counts, transforms, quality scores | `StructuredLogger` in ETL scripts |
| **3. LLM Self-Reporting** | Reasoning, alternatives, confidence | `AgentOutput.decisions` array |

## Rules

- Every pipeline run MUST produce a `trace_events.jsonl` (via `AgentTracer`)
- Every sub-agent MUST include a `decisions` array in its `AgentOutput`
- Every ETL script MUST use `StructuredLogger` for structured log output
- All trace events use three surfaces: **operational** (what), **cognitive** (why), **contextual** (where)
- CloudTrail enabled for all Lake Formation operations — audit trail for data access and PII tag changes

## Key Files

```
shared/logging/agent_tracer.py
shared/logging/trace_viewer.py
shared/utils/orchestrator_logger.py
shared/utils/structured_logger.py
```
