# Pipeline Execution Logs

This folder contains execution traces and logs for the product_inventory pipeline.

## Structure

```
logs/
├── trace_events.jsonl          # Cumulative trace history (all runs)
├── run_YYYYMMDD_HHMMSS/       # Per-run logs
│   ├── trace.jsonl            # This run's trace events
│   ├── orchestrator.log       # Phase transitions, test gates
│   ├── extract.log            # Bronze extraction logs
│   ├── transform.log          # Silver transformation logs
│   ├── quality.log            # Quality check results
│   └── load.log               # Gold load logs
└── latest -> run_YYYYMMDD_HHMMSS/  # Symlink to latest run
```

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
