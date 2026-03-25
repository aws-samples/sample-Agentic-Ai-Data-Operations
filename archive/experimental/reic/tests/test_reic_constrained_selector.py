"""Tests for shared.reic.constrained_selector."""

import pytest
from shared.reic.constrained_selector import (
    AgentSelection,
    ConstrainedAgentSelector,
    TfIdfScorer,
)


@pytest.fixture
def selector():
    """Selector with keyword-based scorer."""
    keywords = {
        "router": ["check existing", "find workload", "search workloads"],
        "data_onboarding": ["new source", "onboard", "gather requirements", "deploy"],
        "metadata": ["profile data", "detect schema", "generate config", "pii"],
        "transformation": ["clean data", "transform", "bronze to silver", "silver to gold"],
        "quality": ["quality rules", "quality check", "validation", "anomaly"],
        "dag": ["create dag", "schedule", "airflow", "orchestrate"],
    }
    scorer = TfIdfScorer(keywords)
    return ConstrainedAgentSelector(scorer=scorer)


class TestConstrainedSelection:
    def test_selects_valid_agent(self, selector):
        result = selector.select("clean the data", phase="build")
        assert result.agent in ["metadata", "transformation", "quality", "dag"]

    def test_phase_constrains_agents(self, selector):
        result = selector.select("anything", phase="profiling")
        assert result.constrained_set == ["metadata"]
        assert result.agent == "metadata"

    def test_discovery_agents(self, selector):
        result = selector.select("check if data exists", phase="discovery")
        assert result.agent in ["router", "data_onboarding"]

    def test_deploy_phase(self, selector):
        result = selector.select("deploy to production", phase="deploy")
        assert result.agent == "data_onboarding"

    def test_build_transformation(self, selector):
        result = selector.select("clean data bronze to silver transform", phase="build")
        assert result.agent == "transformation"

    def test_build_quality(self, selector):
        result = selector.select("quality rules validation check", phase="build")
        assert result.agent == "quality"

    def test_build_dag(self, selector):
        result = selector.select("create dag schedule airflow", phase="build")
        assert result.agent == "dag"


class TestProbabilities:
    def test_softmax_sums_to_one(self, selector):
        result = selector.select("transform data", phase="build")
        total = sum(result.all_probabilities.values())
        assert abs(total - 1.0) < 1e-6

    def test_probabilities_bounded(self, selector):
        result = selector.select("anything", phase="build")
        for p in result.all_probabilities.values():
            assert 0.0 <= p <= 1.0

    def test_top_agent_has_highest_prob(self, selector):
        result = selector.select("clean data", phase="build")
        assert result.probability == max(result.all_probabilities.values())


class TestDeterminism:
    def test_same_result_twice(self, selector):
        r1 = selector.select("clean the sales data", phase="build")
        r2 = selector.select("clean the sales data", phase="build")
        assert r1.agent == r2.agent
        assert r1.probability == r2.probability


class TestErrors:
    def test_invalid_phase_raises(self, selector):
        with pytest.raises(ValueError, match="Unknown phase"):
            selector.select("anything", phase="nonexistent")

    def test_unconstrained_selection(self, selector):
        result = selector.select("clean data")
        assert result.agent in ConstrainedAgentSelector.ALL_AGENTS
