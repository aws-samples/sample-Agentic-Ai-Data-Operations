"""
Ontology manifest writer.

Emits `ontology_manifest.json` alongside ontology.ttl + mappings.ttl with
version metadata, SHA-256 checksums of source + output artifacts, counts,
and the Data Steward review checklist.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_STEWARD_CHECKLIST: List[str] = [
    "Verify OWL class names match business terminology.",
    "Review auto-induced properties (ex:autoInduced=true) for correctness.",
    "Author SHACL constraints for business rules (in ORION).",
    "Check PII-flagged properties have correct classification + sensitivity.",
    "Validate R2RML mappings point to the correct Gold-zone tables.",
    "Run T-Box reasoning and SHACL validation in ORION before publish.",
]


@dataclass
class OntologyManifest:
    namespace: str
    version: str
    state: str  # "STAGED_LOCAL" today; "STAGED_ORION" when ORION is wired.
    created_at: str
    created_by: str
    source_workload: str
    source_glue_database: str
    source_glue_table: str
    source_semantic_yaml_sha256: str
    ontology_ttl_path: str
    ontology_ttl_sha256: str
    mappings_ttl_path: str
    mappings_ttl_sha256: str
    owl_class_count: int
    owl_datatype_property_count: int
    owl_object_property_count: int
    pii_flagged_count: int
    auto_induced_count: int
    r2rml_triples_map_count: int
    r2rml_column_mappings_count: int
    r2rml_fk_join_count: int
    awaiting_action: str = "DATA_STEWARD_REVIEW"
    review_checklist: List[str] = field(default_factory=lambda: list(DEFAULT_STEWARD_CHECKLIST))
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def sha256_file(path: str | Path) -> str:
    """Compute SHA-256 hex digest of a file's bytes."""
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(
    *,
    manifest_path: str | Path,
    namespace: str,
    version: str,
    source_workload: str,
    source_glue_database: str,
    source_glue_table: str,
    semantic_yaml_path: str,
    ontology_ttl_path: str,
    mappings_ttl_path: str,
    owl_class_count: int,
    owl_datatype_property_count: int,
    owl_object_property_count: int,
    pii_flagged_count: int,
    auto_induced_count: int,
    r2rml_triples_map_count: int,
    r2rml_column_mappings_count: int,
    r2rml_fk_join_count: int,
    state: str = "STAGED_LOCAL",
    created_by: str = "ADOP/ontology-staging-agent",
    created_at: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> OntologyManifest:
    """Build and write an OntologyManifest to `manifest_path`."""
    manifest = OntologyManifest(
        namespace=namespace,
        version=version,
        state=state,
        created_at=created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        created_by=created_by,
        source_workload=source_workload,
        source_glue_database=source_glue_database,
        source_glue_table=source_glue_table,
        source_semantic_yaml_sha256=sha256_file(semantic_yaml_path),
        ontology_ttl_path=str(ontology_ttl_path),
        ontology_ttl_sha256=sha256_file(ontology_ttl_path),
        mappings_ttl_path=str(mappings_ttl_path),
        mappings_ttl_sha256=sha256_file(mappings_ttl_path),
        owl_class_count=owl_class_count,
        owl_datatype_property_count=owl_datatype_property_count,
        owl_object_property_count=owl_object_property_count,
        pii_flagged_count=pii_flagged_count,
        auto_induced_count=auto_induced_count,
        r2rml_triples_map_count=r2rml_triples_map_count,
        r2rml_column_mappings_count=r2rml_column_mappings_count,
        r2rml_fk_join_count=r2rml_fk_join_count,
        warnings=warnings or [],
    )
    out_path = Path(manifest_path)
    out_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
