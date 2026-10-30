# Spec Contracts

Versioned JSON Schemas (Draft 2020-12) that define the shape of every workload configuration file. The codegen renderer validates specs against these contracts before rendering artifacts.

Bronze, Silver, and Gold use organization defaults. Optional domain/project
policies and per-run overrides may only tighten those defaults. Source and
target contracts remain separate because they vary by workload and connector.

Bronze supports CSV, Parquet, JSON, Avro, ORC, XML, and raw log text. XML
requires a `row_tag`; logs remain raw in Bronze and declare a `log_type` to
guide approved Silver transformations. XML readers must disable DTD and
external-entity resolution.

## Versioning Policy

- Schemas are **immutable** once published. A released `v1/` schema is never modified.
- Adding a new required field or removing an existing one requires a new version directory (`v2/`).
- Adding an **optional** field with a default is a non-breaking change — add it as a new property with `"default"` in the schema within the same version.
- A `v1` → `v2` migration requires a migration script under `contracts/migrations/` (that directory does not exist yet — no second version has been cut) and a dual-validation period where both versions are accepted.
- Any spec missing `schema_version` is rejected by `shared.codegen.spec_loader`.

## Schema Files (v1)

| Schema | Validates | Used By |
|--------|-----------|---------|
| `source_profile.schema.json` | `config/source.yaml` | Phase 3 profiling output |
| `target_profile.schema.json` | `config/target.yaml` | Target contract for the selected sink |
| `bronze_spec.schema.json` | Bronze ingestion spec | Bronze ingestion template |
| `silver_spec.schema.json` | Silver transform spec | Silver transform template |
| `gold_spec.schema.json` | Gold aggregation spec | Gold aggregate template |
| `quality_spec.schema.json` | Quality rules spec | Quality check template |
| `dag_spec.schema.json` | DAG scheduling spec | Airflow DAG template |
| `workload_manifest.schema.json` | Top-level manifest | Drift validator |
| `run_context.schema.json` | `run/context.json` | Orchestrator (writes end of Phase 2), every sub-agent (reads) |

## Validation

Run `python scripts/validate_contracts.py` to confirm all schemas are valid JSON Schema Draft 2020-12.

The pre-commit hook `contracts-schema-validator` runs this automatically on changes to `contracts/**/*.schema.json`.
