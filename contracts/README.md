# Spec Contracts

Versioned JSON Schemas (Draft 2020-12) that define the shape of every workload configuration file. The codegen renderer validates specs against these contracts before rendering artifacts.

For how contracts connect to templates, the renderer and the drift validator, and how to extend them to new zones, data sources and data targets, see [How contracts are wired](../README.md#how-contracts-are-wired) and [Extending contracts](../README.md#extending-contracts) in the main README.

## Versioning Policy

- Schemas are **immutable** once published. A released `v1/` schema is never modified.
- Adding a new required field or removing an existing one requires a new version directory (`v2/`).
- Adding an **optional** field with a default is a non-breaking change — add it as a new property with `"default"` in the schema within the same version.
- A spec selects its contract with `schema_version`. `shared.codegen.spec_loader.load_spec(path, spec_type, schema_version)` resolves `contracts/{schema_version}/{schema}` through `SPEC_TYPE_TO_SCHEMA`. Any spec missing `schema_version` is rejected.
- Both versions stay accepted while workloads migrate. The planned `contracts/migrations/` directory for v1 → v2 migration scripts does not exist yet; migrate specs by hand and re-render.

## Schema Files

| Schema | v1 | v2 | Validates | Used By |
|--------|----|----|-----------|---------|
| `source_profile.schema.json` | ✓ | | `config/source.yaml` | Phase 3 profiling output |
| `bronze_spec.schema.json` | ✓ | ✓ | `config/bronze.yaml` | `bronze_ingestion` template |
| `silver_spec.schema.json` | ✓ | | `config/silver.yaml` | `silver_transform`, `iceberg_ddl` templates |
| `gold_spec.schema.json` | ✓ | ✓ | `config/gold.yaml` | `gold_aggregate`, `iceberg_ddl` templates |
| `quality_spec.schema.json` | ✓ | | `config/quality_rules.yaml` | `quality_check` template |
| `dag_spec.schema.json` | ✓ | ✓ | `config/schedule.yaml` | `airflow_dag`, `glue_job_config` templates |
| `workload_manifest.schema.json` | ✓ | | Top-level manifest | Drift validator |
| `run_context.schema.json` | ✓ | | `run/context.json` | Orchestrator (writes end of Phase 2), every sub-agent (reads) |

What v2 changed: `bronze_spec` v2 makes `catalog_database`, `catalog_table` and `idempotency_key` required. `gold_spec` v2 and `dag_spec` v2 keep the v1 fields and required list; the version selects different template behavior. A v2 DAG renders the IANA schedule timezone into the Airflow start date, and v2 Gold adds approved passthrough controls.

## Validation

Check that every schema is valid JSON Schema Draft 2020-12:

```bash
python3 -c "import json, glob; from jsonschema import Draft202012Validator as V; [V.check_schema(json.load(open(f))) for f in glob.glob('contracts/v*/*.schema.json')]; print('ok')"
```

`.pre-commit-config.yaml` defines a `contracts-schema-validator` hook that calls `scripts/validate_contracts.py`. That script is not in the repository yet, so the hook fails until it is added.
