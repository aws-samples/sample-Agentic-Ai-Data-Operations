# Spec Contracts

Versioned JSON Schemas (Draft 2020-12) that define the shape of every workload configuration file. The codegen renderer validates specs against these contracts before rendering artifacts.

Zone contracts are organization defaults: Bronze, Silver, and Gold rules apply
to every domain and project. Optional domain/project policy files and per-run
user answers may only tighten those defaults. Source and target contracts are
separate because they vary by workload and connector.

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
| `target_profile.schema.json` | ✓ | | `config/target.yaml` | Target contract for the selected sink |
| `bronze_spec.schema.json` | ✓ | ✓ | `config/bronze.yaml` | `bronze_ingestion` template |
| `silver_spec.schema.json` | ✓ | | `config/silver.yaml` | `silver_transform`, `iceberg_ddl` templates |
| `gold_spec.schema.json` | ✓ | ✓ | `config/gold.yaml` | `gold_aggregate`, `iceberg_ddl` templates |
| `quality_spec.schema.json` | ✓ | | `config/quality_rules.yaml` | `quality_check` template |
| `dag_spec.schema.json` | ✓ | ✓ | `config/schedule.yaml` | `airflow_dag`, `glue_job_config` templates |
| `workload_manifest.schema.json` | ✓ | | Top-level manifest | Drift validator |
| `run_context.schema.json` | ✓ | | `run/context.json` | Orchestrator (writes end of Phase 2), every sub-agent (reads) |

What v2 changed: `bronze_spec` v2 makes `catalog_database`, `catalog_table` and `idempotency_key` required. `gold_spec` v2 and `dag_spec` v2 keep the v1 fields and required list; the version selects different template behavior. A v2 DAG renders the IANA schedule timezone into the Airflow start date, and v2 Gold adds approved passthrough controls.

## Governance contract hierarchy

The effective zone policy is resolved before rendering:

```text
organization default → domain policy → project policy → per-run override
```

The organization default is stored in
`contracts/policies/organization/default.yaml`. Domain and project files are
optional. A user can accept the inherited policy and continue without extra
zone questions, or provide a per-run override in
`run/context.json#human_answers.contract_overrides`.

Lower layers cannot reduce a quality threshold, disable PII detection, change
the required Iceberg format, or contradict an inherited immutability or
encryption rule. The resolver records an effective policy hash for deployment
preflight.

Bronze supports CSV, Parquet, JSON, Avro, ORC, XML, and raw log text. XML
requires a `row_tag`; logs remain raw in Bronze and declare a `log_type` to
guide approved Silver transformations. XML readers must disable DTD and
external-entity resolution.

## Validation

Check that every schema is valid JSON Schema Draft 2020-12:

```bash
python3 -c "import json, glob; from jsonschema import Draft202012Validator as V; [V.check_schema(json.load(open(f))) for f in glob.glob('contracts/v*/*.schema.json')]; print('ok')"
```

`.pre-commit-config.yaml` defines a `contracts-schema-validator` hook that calls `scripts/validate_contracts.py`. That script is not in the repository yet, so the hook fails until it is added.
