"""Unit tests for shared.semantic_layer.r2rml_mapper."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, URIRef

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from shared.semantic_layer.owl_inducer import induce_owl  # noqa: E402
from shared.semantic_layer.r2rml_mapper import generate_r2rml  # noqa: E402

SEMANTIC_YAML = PROJECT_ROOT / "workloads" / "financial_portfolios" / "config" / "semantic.yaml"
NAMESPACE = "finance"
GLUE_DB = "gold_financial_portfolios"
RR = Namespace("http://www.w3.org/ns/r2rml#")
EX = Namespace(f"http://orion.aws/{NAMESPACE}/ontology#")


@pytest.fixture
def mappings(tmp_path):
    dest = tmp_path / "semantic.yaml"
    dest.write_text(SEMANTIC_YAML.read_text(encoding="utf-8"), encoding="utf-8")
    owl_result = induce_owl(
        semantic_yaml_path=str(dest),
        glue_database=GLUE_DB,
        glue_table="fact_positions",
        namespace=NAMESPACE,
    )
    return generate_r2rml(
        ontology_ttl_path=owl_result.ontology_ttl_path,
        semantic_yaml_path=str(dest),
        glue_database=GLUE_DB,
        namespace=NAMESPACE,
    )


@pytest.fixture
def graph(mappings):
    g = Graph()
    g.parse(mappings.mappings_ttl_path, format="turtle")
    return g


class TestTriplesMapGeneration:
    def test_one_triples_map_per_entity(self, mappings):
        # financial_portfolios has 3 tables: stocks, portfolios, positions
        assert mappings.triples_map_count == 3

    def test_triples_map_declared_as_r2rml_type(self, graph):
        triples_maps = list(graph.subjects(predicate=None, object=RR.TriplesMap))
        # RDF query: find subjects of type rr:TriplesMap
        triples_maps = [s for s, p, o in graph if p.endswith("type") and o == RR.TriplesMap]
        assert len(triples_maps) >= 3


class TestLogicalTable:
    def test_logical_table_sql_present(self, mappings):
        text = Path(mappings.mappings_ttl_path).read_text(encoding="utf-8")
        assert "rr:sqlQuery" in text
        assert f"SELECT * FROM {GLUE_DB}.portfolios" in text


class TestSubjectMap:
    def test_subject_uri_template(self, mappings):
        text = Path(mappings.mappings_ttl_path).read_text(encoding="utf-8")
        # subject URI template for Portfolio should key on portfolio_id
        assert "http://orion.aws/finance/data/Portfolio/{portfolio_id}" in text

    def test_subject_class_binding(self, mappings):
        text = Path(mappings.mappings_ttl_path).read_text(encoding="utf-8")
        assert "rr:class ex:Portfolio" in text
        assert "rr:class ex:Stock" in text
        assert "rr:class ex:Position" in text


class TestColumnMappings:
    def test_column_mappings_emitted(self, mappings):
        # financial_portfolios has 40+ columns — expect many predicateObjectMaps
        assert mappings.column_mappings_count >= 40

    def test_datatype_mapping(self, mappings):
        text = Path(mappings.mappings_ttl_path).read_text(encoding="utf-8")
        # market_cap_billions is decimal
        assert "market_cap_billions" in text
        assert "xsd:decimal" in text


class TestForeignKeyJoins:
    def test_fk_join_present(self, mappings):
        # positions has FKs to portfolios (portfolio_id) and stocks (ticker)
        assert mappings.fk_join_count >= 2

    def test_parent_triples_map_emitted(self, mappings):
        text = Path(mappings.mappings_ttl_path).read_text(encoding="utf-8")
        assert "rr:parentTriplesMap" in text
        assert "<#PortfolioMapping>" in text
        assert "<#StockMapping>" in text

    def test_join_condition_has_child_and_parent(self, mappings):
        text = Path(mappings.mappings_ttl_path).read_text(encoding="utf-8")
        assert "rr:child" in text
        assert "rr:parent" in text


class TestValidTurtleOutput:
    def test_mappings_parses_without_error(self, mappings):
        g = Graph()
        g.parse(mappings.mappings_ttl_path, format="turtle")
        assert len(g) > 50


class TestMissingOntology:
    def test_raises_when_ontology_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            generate_r2rml(
                ontology_ttl_path=str(tmp_path / "nonexistent.ttl"),
                semantic_yaml_path=str(SEMANTIC_YAML),
                glue_database=GLUE_DB,
                namespace=NAMESPACE,
            )
