"""Unit tests for shared.semantic_layer.owl_inducer against the
financial_portfolios semantic.yaml fixture.

These tests run locally with zero AWS dependencies. They verify:
- entity -> owl:Class mapping
- column roles -> owl:DatatypeProperty with correct xsd range
- relationships -> owl:ObjectProperty + owl:FunctionalProperty for many-to-one
- dimension hierarchies -> rdfs:subClassOf chain
- PII flags -> ex:piiClassification / ex:dataSensitivity annotations
- Glue enrichment -> ex:autoInduced annotations for Glue-only columns
- Valid Turtle output (rdflib parse)
- Deterministic output (two runs produce byte-identical files)
- Namespace prefix @prefix ex: <http://orion.aws/{namespace}/ontology#>
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

# Make shared/ importable when running from the workload directory.
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from shared.semantic_layer.owl_inducer import induce_owl  # noqa: E402


SEMANTIC_YAML = PROJECT_ROOT / "workloads" / "financial_portfolios" / "config" / "semantic.yaml"
NAMESPACE = "finance"
EX = Namespace(f"http://orion.aws/{NAMESPACE}/ontology#")


@pytest.fixture
def induce(tmp_path):
    """Induce into a temp directory so tests don't clobber the real file."""
    # Copy semantic.yaml into tmp so out path is isolated.
    dest = tmp_path / "semantic.yaml"
    dest.write_text(SEMANTIC_YAML.read_text(encoding="utf-8"), encoding="utf-8")
    return induce_owl(
        semantic_yaml_path=str(dest),
        glue_database="gold_financial_portfolios",
        glue_table="fact_positions",
        namespace=NAMESPACE,
        version="v1",
    )


@pytest.fixture
def graph(induce):
    g = Graph()
    g.parse(induce.ontology_ttl_path, format="turtle")
    return g


class TestEntityToClass:
    def test_portfolio_class_exists(self, graph):
        assert (EX.Portfolio, RDF.type, OWL.Class) in graph

    def test_position_class_exists(self, graph):
        assert (EX.Position, RDF.type, OWL.Class) in graph

    def test_stock_class_exists(self, graph):
        assert (EX.Stock, RDF.type, OWL.Class) in graph

    def test_class_has_label(self, graph):
        labels = list(graph.objects(EX.Portfolio, RDFS.label))
        assert Literal("portfolios") in labels


class TestColumnToDatatypeProperty:
    def test_dimension_string_column(self, graph):
        """company_name is role=dimension, type=string -> xsd:string range."""
        assert (EX.companyName, RDF.type, OWL.DatatypeProperty) in graph
        ranges = list(graph.objects(EX.companyName, RDFS.range))
        assert XSD.string in ranges

    def test_measure_decimal_column(self, graph):
        """market_cap_billions is role=measure, type=decimal -> xsd:decimal range."""
        assert (EX.marketCapBillions, RDF.type, OWL.DatatypeProperty) in graph
        ranges = list(graph.objects(EX.marketCapBillions, RDFS.range))
        assert XSD.decimal in ranges

    def test_measure_has_default_aggregation(self, graph):
        """Measures expose their default_aggregation as ex:defaultAggregation."""
        aggs = list(graph.objects(EX.marketCapBillions, EX.defaultAggregation))
        assert Literal("sum") in aggs

    def test_temporal_date_column(self, graph):
        """listing_date is role=temporal, type=date -> xsd:date range."""
        assert (EX.listingDate, RDF.type, OWL.DatatypeProperty) in graph
        ranges = list(graph.objects(EX.listingDate, RDFS.range))
        assert XSD.date in ranges

    def test_identifier_flagged_primary_key(self, graph):
        """ticker is role=identifier -> ex:isPrimaryKey true."""
        pks = list(graph.objects(EX.ticker, EX.isPrimaryKey))
        assert pks, "ticker should have ex:isPrimaryKey annotation"


class TestRelationshipToObjectProperty:
    def test_positions_to_portfolio_object_property(self, graph):
        """positions -> portfolios (many_to_one) emits hasPortfolio + FunctionalProperty."""
        assert (EX.hasPortfolio, RDF.type, OWL.ObjectProperty) in graph
        # many_to_one should also be FunctionalProperty
        assert (EX.hasPortfolio, RDF.type, OWL.FunctionalProperty) in graph

    def test_object_property_domain_and_range(self, graph):
        domains = list(graph.objects(EX.hasPortfolio, RDFS.domain))
        ranges = list(graph.objects(EX.hasPortfolio, RDFS.range))
        assert EX.Position in domains
        assert EX.Portfolio in ranges


class TestHierarchyToSubclass:
    def test_equity_classification_has_subclass_chain(self, graph):
        """equity_classification: sector -> industry -> ticker (rdfs:subClassOf chain)."""
        assert (EX.Industry, RDFS.subClassOf, EX.Sector) in graph

    def test_portfolio_management_chain(self, graph):
        """manager -> strategy -> risk_level -> portfolio."""
        assert (EX.Strategy, RDFS.subClassOf, EX.Manager) in graph
        assert (EX.RiskLevel, RDFS.subClassOf, EX.Strategy) in graph


class TestPIIAnnotation:
    def test_manager_name_has_pii_classification(self, graph):
        """portfolios.manager_name has pii_classification.type=NAME."""
        piis = list(graph.objects(EX.managerName, EX.piiClassification))
        assert Literal("NAME") in piis

    def test_manager_name_has_sensitivity(self, graph):
        sens = list(graph.objects(EX.managerName, EX.dataSensitivity))
        assert Literal("MEDIUM") in sens


class TestGlueEnrichment:
    def test_auto_induced_column_marked(self, tmp_path):
        dest = tmp_path / "semantic.yaml"
        dest.write_text(SEMANTIC_YAML.read_text(encoding="utf-8"), encoding="utf-8")
        glue_schema = {
            "columns": [
                {"name": "etl_run_id", "type": "string", "comment": "Added by Glue job"},
                # Known column — should NOT be re-emitted
                {"name": "position_id", "type": "bigint"},
            ]
        }
        result = induce_owl(
            semantic_yaml_path=str(dest),
            glue_database="gold_financial_portfolios",
            glue_table="positions",
            namespace=NAMESPACE,
            glue_schema=glue_schema,
        )
        assert result.auto_induced_count == 1

        g = Graph()
        g.parse(result.ontology_ttl_path, format="turtle")
        auto_flags = list(g.objects(EX.etlRunId, EX.autoInduced))
        assert Literal(True) in auto_flags

    def test_known_column_not_auto_induced(self, tmp_path):
        dest = tmp_path / "semantic.yaml"
        dest.write_text(SEMANTIC_YAML.read_text(encoding="utf-8"), encoding="utf-8")
        glue_schema = {"columns": [{"name": "position_id", "type": "bigint"}]}
        result = induce_owl(
            semantic_yaml_path=str(dest),
            glue_database="gold_financial_portfolios",
            glue_table="positions",
            namespace=NAMESPACE,
            glue_schema=glue_schema,
        )
        # position_id is already in semantic.yaml -> should not be auto-induced
        assert result.auto_induced_count == 0


class TestValidTurtleOutput:
    def test_parses_without_error(self, induce):
        g = Graph()
        # No exception = valid turtle
        g.parse(induce.ontology_ttl_path, format="turtle")
        assert len(g) > 100, f"Expected substantial triple count, got {len(g)}"


class TestNamespacePrefix:
    def test_ex_prefix_in_turtle(self, induce):
        text = Path(induce.ontology_ttl_path).read_text(encoding="utf-8")
        assert f"@prefix ex: <http://orion.aws/{NAMESPACE}/ontology#>" in text


class TestDeterminism:
    def test_two_runs_produce_identical_bytes(self, tmp_path):
        dest = tmp_path / "semantic.yaml"
        dest.write_text(SEMANTIC_YAML.read_text(encoding="utf-8"), encoding="utf-8")
        r1 = induce_owl(
            semantic_yaml_path=str(dest),
            glue_database="gold_financial_portfolios",
            glue_table="fact_positions",
            namespace=NAMESPACE,
        )
        hash1 = hashlib.sha256(Path(r1.ontology_ttl_path).read_bytes()).hexdigest()
        r2 = induce_owl(
            semantic_yaml_path=str(dest),
            glue_database="gold_financial_portfolios",
            glue_table="fact_positions",
            namespace=NAMESPACE,
        )
        hash2 = hashlib.sha256(Path(r2.ontology_ttl_path).read_bytes()).hexdigest()
        assert hash1 == hash2


class TestCounts:
    def test_class_count_positive(self, induce):
        assert induce.class_count > 0

    def test_datatype_property_count_matches_columns(self, induce):
        # financial_portfolios has 40+ columns across 3 tables
        assert induce.datatype_property_count >= 40

    def test_object_property_count_positive(self, induce):
        # 3 relationships between stocks/portfolios/positions
        assert induce.object_property_count >= 2

    def test_pii_flagged_count_positive(self, induce):
        # manager_name has pii_classification in fixture
        assert induce.pii_flagged_count >= 1


class TestMissingSemanticYaml:
    def test_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            induce_owl(
                semantic_yaml_path="/nonexistent/semantic.yaml",
                glue_database="db",
                glue_table="t",
                namespace="ns",
            )
