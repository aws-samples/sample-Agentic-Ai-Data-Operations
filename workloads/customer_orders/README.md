# customer_orders

This workload contains the checked-in customer-orders pipeline artifacts for
the shared ADOP repository.

Run tests from the repository root:

```bash
python3 -m pytest workloads/customer_orders/tests/ -q
```

Runtime evidence belongs inside this workload:

- `run/` — requirements, context, and decisions
- `logs/` — `trace_events.jsonl` and per-run traces

The generated scripts, DAG, and SQL are renderer-owned artifacts.
