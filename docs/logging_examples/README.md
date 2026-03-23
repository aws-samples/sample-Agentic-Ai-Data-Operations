# Deep Agent Logging — Example Output

Sample trace data from a `financial_portfolios` pipeline run demonstrating the three-layer observability model.

## Three-Layer Model

```
Layer 1: Orchestrator (OrchestratorLogger + AgentTracer)
    Captures: phase transitions, test gates, retries, pipeline summary
    Source:   run_pipeline.py / main conversation

Layer 2: Generated Scripts (StructuredLogger)
    Captures: row counts, transformations applied, quality scores
    Source:   workloads/*/scripts/ (Glue ETL, quality checks)

Layer 3: LLM Self-Reporting (AgentOutput.decisions)
    Captures: reasoning, alternatives considered, confidence levels
    Source:   Sub-agent structured output via SKILLS.md prompts
```

All three layers link via `run_id` and `parent_span_id`.

## Files

| File | Description |
|------|-------------|
| `trace_events.jsonl` | Raw trace events (~30 events from a full pipeline run) |
| `agent_log.md` | Human-readable narrative generated via `trace_viewer --export-md` |
| `cognitive_map.json` | Decision tree generated via `trace_viewer --export-map` |

## Viewing

```bash
# Summary
python3 -m shared.logging.trace_viewer docs/logging_examples/trace_events.jsonl --summary

# Agent decisions only
python3 -m shared.logging.trace_viewer docs/logging_examples/trace_events.jsonl --decisions

# Filter to specific agent
python3 -m shared.logging.trace_viewer docs/logging_examples/trace_events.jsonl --agent "Metadata Agent" --timeline

# Export markdown narrative
python3 -m shared.logging.trace_viewer docs/logging_examples/trace_events.jsonl --export-md agent_log.md

# Export decision tree
python3 -m shared.logging.trace_viewer docs/logging_examples/trace_events.jsonl --export-map cognitive_map.json

# Validate JSONL with jq
jq '.' docs/logging_examples/trace_events.jsonl
```

## Three Surfaces

Each trace event belongs to one surface:

- **Operational** — what happened (phase_start, rows_processed, test_gate_pass)
- **Cognitive** — why it happened (schema_inference, transformation_choice, threshold_selection)
- **Contextual** — what surrounded it (pipeline_start, pipeline_complete, environment config)
