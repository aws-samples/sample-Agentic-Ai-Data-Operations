"""
Deterministic utilities for REIC.

Re-exports YAML helpers from shared.utils.deterministic_yaml and adds
text normalization, numerically stable softmax, and cosine similarity
(all pure-Python, no external deps).
"""

from __future__ import annotations

import math
import re

from shared.utils.deterministic_yaml import ordered_dump, ordered_load

__all__ = [
    "ordered_dump",
    "ordered_load",
    "deterministic_embed",
    "stable_softmax",
    "cosine_similarity",
]


def deterministic_embed(text: str) -> str:
    """Canonicalize text for deterministic comparison.

    Lowercases, collapses whitespace, strips punctuation, sorts tokens.
    Same logical input always produces the same output string.
    """
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = sorted(text.split())
    return " ".join(tokens)


def stable_softmax(scores: list[float], temperature: float = 1.0) -> list[float]:
    """Numerically stable softmax: subtract max before exp to avoid overflow.

    Returns a list of probabilities that sum to 1.0.
    Raises ValueError if scores is empty or temperature <= 0.
    """
    if not scores:
        raise ValueError("scores must be non-empty")
    if temperature <= 0:
        raise ValueError("temperature must be positive")

    max_score = max(scores)
    exps = [math.exp((s - max_score) / temperature) for s in scores]
    total = sum(exps)
    return [e / total for e in exps]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Pure Python, no numpy.

    Returns 0.0 if either vector has zero magnitude.
    """
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")

    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))

    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)
