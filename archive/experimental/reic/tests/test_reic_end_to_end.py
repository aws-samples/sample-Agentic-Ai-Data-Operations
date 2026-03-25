"""End-to-end integration tests for REIC pipeline."""

import pytest

from shared.reic import (
    ConstrainedAgentSelector,
    HierarchicalClassifier,
    WorkloadIndex,
)


@pytest.fixture(scope="module")
def index():
    idx = WorkloadIndex(workloads_dir="workloads")
    count = idx.build_index()
    assert count > 0
    return idx


@pytest.fixture(scope="module")
def classifier():
    return HierarchicalClassifier()


TEST_INTENTS = [
    ("I want to onboard new CRM data", "discovery"),
    ("check if sales data already exists", "validation"),
    ("validate the source configuration", "validation"),
    ("profile the dataset and detect schema", "profiling"),
    ("find PII columns in the data", "profiling"),
    ("clean data from bronze to silver", "build"),
    ("create a star schema in gold zone", "build"),
    ("generate quality rules and thresholds", "build"),
    ("create an airflow DAG for scheduling", "build"),
    ("deploy the pipeline and register in glue", "deploy"),
]


class TestEndToEnd:
    @pytest.mark.parametrize("intent,expected_phase", TEST_INTENTS)
    def test_classify_intent(self, classifier, intent, expected_phase):
        result = classifier.classify(intent)
        assert result.phase == expected_phase, (
            f"Intent '{intent}' classified as '{result.phase}', "
            f"expected '{expected_phase}'"
        )

    def test_phase_agent_action_chain(self, classifier):
        """Every classification produces a complete phase->agent->action chain."""
        for intent, _ in TEST_INTENTS:
            result = classifier.classify(intent)
            assert result.phase, f"Missing phase for '{intent}'"
            assert result.agent, f"Missing agent for '{intent}'"
            assert result.action, f"Missing action for '{intent}'"
            assert result.action != "unknown", (
                f"Action is 'unknown' for '{intent}' "
                f"(phase={result.phase}, agent={result.agent})"
            )

    def test_index_search_with_classification(self, index, classifier):
        """Index search + classification work together."""
        result = classifier.classify("customer CRM master data")
        matches = index.search("customer CRM master data")
        assert result.phase in ("discovery", "build")
        if matches:
            assert matches[0].workload_name == "customer_master"

    def test_all_workloads_searchable(self, index):
        """Each indexed workload can be found by its own name."""
        for name in index._documents:
            results = index.search(name.replace("_", " "))
            found = [r.workload_name for r in results]
            assert name in found, f"Workload '{name}' not found by its own name"

    def test_determinism_full_pipeline(self, index, classifier):
        """Full pipeline produces identical results on repeated calls."""
        intent = "clean and transform customer data"
        r1 = classifier.classify(intent)
        s1 = index.search(intent)
        r2 = classifier.classify(intent)
        s2 = index.search(intent)
        assert r1.phase == r2.phase
        assert r1.agent == r2.agent
        assert len(s1) == len(s2)
        for a, b in zip(s1, s2):
            assert a.workload_name == b.workload_name
            assert a.score == b.score
