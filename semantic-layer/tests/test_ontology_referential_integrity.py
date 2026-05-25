"""Every rdfs:domain / rdfs:range references a class declared in the ontology."""
from pathlib import Path

from rdflib import Graph, OWL, RDF, RDFS, XSD

ROOT = Path(__file__).parent.parent


def test_domain_range_references_existing_classes():
    g = Graph()
    g.parse(ROOT / "ontology.ttl", format="turtle")

    declared_classes = {s for s in g.subjects(RDF.type, OWL.Class)}

    # XSD datatype IRIs are valid ranges; collect them for the allowlist
    builtin_xsd = {XSD.string, XSD.integer, XSD.dateTime, XSD.date,
                   XSD.boolean, XSD.decimal, XSD.float, XSD.double}

    issues = []
    for prop in g.subjects(RDF.type, OWL.ObjectProperty):
        for rng in g.objects(prop, RDFS.range):
            if rng not in declared_classes:
                issues.append(f"ObjectProperty {prop} has range {rng} not declared as owl:Class")
        for dom in g.objects(prop, RDFS.domain):
            if dom not in declared_classes:
                issues.append(f"ObjectProperty {prop} has domain {dom} not declared as owl:Class")

    for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
        for dom in g.objects(prop, RDFS.domain):
            if dom not in declared_classes:
                issues.append(f"DatatypeProperty {prop} has domain {dom} not declared as owl:Class")
        for rng in g.objects(prop, RDFS.range):
            if rng not in builtin_xsd and rng not in declared_classes:
                issues.append(f"DatatypeProperty {prop} has range {rng} not in XSD nor declared")

    assert not issues, "\n".join(issues)
