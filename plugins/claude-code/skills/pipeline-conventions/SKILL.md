---
name: pipeline-conventions
description: ADOP's data-engineering standards — the five quality dimensions and zone gates, zone mutability rules, transformation and schema-evolution rules, Airflow/PySpark and SQL/YAML conventions, testing strategy, and the shared glossary. Load this when writing a spec, authoring quality rules, extending a template, or when a term like Silver, SCD Type 2, R2RML or quality gate needs a precise meaning. These are the standards the vendored templates already encode — read them to extend a spec correctly, not to hand-write the artifact.
---

# Pipeline conventions

Derived from `.claude/rules/{03-python-airflow,04-sql,05-yaml,06-quality-testing,08-transformations,09-glossary}.md`
in the ADOP repository. In a checkout, the Airflow and SQL rules are **path-scoped** — they load
automatically when you edit a matching file. A plugin has no equivalent, so read this before
writing a spec rather than relying on a rule firing.

Most of what follows is already enforced by the vendored templates under
`lib/shared/templates/`. Read it so you can extend a **spec** correctly; artifacts still come
only from `scripts/adop_render.py`.

## Data zones — mutability is not negotiable

| Zone | Mutability | Quality gate | Format |
|---|---|---|---|
| Bronze | **IMMUTABLE** — any code that updates Bronze is a bug | none (raw ingestion) | raw source format |
| Silver | updatable, schema-enforced | score ≥ **0.80**, no critical failures | Apache Iceberg on S3 Tables, always |
| Gold | updatable, curated | score ≥ **0.95**, no critical failures | Iceberg, schema per use case |

Silver is always Iceberg — no exceptions. Registered in the Glue Data Catalog, time-travel
enabled, partitioned by business dimensions. Gold's shape is chosen during Phase 1: star schema
for reporting, flat Iceberg for analytics and ML, Iceberg plus DynamoDB for API serving.

## The five quality dimensions

**Completeness, Accuracy, Consistency, Validity, Uniqueness.** All five, named exactly.

This matters more than it looks: an earlier version of this plugin substituted its own set of
five and dropped **Accuracy** and **Consistency**. Quality scores then stop being comparable
between workloads, which is precisely the fragmentation ADOP exists to prevent — occurring
inside ADOP. `.claude/rules/06-quality-testing.md` is the authority.

- Quality checks are deterministic: the same data always yields the same score.
- A critical rule failure blocks zone promotion regardless of the overall score.
- Anomaly detection covers outliers (>3 std dev), distribution shifts, volume deviation (>20%)
  and null spikes.
- Always compare the current run against a historical baseline.

## Transformations

- MUST be **idempotent** — running twice produces identical output.
- **Never drop records silently** — quarantine failed records with error context.
- Schema evolution: new fields → add with `nullable=true`; removed fields → keep with nulls;
  type changes → safe cast, quarantine the failures.
- Always record lineage: source dataset, target dataset, transformation type, timestamp.
- Always validate the output schema against the SageMaker Catalog before writing.

## Airflow

Always: `catchup=False`, `max_active_runs=1`, `retries=3`, exponential backoff,
`on_failure_callback`, `TaskGroup` for stage organisation, Airflow Variables for configuration.

Never: hardcoded secrets, `SubDagOperator`, `provide_context=True`,
`start_date=datetime.now()`, `depends_on_past=True` without justification, inline computation in
the DAG file, disabled retries in production.

**Every `Variable.get()` MUST pass `default_var`.** Without it the DAG fails to parse and never
appears in the Airflow UI:

```python
glue_role = Variable.get("glue_iam_role", default_var="AWSGlueServiceRole")   # correct
glue_role = Variable.get("glue_iam_role")                                     # breaks parsing
```

Use `PythonOperator` calling scripts under `workloads/{name}/scripts/`, never inline logic.
Every DAG carries `doc_md` and an `sla` on critical tasks.

## Glue ETL

- All ETL targets the AWS Glue runtime: PySpark, `GlueContext`, `DynamicFrame`, Iceberg catalog.
  There is **no** local or pandas fallback mode.
- Read via `glue_context.create_dynamic_frame.from_catalog(...)` — never raw S3 paths.
- Write via the catalog: `df.writeTo("glue_catalog.db.table").using("iceberg")` — never
  `df.write.save("s3://...")`.
- Lineage writes use the boto3 S3 client, not `saveAsTextFile()`.

## SQL

- SQL lives in `workloads/{name}/sql/{zone}/`.
- Fully qualified table names: `database.schema.table`.
- CTEs over nested subqueries; always `LIMIT` analytical queries.
- Never `SELECT *` in production queries.
- Never DDL in Gold-zone SQL — Gold is read-only for analysis.

## YAML configuration

- Follow the config schemas for `source.yaml`, `transformations.yaml`, `quality_rules.yaml` and
  `schedule.yaml`.
- Never put credentials in YAML — reference Secrets Manager ARNs or Airflow Connection IDs.
- Comment any non-obvious choice.

## Testing

- **Unit tests** for every agent method, mocking external dependencies.
- **Property-based tests** for transformation idempotency, lineage completeness, quality
  monotonicity, schema preservation and Bronze immutability.
- **Integration tests**: sub-agents have no MCP or AWS access, so an integration test written by
  a sub-agent means *cross-artifact*, not cross-cloud — source fixture → spec → contract
  validator → rendered output → run context, asserted to agree. Tests needing live AWS belong to
  post-deployment verification, which the orchestrator runs.
- Coverage target 80% minimum.
- Place tests in `workloads/{name}/tests/`.

## Extending a template safely

If the renderer raises `MissingSlotError`, the spec is missing a value the template needs.
**Extend the spec schema and bump the template version — never edit the template to work
around it.** A template edit desynchronises every artifact already rendered from it, because the
provenance header records `template_hash` and the drift validator compares it.

## Glossary

| Term | Meaning |
|---|---|
| Bronze Zone | Raw, immutable data as ingested from source, original format preserved |
| Silver Zone | Cleaned, validated, schema-enforced — always Apache Iceberg on S3 Tables |
| Gold Zone | Curated, business-ready — Iceberg, format determined by use case |
| Apache Iceberg | Open table format — ACID transactions, time-travel, schema evolution, partition pruning |
| S3 Tables | S3 bucket type optimised for Iceberg — automatic compaction and catalog integration |
| SageMaker Catalog | Extends the Glue Data Catalog with custom metadata columns for business context |
| Ontology Staging | Induces OWL + R2RML from `semantic.yaml` + Glue schema, emits for AWS Semantic Layer handoff |
| AWS Semantic Layer | External platform consuming ADOP's staged OWL/R2RML — owns SHACL, T-Box, VKG, NL→SQL |
| R2RML | W3C standard mapping relational schemas to RDF — wires OWL classes to physical tables |
| MCP Layer | Model Context Protocol — standard interface for model interaction with the platform |
| Quality Gate | Threshold check that blocks data from advancing to the next zone |
| Lineage | Record of provenance — which source → which target via which transformation |
| SCD Type 2 | Slowly Changing Dimension — preserves historical records in Gold dimension tables |
| Star Schema | Fact table (measures + FK keys) plus dimension tables (attributes), for reporting/BI |
