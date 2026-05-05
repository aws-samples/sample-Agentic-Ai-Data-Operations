"""
Staging Service — the single entry point the Ontology Staging sub-agent
calls. In this iteration it runs in `mode="local"`, which emits three
artifacts to `workloads/{name}/config/` and performs NO AWS calls:

    - ontology.ttl                  (OWL2, validated with rdflib)
    - mappings.ttl                  (R2RML wiring OWL to Glue Gold tables)
    - ontology_manifest.json        (state=STAGED_LOCAL, checksums, steward checklist)

The `mode="aws_semantic_layer"` branch is stubbed with NotImplementedError
so the call sites (sub-agent prompt, future orchestration) are stable.
When the upcoming AWS Semantic Layer deploys, a follow-up implements that
branch to read the already committed TTL files and push them to
Neptune SPARQL + S3 + DynamoDB + SNS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from shared.semantic_layer.manifest import OntologyManifest, write_manifest
from shared.semantic_layer.owl_inducer import OWLInductionResult, induce_owl
from shared.semantic_layer.r2rml_mapper import R2RMLResult, generate_r2rml
from shared.semantic_layer.turtle_validator import ValidationResult, validate_and_fix


@dataclass
class StagingResult:
    state: str
    workload: str
    namespace: str
    version: str
    ontology_ttl_path: str
    mappings_ttl_path: str
    manifest_path: str
    owl_class_count: int
    owl_datatype_property_count: int
    owl_object_property_count: int
    pii_flagged_count: int
    auto_induced_count: int
    r2rml_triples_map_count: int
    r2rml_column_mappings_count: int
    r2rml_fk_join_count: int
    ontology_triple_count: int
    mappings_triple_count: int
    warnings: List[str] = field(default_factory=list)
    fixes_applied: List[str] = field(default_factory=list)


def induce_and_stage(
    *,
    dataset_name: str,
    glue_database: str,
    glue_table: str,
    namespace: str,
    version: str = "v1",
    glue_schema: Optional[Dict[str, Any]] = None,
    mode: Literal["local", "aws_semantic_layer"] = "local",
    aws_semantic_layer_config: Optional[Dict[str, Any]] = None,
    workload_root: str = "workloads",
) -> StagingResult:
    """
    End-to-end staging: induce OWL -> generate R2RML -> validate both TTL
    files -> write manifest.

    Args:
        dataset_name: Workload directory name under workload_root/.
        glue_database: Glue database name for R2RML logical-table SQL.
        glue_table: Gold-zone table name that anchors the induction.
        namespace: Ontology namespace prefix (e.g., "finance").
        version: Ontology version string. Default "v1".
        glue_schema: Optional dict for Glue-enrichment of columns not
                     in semantic.yaml. Shape: {"columns":
                     [{"name": str, "type": str, "comment": str}]}.
        mode: "local" (today) or "aws_semantic_layer" (future, not implemented).
        aws_semantic_layer_config: Reserved for future
                                   `mode="aws_semantic_layer"` parameters.
        workload_root: Root directory where workloads live. Default
                       "workloads" (relative).

    Returns:
        StagingResult with paths, counts, warnings, and fixes applied.

    Raises:
        FileNotFoundError: If semantic.yaml is missing.
        NotImplementedError: If mode="aws_semantic_layer" (platform not yet deployed).
        RuntimeError: If Turtle validation fails after max retries.
    """
    return stage_ontology(
        dataset_name=dataset_name,
        glue_database=glue_database,
        glue_table=glue_table,
        namespace=namespace,
        version=version,
        glue_schema=glue_schema,
        mode=mode,
        aws_semantic_layer_config=aws_semantic_layer_config,
        workload_root=workload_root,
    )


def stage_ontology(
    *,
    dataset_name: str,
    glue_database: str,
    glue_table: str,
    namespace: str,
    version: str = "v1",
    glue_schema: Optional[Dict[str, Any]] = None,
    mode: Literal["local", "aws_semantic_layer"] = "local",
    aws_semantic_layer_config: Optional[Dict[str, Any]] = None,
    workload_root: str = "workloads",
) -> StagingResult:
    """See induce_and_stage(). Same implementation; kept for API parity."""
    if mode == "aws_semantic_layer":
        raise NotImplementedError(
            "AWS Semantic Layer deployment pending. The "
            "`mode='aws_semantic_layer'` branch will be implemented in a "
            "follow-up prompt (prompts/data-onboarding-agent/"
            "ontology-publish-agent.md) once the platform's Neptune cluster, "
            "DynamoDB version table, S3 knowledge-layer bucket, and SNS "
            "steward topic exist. For now, commit the local TTL files "
            "emitted by `mode='local'` and hand them off to the Data "
            "Steward out-of-band."
        )
    if mode != "local":
        raise ValueError(
            f"Unknown mode: {mode!r}. Expected 'local' or 'aws_semantic_layer'."
        )

    config_dir = Path(workload_root) / dataset_name / "config"
    semantic_yaml_path = config_dir / "semantic.yaml"
    if not semantic_yaml_path.exists():
        raise FileNotFoundError(
            f"semantic.yaml not found at {semantic_yaml_path}. "
            f"Run the Metadata Agent first to populate the semantic layer."
        )

    # Step 1: OWL induction
    owl_result: OWLInductionResult = induce_owl(
        semantic_yaml_path=str(semantic_yaml_path),
        glue_database=glue_database,
        glue_table=glue_table,
        namespace=namespace,
        version=version,
        glue_schema=glue_schema,
    )

    # Step 2: Validate ontology.ttl
    ont_validation: ValidationResult = validate_and_fix(owl_result.ontology_ttl_path)
    if not ont_validation.ok:
        raise RuntimeError(
            f"Generated ontology.ttl failed Turtle validation after max "
            f"retries. Fixes attempted: {ont_validation.fixes_applied}. "
            f"Last error: {ont_validation.error}"
        )

    # Step 3: R2RML mapping
    r2rml_result: R2RMLResult = generate_r2rml(
        ontology_ttl_path=owl_result.ontology_ttl_path,
        semantic_yaml_path=str(semantic_yaml_path),
        glue_database=glue_database,
        namespace=namespace,
    )

    # Step 4: Validate mappings.ttl
    map_validation: ValidationResult = validate_and_fix(r2rml_result.mappings_ttl_path)
    if not map_validation.ok:
        raise RuntimeError(
            f"Generated mappings.ttl failed Turtle validation after max "
            f"retries. Fixes attempted: {map_validation.fixes_applied}. "
            f"Last error: {map_validation.error}"
        )

    # Step 5: Write manifest
    manifest_path = config_dir / "ontology_manifest.json"
    warnings = list(owl_result.warnings) + list(r2rml_result.warnings)
    write_manifest(
        manifest_path=manifest_path,
        namespace=namespace,
        version=version,
        source_workload=dataset_name,
        source_glue_database=glue_database,
        source_glue_table=glue_table,
        semantic_yaml_path=str(semantic_yaml_path),
        ontology_ttl_path=owl_result.ontology_ttl_path,
        mappings_ttl_path=r2rml_result.mappings_ttl_path,
        owl_class_count=owl_result.class_count,
        owl_datatype_property_count=owl_result.datatype_property_count,
        owl_object_property_count=owl_result.object_property_count,
        pii_flagged_count=owl_result.pii_flagged_count,
        auto_induced_count=owl_result.auto_induced_count,
        r2rml_triples_map_count=r2rml_result.triples_map_count,
        r2rml_column_mappings_count=r2rml_result.column_mappings_count,
        r2rml_fk_join_count=r2rml_result.fk_join_count,
        warnings=warnings,
    )

    fixes_applied: List[str] = []
    if ont_validation.fixes_applied:
        fixes_applied.extend(f"ontology.ttl:{f}" for f in ont_validation.fixes_applied)
    if map_validation.fixes_applied:
        fixes_applied.extend(f"mappings.ttl:{f}" for f in map_validation.fixes_applied)

    return StagingResult(
        state="STAGED_LOCAL",
        workload=dataset_name,
        namespace=namespace,
        version=version,
        ontology_ttl_path=owl_result.ontology_ttl_path,
        mappings_ttl_path=r2rml_result.mappings_ttl_path,
        manifest_path=str(manifest_path),
        owl_class_count=owl_result.class_count,
        owl_datatype_property_count=owl_result.datatype_property_count,
        owl_object_property_count=owl_result.object_property_count,
        pii_flagged_count=owl_result.pii_flagged_count,
        auto_induced_count=owl_result.auto_induced_count,
        r2rml_triples_map_count=r2rml_result.triples_map_count,
        r2rml_column_mappings_count=r2rml_result.column_mappings_count,
        r2rml_fk_join_count=r2rml_result.fk_join_count,
        ontology_triple_count=ont_validation.triple_count,
        mappings_triple_count=map_validation.triple_count,
        warnings=warnings,
        fixes_applied=fixes_applied,
    )
