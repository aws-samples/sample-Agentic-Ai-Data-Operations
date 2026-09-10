# Transformation Rules

> **Scope (convention, not runtime-enforced):** these rules apply when writing or
> editing transformation artifacts — `workloads/**/scripts/**`,
> `workloads/**/sql/**`, and `workloads/**/config/transformations.yaml`. On Claude
> Code this file loaded only for those paths via frontmatter globs; Amazon Q
> Developer CLI has no glob-conditional rule loading, so this rule is always in
> context. Apply it only when the current task touches transformation logic, and
> ignore it otherwise.

- Transformations MUST be **idempotent** — running twice produces identical output
- Never drop records silently — quarantine failed records with error context
- Schema evolution: new fields → add with `nullable=true`; removed fields → keep with nulls; type changes → safe cast, quarantine failures
- Always record lineage: source dataset, target dataset, transformation type, timestamp
- Always validate output schema against the SageMaker Catalog before writing

## Data Zone Mutability

- **Bronze**: IMMUTABLE. Never modify after ingestion. Any code that updates Bronze is a bug.
- **Silver**: Updatable (schema-enforced). Always Apache Iceberg on S3 Tables.
- **Gold**: Updatable (curated). Iceberg, schema determined by use case.

## Silver is always Iceberg — no exceptions

Registered in Glue Data Catalog. Time-travel enabled. Partitioned by business dimensions.
