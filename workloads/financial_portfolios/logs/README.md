# Pipeline Execution Logs

This folder contains execution traces and logs for the financial_portfolios pipeline.

## Structure

```
logs/
├── trace_events.jsonl          # Cumulative trace history (all runs)
├── run_YYYYMMDD_HHMMSS/       # Per-run logs
│   ├── README.md              # Run summary
│   ├── orchestrator.log       # Phase transitions, test gates
│   ├── extract.log            # Bronze extraction logs
│   ├── transform.log          # Silver transformation logs
│   ├── quality.log            # Quality check results
│   ├── load.log               # Gold load logs
│   └── lineage.jsonl          # Data lineage events
└── latest -> run_YYYYMMDD_HHMMSS/  # Symlink to latest run
```

## Demo Data (Historical Runs)

This directory contains **sample logs** from historical pipeline runs to demonstrate the system:

| Run ID | Date | Status | Rows | Duration | Quality (Silver/Gold) |
|--------|------|--------|------|----------|---------------------|
| `run-20260320-130512` | 2026-03-20 | ✅ Initial Deployment | - | 362s | - |
| `run-20260322-091523` | 2026-03-22 | ✅ Success | 203 | 111s | 0.98 / 0.99 |
| `run-20260323-091545` | 2026-03-23 | ✅ Success | 203 | 110s | 0.98 / 0.99 |

**Sample Run Directory**: `run_20260322_091523/` contains detailed logs showing all three logging layers in action.

## Log Layers

| Layer | Source | Content |
|-------|--------|---------|
| **Orchestrator** | `shared/logging/agent_tracer.py` | Phase transitions, retries, test gates |
| **ETL Scripts** | `shared/utils/structured_logger.py` | Row counts, transforms, quality scores |
| **Agent Decisions** | Sub-agent output | Reasoning, alternatives, confidence |

## Viewing Logs

**Latest run:**
```bash
cd logs/latest
tail -f orchestrator.log
```

**Trace history:**
```bash
python ../../shared/logging/trace_viewer.py trace_events.jsonl
```

**Search events:**
```bash
grep "quality_check" trace_events.jsonl | jq .
```

## Retention

- `trace_events.jsonl` — committed to git (cumulative history)
- `run_*/` folders — ignored by git (per-run ephemeral logs)
- Old runs are retained locally but not synced to repo
