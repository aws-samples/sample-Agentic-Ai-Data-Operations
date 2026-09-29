# 08 — DEEP AGENT LOGGING: Three-Layer Observability
> Full-stack tracing across orchestrator, generated scripts, and LLM agent reasoning.

## Purpose

Build a deep logging system that captures what happened (operational), why it happened (cognitive), and what surrounded it (contextual) across the three layers that are actually instrumentable in this platform:

1. **Layer 1 — Orchestrator** (`OrchestratorLogger` + `run_pipeline.py`): Phase transitions, sub-agent spawning, test gates, retries
2. **Layer 2 — Generated Scripts** (Glue ETL, quality checks, DAGs): Row counts, transformations applied, quality scores, errors
3. **Layer 3 — LLM Self-Reporting** (SKILLS.md spawn prompts): Structured decision traces returned as part of `AgentOutput`

All three layers are linked by a shared `run_id`, producing a unified trace per pipeline execution.

## When to Use

- After you have at least one working workload (e.g., `workloads/financial_portfolios/`)
- When you want to understand WHY an agent made a decision, not just WHAT it produced
- Before scaling to more workloads — get observability in place first

## Prompt Template

```
Implement the Deep Agent Logging system for the Agentic Data Onboarding platform.

This system adds three-layer observability: orchestrator tracing, script-level structured logging, and LLM agent self-reporting. All layers link via run_id.

Read these files first to understand what exists:
- shared/utils/orchestrator_logger.py (Layer 1 — exists, needs enhancement)
- shared/utils/structured_logger.py (Layer 2 — exists, unused in scripts)
- shared/templates/agent_output_schema.py (Layer 3 — exists, needs decisions array)
- SKILLS.md (agent spawn prompts — need decision reporting requirement)
- CLAUDE.md (project config — needs logging protocol section)

=== EXECUTION MODEL (READ THIS FIRST) ===

This platform uses Claude Code LLM sub-agents, NOT Python agent classes.
You CANNOT instrument LLM reasoning with decorators or function hooks.

The three instrumentable layers are:

Layer 1 — Orchestrator (Python code we control):
  - run_pipeline.py / main conversation orchestration logic
  - shared/utils/orchestrator_logger.py (OrchestratorLogger class)
  - This is where sub-agents are spawned, test gates checked, phases transition
  - FULLY instrumentable — add three-surface events here

Layer 2 — Generated Scripts (Python code running on Glue/Airflow):
  - workloads/*/scripts/ (ETL scripts, quality checks)
  - shared/utils/structured_logger.py (StructuredLogger class — exists but currently unused)
  - FULLY instrumentable — wire StructuredLogger into every script

Layer 3 — LLM Agent Self-Reporting (prompt engineering):
  - Sub-agents are LLM prompts in SKILLS.md, spawned via Claude Code Agent tool
  - Cannot observe reasoning externally — must REQUIRE structured output
  - Add a `decisions` array to AgentOutput so agents report their own cognitive trace
  - Each decision: reasoning, choice_made, alternatives_considered, rejection_reasons, confidence

=== THREE-SURFACE EVENT MODEL ===

Every trace event belongs to one of three surfaces (inspired by AgentTrace):

1. OPERATIONAL — what happened
   - phase_start, phase_complete, phase_retry, phase_escalate
   - script_start, script_complete, rows_processed, rows_quarantined
   - test_gate_pass, test_gate_fail, artifact_created
   - dag_task_start, dag_task_complete, quality_check_result

2. COGNITIVE — why it happened (LLM self-report)
   - decision_made (reasoning, alternatives, confidence)
   - schema_inference (why these types were chosen)
   - rule_selection (why this quality rule, not that one)
   - transformation_choice (why this cleaning approach)

3. CONTEXTUAL — what surrounded it
   - workload_name, run_id, phase, agent_name
   - input_hash, output_hash (determinism verification)
   - data_zone (bronze/silver/gold), row_count, column_count
   - parent_span_id (links sub-agent traces to orchestrator)

=== DELIVERABLES ===

Build these files in order:

1. shared/logging/agent_tracer.py
   - AgentTracer class with ~15 OTel-compatible fields (not 30+)
   - Required fields per event:
     timestamp, run_id, trace_id, span_id, parent_span_id,
     surface (operational|cognitive|contextual),
     event_type, agent_name, workload_name, phase,
     data_zone, status, duration_ms, payload (dict for extras)
   - Methods: operational_event(), cognitive_event(), contextual_event()
   - Output: append to workloads/{workload_name}/logs/trace_events.jsonl (one JSON object per line)
   - Per-run logs: workloads/{workload_name}/logs/run_YYYYMMDD_HHMMSS/trace.jsonl
   - Support writing to: local file, stdout, or S3 path
   - Include TraceContext manager for span lifecycle

2. shared/logging/trace_viewer.py
   - CLI tool for reading trace_events.jsonl from workloads/{workload_name}/logs/
   - Commands:
     --summary: high-level run overview (phases, durations, pass/fail)
     --decisions: show only cognitive surface events (agent reasoning)
     --timeline: chronological event list with durations
     --agent <name>: filter to specific agent
     --phase <n>: filter to specific phase
     --failures: show only errors, retries, escalations
     --export-md: generate agent_log.md (human-readable run narrative)
     --export-map: generate cognitive_map.json (decision tree)
   - Input: path to trace_events.jsonl or directory containing one (e.g., workloads/financial_portfolios/logs/)
   - Colorized terminal output (optional, degrade gracefully)

3. Enhance shared/utils/orchestrator_logger.py
   - Import and use AgentTracer alongside existing console output
   - Emit operational events for: phase_start, phase_complete, phase_retry, phase_escalate
   - Emit contextual events for: pipeline_start (with full config), pipeline_complete
   - Add span tracking: each phase gets a span_id, sub-agent calls get child spans
   - Add method: link_sub_agent_trace(sub_agent_output) to correlate Layer 1 <-> Layer 3
   - Preserve ALL existing console output (do not break current behavior)

4. Wire shared/utils/structured_logger.py into ETL scripts
   - For each script in workloads/*/scripts/:
     - Import StructuredLogger at top
     - Initialize with agent name, workload, run_id (from args or env var)
     - Log at script start (input paths, config loaded)
     - Log after each transformation step (rows_in, rows_out, rows_quarantined)
     - Log at script end (total duration, output path, checksum)
   - Add run_id acceptance: scripts should accept --run-id arg or RUN_ID env var
   - Do NOT change script logic — only add logging calls

5. Extend shared/templates/agent_output_schema.py
   - Add decisions field to AgentOutput dataclass:
     decisions: List[Dict[str, Any]] = field(default_factory=list)
   - Each decision dict has this shape:
     {
       "decision_id": "d-001",
       "category": "schema_inference|rule_selection|transformation_choice|format_selection|partition_strategy",
       "reasoning": "Free text explaining the thought process",
       "choice_made": "What was actually chosen",
       "alternatives_considered": ["alt1", "alt2"],
       "rejection_reasons": {"alt1": "reason", "alt2": "reason"},
       "confidence": "high|medium|low",
       "context": {"relevant_key": "relevant_value"}
     }
   - Add helper method: add_decision(category, reasoning, choice, alternatives=None, confidence="high")
   - Preserve ALL existing fields and methods

6. Update SKILLS.md sub-agent spawn prompts
   - Add this requirement to the Sub-Agent Output Format section:
     "You MUST include a `decisions` array documenting every significant choice you made.
      For each decision, explain your reasoning, what alternatives you considered,
      and why you rejected them. This is critical for audit trails and debugging."
   - Add example decisions for each agent type:
     - Metadata Agent: schema inference, PII classification, column role assignment
     - Transformation Agent: cleaning approach, null handling strategy, type casting
     - Quality Agent: threshold selection, rule priority, anomaly detection config
     - DAG Agent: task grouping, retry strategy, dependency ordering

7. Update CLAUDE.md
   - Add "Agent Logging Protocol" section after "Error Handling Philosophy"
   - Brief description of three-layer model
   - Rule: "Every pipeline run MUST produce a trace_events.jsonl"
   - Rule: "Every sub-agent MUST include decisions array in AgentOutput"
   - Rule: "Every ETL script MUST use StructuredLogger"
   - Reference shared/logging/ as the logging home

8. tests/unit/test_agent_tracer.py
   - Test AgentTracer initialization and field defaults
   - Test all three event methods (operational, cognitive, contextual)
   - Test JSONL output format (valid JSON per line)
   - Test TraceContext span lifecycle (start/end, duration calculation)
   - Test trace_viewer CLI (--summary, --decisions, --failures)
   - Test AgentOutput.add_decision() helper
   - Test linking orchestrator spans to sub-agent traces
   - Use tmp_path fixture for file output tests

9. docs/logging_examples/
   - trace_events.jsonl — sample trace from a realistic pipeline run (~30 events)
   - agent_log.md — generated from trace_events.jsonl via trace_viewer --export-md
   - cognitive_map.json — decision tree from trace_viewer --export-map
   - README.md — explains the three-layer model with a diagram

=== LINKING THE THREE LAYERS ===

The key insight: all three layers share run_id and use parent_span_id to form a tree.

Trace hierarchy for a typical run:
  run_id: "run-abc123"
  │
  ├── span: pipeline_start (Layer 1 - orchestrator)
  │   ├── span: phase_1_discovery (Layer 1)
  │   ├── span: phase_2_dedup (Layer 1)
  │   ├── span: phase_3_profiling (Layer 1)
  │   │   └── span: profiling_script (Layer 2 - Glue script)
  │   ├── span: phase_4_metadata (Layer 1)
  │   │   ├── cognitive: schema_inference (Layer 3 - from AgentOutput.decisions)
  │   │   ├── cognitive: pii_classification (Layer 3)
  │   │   └── span: test_gate (Layer 1)
  │   ├── span: phase_4_transformation (Layer 1)
  │   │   ├── span: bronze_to_silver_script (Layer 2 - Glue ETL)
  │   │   ├── cognitive: cleaning_approach (Layer 3)
  │   │   └── span: test_gate (Layer 1)
  │   ├── span: phase_4_quality (Layer 1)
  │   │   ├── span: quality_check_script (Layer 2)
  │   │   ├── cognitive: threshold_selection (Layer 3)
  │   │   └── span: test_gate (Layer 1)
  │   └── span: phase_4_dag (Layer 1)
  │       ├── cognitive: task_grouping (Layer 3)
  │       └── span: test_gate (Layer 1)
  └── span: pipeline_complete (Layer 1)

=== CONSTRAINTS ===

- Do NOT create an AgentTracer decorator or try to wrap LLM calls — LLM agents are prompts, not functions
- Do NOT add token counting fields (gen_ai_input_tokens etc.) — not available from Claude Code sub-agents
- Do NOT break existing OrchestratorLogger console output — enhance, don't replace
- Do NOT change ETL script logic when wiring in StructuredLogger — logging only
- Keep AgentTracer to ~15 fields max — resist the urge to add 30+ OTel fields
- trace_events.jsonl must be valid JSONL (one JSON object per line, parseable by jq)
- All timestamps in ISO 8601 UTC
- All new code must have tests (target: 80% coverage)

=== VERIFICATION ===

After implementation, run these checks:

1. python3 -m pytest tests/unit/test_agent_tracer.py -v  (all tests pass)
2. python3 -m shared.logging.trace_viewer --help  (CLI works, shows all options)
3. python3 -m shared.logging.trace_viewer docs/logging_examples/trace_events.jsonl --summary  (renders summary)
4. python3 -m shared.logging.trace_viewer docs/logging_examples/trace_events.jsonl --decisions  (shows cognitive events)
5. python3 -m shared.logging.trace_viewer docs/logging_examples/trace_events.jsonl --export-md  (generates markdown)
6. jq '.' docs/logging_examples/trace_events.jsonl  (valid JSONL)
7. Check SKILLS.md contains "decisions" requirement in Sub-Agent Output Format
8. Check CLAUDE.md contains "Agent Logging Protocol" section
9. Check shared/templates/agent_output_schema.py has decisions field + add_decision method
10. Check docs/logging_examples/ has all 4 files (trace_events.jsonl, agent_log.md, cognitive_map.json, README.md)
11. Check each workload has logs/ folder with README.md and .gitignore
12. Test: python3 -m shared.logging.trace_viewer workloads/financial_portfolios/logs/ --summary
```

## Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| (none) | This prompt is self-contained | Paste as-is |

## Expected Output

| File | Purpose |
|------|---------|
| `shared/logging/__init__.py` | Package init |
| `shared/logging/agent_tracer.py` | Core tracer (~15 OTel-compatible fields, three surfaces) |
| `shared/logging/trace_viewer.py` | CLI viewer (summary, decisions, timeline, export) |
| `shared/utils/orchestrator_logger.py` | Enhanced with AgentTracer integration |
| `shared/utils/structured_logger.py` | Unchanged (already exists, scripts wire into it) |
| `shared/templates/agent_output_schema.py` | Extended with `decisions` array + `add_decision()` |
| `SKILLS.md` | Updated spawn prompts with decision reporting requirement |
| `CLAUDE.md` | New "Agent Logging Protocol" section |
| `tests/unit/test_agent_tracer.py` | Unit tests for tracer, viewer, and AgentOutput extension |
| `docs/logging_examples/trace_events.jsonl` | Sample trace (~30 events) |
| `docs/logging_examples/agent_log.md` | Human-readable run narrative |
| `docs/logging_examples/cognitive_map.json` | Decision tree |
| `docs/logging_examples/README.md` | Three-layer model explanation |

## Key Design Decisions

### Why not instrument LLM agents directly?
Sub-agents are Claude Code prompts (SKILLS.md), not Python classes. You can't attach decorators, middleware, or tracing hooks to an LLM conversation. Instead, we require structured self-reporting via the `decisions` array in `AgentOutput`.

### Why ~15 fields instead of 30+?
AgentTrace's full OTel schema includes fields like `gen_ai_input_tokens`, `gen_ai_output_tokens`, `gen_ai_model` that aren't available from Claude Code sub-agents. We keep only fields we can actually populate.

### Why three surfaces?
Separating operational/cognitive/contextual lets you filter traces by concern:
- **Debugging a failed pipeline?** Filter to operational surface.
- **Understanding why an agent chose star schema over flat?** Filter to cognitive surface.
- **Correlating across workloads?** Filter to contextual surface.

## Relationship to Other Prompts

| Prompt | Relationship |
|--------|-------------|
| 03-ONBOARD | Logging captures the full onboarding trace end-to-end |
| 06-GOVERN | Lineage + logging together give complete audit trail |
| 07-FIX | Debug traces help diagnose Glue/Iceberg failures |
