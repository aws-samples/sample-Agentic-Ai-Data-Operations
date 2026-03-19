"""Tests for shared.reic.hierarchical_classifier."""

from pathlib import Path

import pytest
import yaml

from shared.reic.hierarchical_classifier import (
    ClassificationResult,
    HierarchicalClassifier,
)


@pytest.fixture
def classifier():
    return HierarchicalClassifier()


class TestClassification:
    def test_discovery_intent(self, classifier):
        result = classifier.classify("I want to onboard new data from our CRM")
        assert result.phase == "discovery"

    def test_build_transform_intent(self, classifier):
        result = classifier.classify("clean and transform the bronze data to silver")
        assert result.phase == "build"

    def test_deploy_intent(self, classifier):
        result = classifier.classify("deploy the pipeline to production and register in glue catalog")
        assert result.phase == "deploy"

    def test_profiling_intent(self, classifier):
        result = classifier.classify("profile the data and detect schema types and PII")
        assert result.phase == "profiling"

    def test_validation_intent(self, classifier):
        result = classifier.classify("validate and check if this source already exists duplicate")
        assert result.phase == "validation"


class TestConfidenceBounds:
    def test_phase_confidence_bounded(self, classifier):
        result = classifier.classify("anything")
        assert 0.0 <= result.phase_confidence <= 1.0

    def test_agent_confidence_bounded(self, classifier):
        result = classifier.classify("anything")
        assert 0.0 <= result.agent_confidence <= 1.0

    def test_action_confidence_bounded(self, classifier):
        result = classifier.classify("anything")
        assert 0.0 <= result.action_confidence <= 1.0


class TestHierarchyYAML:
    def test_hierarchy_loads(self, classifier):
        assert len(classifier.phases) == 5

    def test_expected_phases(self, classifier):
        assert set(classifier.phases) == {
            "discovery", "validation", "profiling", "build", "deploy"
        }

    def test_all_actions_have_intents(self, classifier):
        hierarchy = classifier.hierarchy
        for phase_name, phase_info in hierarchy["phases"].items():
            for agent_name, agent_info in phase_info.get("agents", {}).items():
                for action_name, action_info in agent_info.get("actions", {}).items():
                    intents = action_info.get("intents", [])
                    assert len(intents) > 0, (
                        f"{phase_name}/{agent_name}/{action_name} has no intents"
                    )

    def test_all_actions_have_tool_routing_ref(self, classifier):
        hierarchy = classifier.hierarchy
        for phase_name, phase_info in hierarchy["phases"].items():
            for agent_name, agent_info in phase_info.get("agents", {}).items():
                for action_name, action_info in agent_info.get("actions", {}).items():
                    ref = action_info.get("tool_routing_ref", "")
                    assert ref.startswith("TOOL_ROUTING.md"), (
                        f"{phase_name}/{agent_name}/{action_name} missing tool_routing_ref"
                    )


class TestDeterminism:
    def test_same_classification_twice(self, classifier):
        r1 = classifier.classify("clean the sales data")
        r2 = classifier.classify("clean the sales data")
        assert r1.phase == r2.phase
        assert r1.agent == r2.agent
        assert r1.action == r2.action
        assert r1.phase_confidence == r2.phase_confidence


class TestHelpers:
    def test_agents_for_phase(self, classifier):
        agents = classifier.agents_for_phase("build")
        assert "transformation" in agents
        assert "quality" in agents
        assert "dag" in agents

    def test_actions_for_agent(self, classifier):
        actions = classifier.actions_for_agent("build", "transformation")
        assert "bronze_to_silver" in actions
        assert "silver_to_gold" in actions
