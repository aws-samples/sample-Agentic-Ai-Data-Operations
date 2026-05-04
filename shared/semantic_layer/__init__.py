"""
shared.semantic_layer — ORION ontology staging for ADOP.

ADOP's semantic-layer responsibility: generate OWL (ontology.ttl) + R2RML
(mappings.ttl) from each workload's semantic.yaml + Glue Catalog schema,
validate Turtle syntax, stage locally for handoff to ORION.

What ADOP does NOT do:
- Run T-Box reasoning (HermiT/ELK)  -> ORION at publish time
- Author SHACL constraints           -> Data Steward in ORION
- Run SHACL validation               -> ORION at publish time
- Publish to VKG                     -> Data Steward approves in ORION
- Write to Neptune/DynamoDB/S3       -> Future, when ORION deploys

Top-level usage (called by the Ontology Staging sub-agent):

    from shared.semantic_layer import induce_and_stage

    result = induce_and_stage(
        dataset_name="financial_portfolios",
        glue_database="gold_db",
        glue_table="fact_positions",
        namespace="finance",
        glue_schema=glue_schema_dict,   # fetched via glue-athena MCP get_table
    )

    # result.ontology_ttl_path, result.mappings_ttl_path,
    # result.manifest_path, result.class_count, etc.
"""

from shared.semantic_layer.owl_inducer import (
    OWLInductionResult,
    induce_owl,
)
from shared.semantic_layer.r2rml_mapper import (
    R2RMLResult,
    generate_r2rml,
)
from shared.semantic_layer.turtle_validator import (
    ValidationResult,
    validate_and_fix,
)
from shared.semantic_layer.manifest import (
    OntologyManifest,
    write_manifest,
)
from shared.semantic_layer.staging_service import (
    StagingResult,
    stage_ontology,
    induce_and_stage,
)

__all__ = [
    "OWLInductionResult",
    "induce_owl",
    "R2RMLResult",
    "generate_r2rml",
    "ValidationResult",
    "validate_and_fix",
    "OntologyManifest",
    "write_manifest",
    "StagingResult",
    "stage_ontology",
    "induce_and_stage",
]
