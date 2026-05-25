"""Validate consolidated semantic-layer artifacts parse cleanly with rdflib."""
from pathlib import Path

import pytest
from rdflib import Graph

ROOT = Path(__file__).parent.parent


def test_ontology_parses():
    g = Graph()
    g.parse(ROOT / "ontology.ttl", format="turtle")
    assert len(g) > 0


def test_r2rml_mappings_parse():
    g = Graph()
    g.parse(ROOT / "r2rml-mappings.ttl", format="turtle")
    assert len(g) > 0
