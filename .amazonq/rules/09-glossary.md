# Glossary

| Term | Meaning |
|---|---|
| Bronze Zone | Raw, immutable data as ingested from source (original format preserved) |
| Silver Zone | Cleaned, validated, schema-enforced data — always Apache Iceberg on S3 Tables |
| Gold Zone | Curated, business-ready data — Iceberg tables in format determined by use case |
| Apache Iceberg | Open table format — ACID transactions, time-travel, schema evolution, partition pruning |
| S3 Tables | Amazon S3 bucket type optimized for Iceberg — automatic compaction and catalog integration |
| SageMaker Catalog | Extends Glue Data Catalog with custom metadata columns for business context |
| Ontology Staging | Induces OWL + R2RML from `semantic.yaml` + Glue schema, emits for AWS Semantic Layer handoff |
| AWS Semantic Layer | External platform consuming ADOP's staged OWL/R2RML — owns SHACL, T-Box, VKG, NL→SQL |
| R2RML | W3C standard mapping relational schemas to RDF — wires OWL classes to physical tables |
| MCP Layer | Model Context Protocol — standard interface for AI model interaction with the platform |
| Quality Gate | Threshold check that blocks data from advancing to the next zone |
| Lineage | Record of data provenance — which source → which target via which transformation |
| SCD Type 2 | Slowly Changing Dimension — preserves historical records in Gold dimension tables |
| Star Schema | Fact table (measures + FK keys) + dimension tables (attributes) — for reporting/BI |
