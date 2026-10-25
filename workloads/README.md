# Workloads

`workloads/` contains one governed data-pipeline directory per onboarded
dataset. Workload paths are relative to the repository root.

## Current checked-in workload

### `customer_orders`

The repository currently contains one workload:

```text
workloads/customer_orders/
```

It includes Bronze → Silver → Gold configuration, rendered scripts, SQL, a
DAG, and unit/integration tests.

Run its tests from the repository root:

```bash
python3 -m pytest workloads/customer_orders/tests/ -q
```

## Workload structure

```text
workloads/{name}/
├── config/       Human-confirmed source, semantic, transformation, quality, and schedule rules
├── scripts/      Renderer-produced extract, transform, quality, and load code
├── dags/         Renderer-produced Airflow/MWAA DAGs
├── sql/          Bronze, Silver, and Gold SQL
├── tests/        Unit and integration tests
├── run/          Run context, captured requirements, and decisions
├── logs/         Runtime traces, including trace_events.jsonl
└── README.md     Workload-specific documentation
```

The `run/` and `logs/` directories are workload-local and must not be replaced
with repository-level directories. Every pipeline run must produce:

```text
workloads/{name}/run/requirements.jsonl
workloads/{name}/run/decisions.jsonl
workloads/{name}/logs/trace_events.jsonl
```

Artifacts under `scripts/`, `dags/`, and `sql/` must be produced by the
deterministic renderer. Do not hand-edit those generated files.
