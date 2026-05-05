"""
R2RML Mapper — generates R2RML TriplesMaps linking OWL classes to the
physical Glue/Athena Gold-zone tables that back them.

One TriplesMap per entity in semantic.yaml. Each map emits:
  - rr:logicalTable with an Athena-executable SQL query
  - rr:subjectMap with a URI template anchored on the primary key
  - one rr:predicateObjectMap per column (datatype + FK references)

Public API:
    generate_r2rml(ontology_ttl_path, semantic_yaml_path, glue_database,
                   namespace) -> R2RMLResult
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


R2RML_PREFIXES = """@prefix rr:   <http://www.w3.org/ns/r2rml#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix ex:   <{ex_uri}> .
@prefix :     <{ex_uri}> .

"""


# Map semantic.yaml / Glue types to xsd datatypes for R2RML rr:datatype
_TYPE_MAP = {
    "string": "xsd:string",
    "varchar": "xsd:string",
    "char": "xsd:string",
    "text": "xsd:string",
    "int": "xsd:integer",
    "integer": "xsd:integer",
    "bigint": "xsd:integer",
    "smallint": "xsd:integer",
    "tinyint": "xsd:integer",
    "long": "xsd:integer",
    "decimal": "xsd:decimal",
    "numeric": "xsd:decimal",
    "float": "xsd:decimal",
    "double": "xsd:decimal",
    "real": "xsd:decimal",
    "date": "xsd:date",
    "timestamp": "xsd:dateTime",
    "datetime": "xsd:dateTime",
    "boolean": "xsd:boolean",
    "bool": "xsd:boolean",
}


@dataclass
class R2RMLResult:
    mappings_ttl_path: str
    triples_map_count: int
    column_mappings_count: int
    fk_join_count: int
    warnings: List[str] = field(default_factory=list)


def _class_name(entity_name: str) -> str:
    parts = re.split(r"[_\s]+", entity_name.strip())
    pascal = "".join(p[:1].upper() + p[1:] for p in parts if p)
    if len(pascal) > 3 and pascal.endswith("s") and not pascal.endswith("ss"):
        pascal = pascal[:-1]
    return pascal or "Entity"


def _property_name(col_name: str) -> str:
    parts = re.split(r"[_\s]+", col_name.strip())
    if not parts:
        return col_name
    return parts[0].lower() + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _xsd_for(type_str: Optional[str]) -> str:
    if not type_str:
        return "xsd:string"
    base = type_str.strip().lower().split("(", 1)[0].strip()
    return _TYPE_MAP.get(base, "xsd:string")


def _detect_pk(table: Dict[str, Any], warnings: List[str]) -> Optional[str]:
    pk = table.get("primary_key")
    if pk:
        return pk
    for c in table.get("columns") or []:
        if c.get("role") == "identifier":
            return c.get("name")
        constraints = c.get("constraints") or []
        if "unique" in constraints and "not_null" in constraints:
            return c.get("name")
    cols = table.get("columns") or []
    if cols:
        name = cols[0].get("name")
        warnings.append(
            f"Table {table.get('name')}: no primary_key declared; falling "
            f"back to first column '{name}'."
        )
        return name
    return None


def generate_r2rml(
    ontology_ttl_path: str,
    semantic_yaml_path: str,
    glue_database: str,
    namespace: str,
) -> R2RMLResult:
    """
    Emit mappings.ttl next to the provided ontology.ttl.

    Args:
        ontology_ttl_path: Path to the ontology.ttl produced by induce_owl().
                           Used to anchor the output directory and to validate
                           that a corresponding ontology actually exists.
        semantic_yaml_path: Path to workloads/{name}/config/semantic.yaml
        glue_database: Glue database name for the FROM clause of the
                       logical-table SQL (e.g., "gold_financial_portfolios").
        namespace: ontology namespace (e.g., "finance"). Used for the
                   ex: and subject URI prefixes.

    Returns:
        R2RMLResult with counts + warnings.
    """
    ont_path = Path(ontology_ttl_path)
    if not ont_path.exists():
        raise FileNotFoundError(
            f"ontology.ttl not found at {ont_path}. Run induce_owl() first."
        )

    sem_path = Path(semantic_yaml_path)
    if not sem_path.exists():
        raise FileNotFoundError(f"semantic.yaml not found: {sem_path}")

    with sem_path.open("r", encoding="utf-8") as f:
        semantic = yaml.safe_load(f) or {}

    warnings: List[str] = []
    ex_uri = f"http://semantic.aws/{namespace}/ontology#"
    subject_base = f"http://semantic.aws/{namespace}/data"

    tables = sorted(semantic.get("tables") or [], key=lambda t: t.get("name", ""))
    # Track which columns are FKs per source table for rr:parentTriplesMap
    # emission.
    entity_names = {t.get("name") for t in tables if t.get("name")}
    pk_by_entity: Dict[str, Optional[str]] = {}
    for t in tables:
        if t.get("name"):
            pk_by_entity[t["name"]] = _detect_pk(t, warnings)

    out_lines: List[str] = []
    out_lines.append(R2RML_PREFIXES.format(ex_uri=ex_uri))

    triples_map_count = 0
    column_mappings_count = 0
    fk_join_count = 0

    for table in tables:
        name = table.get("name")
        if not name:
            continue
        cls_name = _class_name(name)
        pk = pk_by_entity.get(name)
        if not pk:
            warnings.append(f"Skipping TriplesMap for {name}: no primary key.")
            continue

        cols = table.get("columns") or []
        col_names = {c.get("name") for c in cols if c.get("name")}
        relationships = {
            rel.get("join_column"): rel
            for rel in (table.get("relationships") or [])
            if rel.get("join_column") and rel.get("target_table") in entity_names
        }

        map_iri = f"<#{cls_name}Mapping>"
        out_lines.append(f"{map_iri} a rr:TriplesMap ;")
        # Logical table: SELECT * FROM glue_db.table_name
        out_lines.append(
            f'    rr:logicalTable [ rr:sqlQuery """SELECT * FROM '
            f'{glue_database}.{name}""" ] ;'
        )
        # Subject map
        out_lines.append(
            f'    rr:subjectMap [\n'
            f'        rr:template "{subject_base}/{cls_name}/{{{pk}}}" ;\n'
            f'        rr:class ex:{cls_name}\n'
            f'    ] ;'
        )
        # Predicate-object maps (sorted for determinism)
        sorted_cols = sorted(cols, key=lambda c: c.get("name", ""))
        pom_lines: List[str] = []
        for col in sorted_cols:
            cname = col.get("name")
            if not cname:
                continue

            if cname in relationships:
                # FK column: emit rr:parentTriplesMap reference
                target_entity = relationships[cname]["target_table"]
                target_cls = _class_name(target_entity)
                pom_lines.append(
                    f"    rr:predicateObjectMap [\n"
                    f"        rr:predicate ex:has{target_cls} ;\n"
                    f"        rr:objectMap [\n"
                    f"            rr:parentTriplesMap <#{target_cls}Mapping> ;\n"
                    f"            rr:joinCondition [\n"
                    f'                rr:child "{cname}" ;\n'
                    f'                rr:parent "{pk_by_entity.get(target_entity, cname)}"\n'
                    f"            ]\n"
                    f"        ]\n"
                    f"    ]"
                )
                fk_join_count += 1
            # Always emit the datatype property too (FK columns are still
            # observable values).
            pom_lines.append(
                f"    rr:predicateObjectMap [\n"
                f"        rr:predicate ex:{_property_name(cname)} ;\n"
                f'        rr:objectMap [ rr:column "{cname}" ; '
                f"rr:datatype {_xsd_for(col.get('type'))} ]\n"
                f"    ]"
            )
            column_mappings_count += 1

        if pom_lines:
            out_lines.append(" ;\n".join(pom_lines) + " .")
        else:
            # no POMs; ensure the triples map terminates
            out_lines.append("    .")
        out_lines.append("")
        triples_map_count += 1

    out_text = "\n".join(out_lines).rstrip() + "\n"
    out_path = ont_path.parent / "mappings.ttl"
    out_path.write_text(out_text, encoding="utf-8")

    return R2RMLResult(
        mappings_ttl_path=str(out_path),
        triples_map_count=triples_map_count,
        column_mappings_count=column_mappings_count,
        fk_join_count=fk_join_count,
        warnings=warnings,
    )
