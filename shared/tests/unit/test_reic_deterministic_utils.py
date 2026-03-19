"""Tests for shared.reic.deterministic_utils."""

import math
import pytest
from shared.reic.deterministic_utils import (
    cosine_similarity,
    deterministic_embed,
    stable_softmax,
)


class TestDeterministicEmbed:
    def test_idempotent(self):
        text = "Clean the Sales Data!"
        assert deterministic_embed(text) == deterministic_embed(text)

    def test_order_independent(self):
        assert deterministic_embed("sales data clean") == deterministic_embed("clean data sales")

    def test_case_insensitive(self):
        assert deterministic_embed("CRM Data") == deterministic_embed("crm data")

    def test_strips_punctuation(self):
        assert deterministic_embed("hello, world!") == deterministic_embed("hello world")

    def test_collapses_whitespace(self):
        assert deterministic_embed("a   b\t\tc") == deterministic_embed("a b c")

    def test_empty_string(self):
        assert deterministic_embed("") == ""


class TestStableSoftmax:
    def test_sums_to_one(self):
        probs = stable_softmax([1.0, 2.0, 3.0])
        assert abs(sum(probs) - 1.0) < 1e-9

    def test_no_nan_or_inf(self):
        probs = stable_softmax([1000.0, 1001.0, 999.0])
        assert all(math.isfinite(p) for p in probs)

    def test_large_negative_scores(self):
        probs = stable_softmax([-1000.0, -999.0, -1001.0])
        assert all(math.isfinite(p) for p in probs)
        assert abs(sum(probs) - 1.0) < 1e-9

    def test_equal_scores(self):
        probs = stable_softmax([1.0, 1.0, 1.0])
        for p in probs:
            assert abs(p - 1 / 3) < 1e-9

    def test_temperature(self):
        hot = stable_softmax([1.0, 2.0], temperature=10.0)
        cold = stable_softmax([1.0, 2.0], temperature=0.1)
        assert abs(hot[0] - hot[1]) < abs(cold[0] - cold[1])

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            stable_softmax([])

    def test_zero_temperature_raises(self):
        with pytest.raises(ValueError):
            stable_softmax([1.0], temperature=0.0)


class TestCosineSimilarity:
    def test_self_similarity(self):
        v = [1.0, 2.0, 3.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-9

    def test_orthogonal(self):
        assert abs(cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-9

    def test_opposite(self):
        assert abs(cosine_similarity([1.0, 0.0], [-1.0, 0.0]) + 1.0) < 1e-9

    def test_zero_vector(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            cosine_similarity([1.0], [1.0, 2.0])
