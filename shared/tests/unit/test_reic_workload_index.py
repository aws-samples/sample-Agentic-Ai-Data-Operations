"""Tests for shared.reic.workload_index."""

import os
import pytest
from shared.reic.workload_index import WorkloadIndex, WorkloadMatch


@pytest.fixture
def index():
    """Build an index from the real workloads/ directory."""
    idx = WorkloadIndex(workloads_dir="workloads")
    count = idx.build_index()
    assert count > 0, "Expected at least one workload to index"
    return idx


class TestWorkloadIndexBuild:
    def test_build_finds_workloads(self, index):
        assert len(index._documents) > 0

    def test_backend_is_tfidf(self, index):
        assert index.backend in ("tfidf", "faiss")

    def test_build_nonexistent_dir(self):
        idx = WorkloadIndex(workloads_dir="nonexistent_dir_xyz")
        count = idx.build_index()
        assert count == 0

    def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("REIC_ENABLED", "false")
        idx = WorkloadIndex()
        # Need to re-detect after env change
        idx._backend = idx._detect_backend()
        assert idx.backend == "disabled"
        assert idx.build_index() == 0


class TestWorkloadIndexSearch:
    def test_exact_name_match(self, index):
        results = index.search("customer master")
        assert len(results) > 0
        assert results[0].workload_name == "customer_master"

    def test_semantic_match_crm(self, index):
        results = index.search("CRM customer data")
        names = [r.workload_name for r in results]
        assert "customer_master" in names

    def test_semantic_match_sales(self, index):
        results = index.search("sales transactions revenue")
        names = [r.workload_name for r in results]
        assert any("sales" in n for n in names)

    def test_no_match_gibberish(self, index):
        results = index.search("xyzzyplugh42 nonsensetoken99")
        assert all(r.score < 0.1 for r in results)

    def test_top_k_respected(self, index):
        results = index.search("data", top_k=2)
        assert len(results) <= 2

    def test_results_are_sorted(self, index):
        results = index.search("customer")
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].score >= results[i + 1].score

    def test_match_has_source_path(self, index):
        results = index.search("customer master")
        assert results[0].source_yaml_path.endswith("source.yaml")

    def test_disabled_returns_empty(self):
        idx = WorkloadIndex()
        idx._backend = "disabled"
        assert idx.search("anything") == []


class TestWorkloadIndexDeterminism:
    def test_same_results_twice(self, index):
        r1 = index.search("order transactions")
        r2 = index.search("order transactions")
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a.workload_name == b.workload_name
            assert a.score == b.score


class TestWorkloadIndexIncremental:
    def test_add_workload(self):
        idx = WorkloadIndex(workloads_dir="workloads")
        idx.build_index()
        initial_count = len(idx._documents)
        # Re-adding existing workload should not duplicate
        idx.add_workload("customer_master")
        assert len(idx._documents) == initial_count
