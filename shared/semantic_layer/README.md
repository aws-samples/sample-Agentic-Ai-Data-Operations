# shared/semantic_layer — ADOP → ORION Ontology Staging

This package is ADOP's **only** semantic-layer code path. It generates an
OWL2 ontology + R2RML mappings from each workload's `semantic.yaml` +
Glue Gold-zone table schema, validates Turtle syntax, and emits three
artifacts to `workloads/{name}/config/` for handoff to ORION.

## Scope boundary

### ADOP does (this package)

- Induce OWL classes from `semantic.yaml` entities.
- Induce OWL datatype properties from column roles + Glue types.
- Induce OWL object properties from explicit relationships (FKs).
- Chain dimension hierarchies as `rdfs:subClassOf`.
- Tag PII-flagged columns with `ex:piiClassification` + `ex:dataSensitivity`.
- Auto-induce properties for Glue columns not present in `semantic.yaml`
  (marked with `ex:autoInduced "true"`).
- Generate one R2RML `TriplesMap` per entity, wiring OWL classes to
  physical Glue/Athena tables.
- Validate Turtle with `rdflib` + apply bounded auto-fixes (max 2 retries).
- Write `ontology_manifest.json` with SHA-256 checksums + steward checklist.

### ADOP does NOT (future / Data Steward / ORION)

- Run T-Box reasoning (HermiT / ELK).
- Author SHACL constraints.
- Run SHACL validation.
- Publish to a VKG (Ontop).
- Write to Neptune, S3, DynamoDB, or SNS.

Those are the Data Steward's responsibilities inside ORION, once ORION
is deployed in AWS.

## Public API

```python
from shared.semantic_layer import induce_and_stage

result = induce_and_stage(
    dataset_name="financial_portfolios",
    glue_database="gold_financial_portfolios",
    glue_table="fact_positions",
    namespace="finance",
    glue_schema=glue_schema_dict,   # optional; from glue-athena MCP get_table
    version="v1",                   # optional
    mode="local",                   # default; mode="orion" raises NotImplementedError
)

# result.ontology_ttl_path, result.mappings_ttl_path, result.manifest_path
# result.owl_class_count, result.pii_flagged_count, ...
```

### Individual steps (rarely called directly)

- `induce_owl(semantic_yaml_path, glue_database, glue_table, namespace, version, glue_schema)` → `OWLInductionResult`
- `generate_r2rml(ontology_ttl_path, semantic_yaml_path, glue_database, namespace)` → `R2RMLResult`
- `validate_and_fix(ttl_path, max_retries=2)` → `ValidationResult`
- `write_manifest(...)` → `OntologyManifest`

## Determinism guarantee

Running `induce_and_stage` twice on the same `semantic.yaml` + same
`glue_schema` produces **byte-identical** `ontology.ttl` and
`mappings.ttl` files. Triples are emitted in IRI-sorted order and the
Turtle body is re-sorted before serialization. The SHA-256 checksums in
the manifest will be stable across reruns.

This matters when ORION ships: the already-committed local TTL files
are the canonical source for publish. No regeneration needed — the
future `ontology-publish-agent` just reads them and pushes to AWS.

## Output schema

Three artifacts land in `workloads/{dataset_name}/config/`:

| File | Contents |
|---|---|
| `ontology.ttl` | `@prefix` block + OWL `Ontology` header + one block per class, property, hierarchy level. Always valid Turtle. |
| `mappings.ttl` | R2RML `TriplesMap` per entity: `rr:logicalTable` (Athena SQL), `rr:subjectMap` (URI template on PK), `rr:predicateObjectMap` for each column + FK joins. |
| `ontology_manifest.json` | `state`, `namespace`, `version`, `created_at`, SHA-256 checksums of inputs/outputs, counts, steward review checklist, warnings. `state="STAGED_LOCAL"` in this iteration. |

## When ORION deploys

The `mode="orion"` branch currently raises `NotImplementedError`. When
ORION is deployed, a follow-up will:

1. Implement `stage_ontology(mode="orion", orion_config=...)` to:
   - Write triples to Neptune draft named graph via SPARQL `INSERT DATA`.
   - Upload TTL + manifest to `s3://{knowledge-layer-bucket}/ontologies/{namespace}/{version}/staged/`.
   - Write DynamoDB record to `orion-ontology-versions` with `state=STAGED`.
   - Publish SNS notification to the steward topic.
2. Add a new prompt `prompts/data-onboarding-agent/ontology-publish-agent.md`
   that reads the already-committed local TTL files and pushes them to
   AWS. No regeneration — deterministic inducer means identical inputs
   give identical outputs.

Because the local files are canonical, switching to ORION is strictly
additive: nothing about today's local output changes.

## Dependencies

- `rdflib >=7.0,<8` — RDF graph + Turtle serialization + parsing.
- `pyyaml` — `semantic.yaml` parsing (already a base dep).
- `shared/metadata/semantic_reader.py` — reused for YAML parsing (no new parser written here).

No AWS SDK dependency in this iteration (local-only).
