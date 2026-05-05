"""
OWL Inducer — converts semantic.yaml + Glue Catalog schema into an OWL2
ontology serialized as Turtle.

Determinism: All triples are emitted in IRI-sorted order so SHA-256 of
the output ontology.ttl is stable across runs with identical inputs.

Public API:
    induce_owl(semantic_yaml_path, glue_database, glue_table, namespace,
               version="v1", glue_schema=None) -> OWLInductionResult
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Map semantic.yaml / Glue type strings to xsd datatypes
_TYPE_MAP = {
    "string": XSD.string,
    "varchar": XSD.string,
    "char": XSD.string,
    "text": XSD.string,
    "int": XSD.integer,
    "integer": XSD.integer,
    "bigint": XSD.integer,
    "smallint": XSD.integer,
    "tinyint": XSD.integer,
    "long": XSD.integer,
    "decimal": XSD.decimal,
    "numeric": XSD.decimal,
    "float": XSD.decimal,
    "double": XSD.decimal,
    "real": XSD.decimal,
    "date": XSD.date,
    "timestamp": XSD.dateTime,
    "datetime": XSD.dateTime,
    "boolean": XSD.boolean,
    "bool": XSD.boolean,
}


@dataclass
class OWLInductionResult:
    ontology_ttl_path: str
    class_count: int
    datatype_property_count: int
    object_property_count: int
    pii_flagged_count: int
    auto_induced_count: int
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _class_name(entity_name: str) -> str:
    """Convert entity_name -> ClassName (snake_case -> PascalCase, singular)."""
    parts = re.split(r"[_\s]+", entity_name.strip())
    pascal = "".join(p[:1].upper() + p[1:] for p in parts if p)
    # crude singularization: trim trailing 's' if length > 3 and not 'ss'
    if len(pascal) > 3 and pascal.endswith("s") and not pascal.endswith("ss"):
        pascal = pascal[:-1]
    return pascal or "Entity"


def _property_name(col_name: str) -> str:
    """Convert column_name -> propertyName (snake_case -> camelCase)."""
    parts = re.split(r"[_\s]+", col_name.strip())
    if not parts:
        return col_name
    return parts[0].lower() + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _xsd_for(type_str: Optional[str]) -> URIRef:
    """Map a type string (possibly parameterized like 'decimal(12,2)') to xsd:*."""
    if not type_str:
        return XSD.string
    base = type_str.strip().lower().split("(", 1)[0].strip()
    return _TYPE_MAP.get(base, XSD.string)


def _safe_literal(value: Any) -> Optional[Literal]:
    """Best-effort Literal coercion. Returns None if value is None or empty."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return Literal(s)


def _sorted_tables(semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    tables = semantic.get("tables") or []
    return sorted(tables, key=lambda t: t.get("name", ""))


def _find_primary_entity(semantic: Dict[str, Any], glue_table: str) -> Optional[Dict[str, Any]]:
    """Try to match the glue_table to a semantic.yaml table (fact preferred)."""
    tables = semantic.get("tables") or []
    gt = glue_table.lower()

    # exact name match first
    for t in tables:
        if t.get("name", "").lower() == gt:
            return t

    # strip common prefixes (fact_, dim_, gold_)
    for t in tables:
        name = t.get("name", "").lower()
        if gt in (f"fact_{name}", f"dim_{name}", f"gold_{name}", f"{name}_gold"):
            return t

    # fallback to first fact table
    for t in tables:
        if t.get("table_type") == "fact":
            return t

    return tables[0] if tables else None


# ---------------------------------------------------------------------------
# Main induction
# ---------------------------------------------------------------------------

def induce_owl(
    semantic_yaml_path: str,
    glue_database: str,
    glue_table: str,
    namespace: str,
    version: str = "v1",
    glue_schema: Optional[Dict[str, Any]] = None,
) -> OWLInductionResult:
    """
    Induce an OWL ontology from semantic.yaml + Glue table schema.

    Args:
        semantic_yaml_path: Path to workloads/{name}/config/semantic.yaml
        glue_database: Glue database name the Gold table lives in
        glue_table: The Gold table name that grounds this induction
        namespace: ontology namespace (e.g., "finance")
        version: Ontology version (default "v1")
        glue_schema: Optional dict {"columns": [{"name": str, "type": str,
                     "comment": Optional[str]}]} for the Gold table. If
                     provided, columns not in semantic.yaml are emitted with
                     ex:autoInduced "true" annotations. If None, no Glue
                     enrichment happens.

    Returns:
        OWLInductionResult with counts + warnings. The ontology.ttl is
        written to the same directory as semantic_yaml_path.
    """
    path = Path(semantic_yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"semantic.yaml not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        semantic = yaml.safe_load(f) or {}

    warnings: List[str] = []
    EX = Namespace(f"http://semantic.aws/{namespace}/ontology#")

    g = Graph()
    g.bind("", EX)
    g.bind("ex", EX)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)

    # Ontology header
    ontology_iri = URIRef(f"http://semantic.aws/{namespace}/ontology/{version}")
    g.add((ontology_iri, RDF.type, OWL.Ontology))
    g.add((ontology_iri, RDFS.label, Literal(f"{namespace} ontology {version}")))
    g.add((ontology_iri, RDFS.comment, Literal(
        f"Induced from semantic.yaml + Glue table {glue_database}.{glue_table} by ADOP."
    )))

    tables = _sorted_tables(semantic)
    class_count = 0
    datatype_property_count = 0
    object_property_count = 0
    pii_flagged_count = 0

    # Track entity-to-class IRI so relationships can reference them
    class_iri_by_entity: Dict[str, URIRef] = {}
    columns_by_entity: Dict[str, Dict[str, Dict[str, Any]]] = {}
    pk_by_entity: Dict[str, Optional[str]] = {}

    # Pass 1: emit one owl:Class per semantic.yaml table
    for table in tables:
        name = table.get("name")
        if not name:
            warnings.append("Table without name skipped.")
            continue
        cls_name = _class_name(name)
        cls_iri = EX[cls_name]
        class_iri_by_entity[name] = cls_iri
        columns_by_entity[name] = {
            c.get("name"): c for c in (table.get("columns") or []) if c.get("name")
        }
        pk_by_entity[name] = _detect_pk(table)

        g.add((cls_iri, RDF.type, OWL.Class))
        g.add((cls_iri, RDFS.label, Literal(name)))
        desc = table.get("description")
        if desc:
            g.add((cls_iri, RDFS.comment, Literal(desc)))
        ttype = table.get("table_type")
        if ttype:
            g.add((cls_iri, EX.tableType, Literal(ttype)))
        grain = table.get("grain")
        if grain:
            g.add((cls_iri, EX.grain, Literal(grain)))
        class_count += 1

    # Pass 2: emit datatype properties for every column
    # Sort column keys too so output is deterministic.
    for entity_name in sorted(columns_by_entity.keys()):
        cls_iri = class_iri_by_entity[entity_name]
        cols = columns_by_entity[entity_name]
        for col_name in sorted(cols.keys()):
            col = cols[col_name]
            prop_iri = EX[_property_name(col_name)]
            rng = _xsd_for(col.get("type"))
            g.add((prop_iri, RDF.type, OWL.DatatypeProperty))
            g.add((prop_iri, RDFS.domain, cls_iri))
            g.add((prop_iri, RDFS.range, rng))
            g.add((prop_iri, RDFS.label, Literal(col_name)))
            desc = col.get("description")
            if desc:
                g.add((prop_iri, RDFS.comment, Literal(desc)))

            role = col.get("role")
            if role:
                g.add((prop_iri, EX.role, Literal(role)))
                if role == "measure":
                    agg = col.get("default_aggregation")
                    if agg:
                        g.add((prop_iri, EX.defaultAggregation, Literal(agg)))
                    unit = col.get("unit")
                    if unit:
                        g.add((prop_iri, EX.unit, Literal(unit)))
                if role == "identifier":
                    g.add((prop_iri, EX.isPrimaryKey, Literal(True)))

            pii = col.get("pii_classification")
            if pii:
                pii_flagged_count += 1
                ptype = pii.get("type")
                sens = pii.get("sensitivity")
                if ptype:
                    g.add((prop_iri, EX.piiClassification, Literal(ptype)))
                if sens:
                    g.add((prop_iri, EX.dataSensitivity, Literal(sens)))

            datatype_property_count += 1

    # Pass 3: emit object properties for explicit relationships
    for table in tables:
        src_name = table.get("name")
        if not src_name or src_name not in class_iri_by_entity:
            continue
        rels = table.get("relationships") or []
        for rel in sorted(rels, key=lambda r: r.get("target_table", "")):
            tgt_name = rel.get("target_table")
            if not tgt_name or tgt_name not in class_iri_by_entity:
                warnings.append(
                    f"Relationship from {src_name} -> {tgt_name} skipped "
                    f"(target not in semantic.yaml)."
                )
                continue
            rel_type = (rel.get("type") or "").lower()
            # Property IRI: has{Target}
            prop_iri = EX[f"has{_class_name(tgt_name)}"]
            g.add((prop_iri, RDF.type, OWL.ObjectProperty))
            g.add((prop_iri, RDFS.domain, class_iri_by_entity[src_name]))
            g.add((prop_iri, RDFS.range, class_iri_by_entity[tgt_name]))
            g.add((prop_iri, RDFS.label, Literal(f"has{_class_name(tgt_name)}")))
            if rel.get("description"):
                g.add((prop_iri, RDFS.comment, Literal(rel["description"])))
            if rel.get("join_column"):
                g.add((prop_iri, EX.joinColumn, Literal(rel["join_column"])))
            if rel_type in ("many_to_one", "many-to-one", "n_to_1"):
                g.add((prop_iri, RDF.type, OWL.FunctionalProperty))
            object_property_count += 1

    # Pass 4: dimension hierarchies -> rdfs:subClassOf chain between level names
    hierarchies = semantic.get("dimension_hierarchies") or []
    for hierarchy in sorted(hierarchies, key=lambda h: h.get("name", "")):
        hname = hierarchy.get("name")
        levels = hierarchy.get("levels") or []
        if not hname or len(levels) < 2:
            continue
        root_iri = EX[_class_name(hname)]
        g.add((root_iri, RDF.type, OWL.Class))
        g.add((root_iri, RDFS.label, Literal(hname)))
        class_count += 1
        # Chain levels: level[i+1] subClassOf level[i]
        sorted_levels = sorted(levels, key=lambda L: L.get("level", 0))
        prev_iri = root_iri
        for lvl in sorted_levels:
            lname = lvl.get("name")
            if not lname:
                continue
            lvl_iri = EX[_class_name(lname)]
            if (lvl_iri, RDF.type, OWL.Class) not in g:
                g.add((lvl_iri, RDF.type, OWL.Class))
                g.add((lvl_iri, RDFS.label, Literal(lname)))
                class_count += 1
            g.add((lvl_iri, RDFS.subClassOf, prev_iri))
            if lvl.get("description"):
                g.add((lvl_iri, RDFS.comment, Literal(lvl["description"])))
            prev_iri = lvl_iri

    # Pass 5: Glue enrichment — columns in Glue but not in semantic.yaml
    auto_induced_count = 0
    if glue_schema:
        primary_entity = _find_primary_entity(semantic, glue_table)
        if primary_entity:
            primary_cls = class_iri_by_entity.get(primary_entity.get("name"))
            known_cols = set(
                (columns_by_entity.get(primary_entity.get("name")) or {}).keys()
            )
            glue_cols = glue_schema.get("columns") or []
            for col in sorted(glue_cols, key=lambda c: c.get("name", "")):
                cname = col.get("name")
                if not cname or cname in known_cols:
                    continue
                prop_iri = EX[_property_name(cname)]
                g.add((prop_iri, RDF.type, OWL.DatatypeProperty))
                if primary_cls:
                    g.add((prop_iri, RDFS.domain, primary_cls))
                g.add((prop_iri, RDFS.range, _xsd_for(col.get("type"))))
                g.add((prop_iri, RDFS.label, Literal(cname)))
                if col.get("comment"):
                    g.add((prop_iri, RDFS.comment, Literal(col["comment"])))
                g.add((prop_iri, EX.autoInduced, Literal(True)))
                auto_induced_count += 1
                datatype_property_count += 1
        else:
            warnings.append(
                f"Glue enrichment skipped: no semantic.yaml table matched "
                f"Glue table {glue_table}."
            )

    # Serialize — sorted for determinism
    out_path = path.parent / "ontology.ttl"
    ttl_bytes = g.serialize(format="turtle", encoding="utf-8")
    # rdflib does not guarantee triple order in Turtle output; sort the body
    # lines (preserving @prefix header) to lock determinism.
    ttl_text = ttl_bytes.decode("utf-8")
    ttl_text = _deterministic_sort_turtle(ttl_text)
    out_path.write_text(ttl_text, encoding="utf-8")

    return OWLInductionResult(
        ontology_ttl_path=str(out_path),
        class_count=class_count,
        datatype_property_count=datatype_property_count,
        object_property_count=object_property_count,
        pii_flagged_count=pii_flagged_count,
        auto_induced_count=auto_induced_count,
        warnings=warnings,
    )


def _detect_pk(table: Dict[str, Any]) -> Optional[str]:
    """Find the primary key column for a table."""
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
    return cols[0].get("name") if cols else None


def _deterministic_sort_turtle(ttl_text: str) -> str:
    """
    Sort body statements of a Turtle document to lock determinism.

    Treats `@prefix` / `@base` lines as the header (kept in original order,
    deduplicated) and sorts every remaining statement block (ending with
    `.`) alphabetically. Blank lines between blocks are preserved.
    """
    lines = ttl_text.splitlines()
    header = []
    seen_prefix = set()
    body_lines: List[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("@prefix") or stripped.startswith("@base"):
            if stripped not in seen_prefix:
                header.append(lines[i])
                seen_prefix.add(stripped)
            i += 1
        else:
            break
    body_lines = lines[i:]

    # Split body into statement blocks. A statement is a sequence of lines
    # ending at a line whose stripped content ends with '.' and is not part
    # of a blank-node / string literal continuation. rdflib's Turtle output
    # is flat enough that line-ending '.' is a reliable delimiter.
    blocks: List[str] = []
    current: List[str] = []
    for line in body_lines:
        current.append(line)
        if line.rstrip().endswith("."):
            blocks.append("\n".join(current).rstrip())
            current = []
    if current and any(ln.strip() for ln in current):
        blocks.append("\n".join(current).rstrip())

    blocks = [b for b in blocks if b.strip()]
    blocks.sort()

    out = "\n".join(header).rstrip()
    if out:
        out += "\n\n"
    out += "\n\n".join(blocks) + "\n"
    return out
