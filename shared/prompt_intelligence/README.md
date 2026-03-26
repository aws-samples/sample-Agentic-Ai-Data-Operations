# Prompt Intelligence: Self-Healing Prompt Architecture

Analyzes trace logs to extract failure patterns and best practices across workloads, generating actionable recommendations for prompt improvements.

## What It Does

The Prompt Intelligence system learns from mistakes by:
1. **Extracting failure patterns** from `trace_events.jsonl` files
2. **Correlating low-confidence decisions** to test gate failures
3. **Aggregating patterns across workloads** to find common mistakes
4. **Generating actionable recommendations** mapped to specific prompt sections
5. **Identifying best practices** from high-confidence successful decisions

## When Does It Run?

**On-demand, not automatic.** Run after workloads complete and have trace logs.

**Typical schedule:**
- **Weekly** (proactive learning): Every Monday morning
- **After failures** (reactive): After test gate failures or deployment issues
- **Before deployments** (preventive): Before pushing multiple workloads to production
- **After milestones** (batch): After every 5-10 new workloads onboarded

See [WHEN_TO_RUN.md](WHEN_TO_RUN.md) for detailed triggers, CI/CD integration, and scheduling guide.

## Quick Start

```bash
# Analyze all workloads
python3 -m shared.prompt_intelligence.cli analyze --all

# Analyze single workload
python3 -m shared.prompt_intelligence.cli analyze --workload customer_master

# Show only top 10 patterns
python3 -m shared.prompt_intelligence.cli analyze --all --top 10

# Save to specific file
python3 -m shared.prompt_intelligence.cli analyze --all --output my_report.md
```

## Output

Generates a markdown report in `docs/prompt_intelligence/YYYY-MM-DD_report.md` with:
- **Executive Summary**: Impact distribution, top blockers, estimated time savings
- **Failure Patterns**: Grouped by impact (BLOCKING, DEGRADED, MINOR)
- **Best Practices**: Validated decision patterns that consistently work
- **Implementation Guide**: Step-by-step instructions for applying fixes

## Pattern Types

| Type | Examples | Typical Cause |
|------|----------|---------------|
| **schema_error** | `KeyError: 'primary_key'` | Schema inference failures |
| **pii_false_positive** | `fund_name flagged as PII` | Overly aggressive PII detection |
| **quality_threshold** | `Completeness < 0.80` | Thresholds too strict |

## Architecture

```
trace_events.jsonl → FailureAnalyzer → aggregate_cross_workload() → ReportGenerator → report.md
```

## Requirements

- Python 3.8+
- Existing workloads with `logs/trace_events.jsonl` files
- AgentTracer-compatible trace format

## Files

```
shared/prompt_intelligence/
├── __init__.py                 # Module exports
├── cli.py                      # Command-line interface
├── failure_analyzer.py         # Extract failure patterns
├── success_profiler.py         # Extract success patterns
├── report_generator.py         # Generate markdown reports
├── schemas.py                  # Data structures
└── README.md                   # This file
```

## Limitations (MVP)

- Exact text matching for pattern grouping (no semantic similarity yet)
- Heuristic correlation between decisions and failures
- Manual prompt patching (no auto-injection)
- No feedback loop (can't track if applied fixes work)

Future versions will add Titan embeddings, DynamoDB storage, automated prompt injection, and feedback loop.
