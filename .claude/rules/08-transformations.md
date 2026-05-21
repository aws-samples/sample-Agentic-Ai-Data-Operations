---
paths:
  - "workloads/**/scripts/**"
  - "workloads/**/sql/**"
  - "workloads/**/config/transformations.yaml"
---

# Transformation Rules

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
