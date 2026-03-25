"""
Constrained agent selection with probability-based ranking.

Implements REIC Equations 4-5:
  P(agent | intent, phase) = softmax(scores) over constrained agent set

Three scorer backends:
  - TfIdfScorer: always available (stdlib only)
  - EmbeddingScorer: optional (sentence-transformers)
  - ExternalScorer: wraps any callable (for LLM integration)
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, runtime_checkable

from shared.reic.deterministic_utils import deterministic_embed, stable_softmax


@dataclass
class AgentSelection:
    """Result of constrained agent selection."""
    agent: str
    probability: float
    all_probabilities: dict[str, float] = field(default_factory=dict)
    constrained_set: list[str] = field(default_factory=list)


@runtime_checkable
class Scorer(Protocol):
    """Protocol for scoring intent-agent similarity."""
    def score(self, intent: str, candidates: list[str]) -> list[float]: ...


class TfIdfScorer:
    """TF-IDF based scorer using keyword overlap. No external deps."""

    def __init__(self, agent_keywords: dict[str, list[str]] | None = None):
        self._agent_keywords = agent_keywords or {}

    def set_keywords(self, agent_keywords: dict[str, list[str]]) -> None:
        self._agent_keywords = agent_keywords

    def score(self, intent: str, candidates: list[str]) -> list[float]:
        intent_norm = deterministic_embed(intent)
        intent_tokens = set(intent_norm.split())
        scores = []
        for agent in candidates:
            keywords = self._agent_keywords.get(agent, [])
            keyword_tokens = set()
            for kw in keywords:
                keyword_tokens.update(deterministic_embed(kw).split())
            if not keyword_tokens:
                scores.append(0.0)
                continue
            overlap = len(intent_tokens & keyword_tokens)
            score = overlap / math.sqrt(len(intent_tokens) * len(keyword_tokens)) if keyword_tokens else 0.0
            scores.append(score)
        return scores


class EmbeddingScorer:
    """Scorer using sentence-transformers embeddings. Optional dependency."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name)
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for EmbeddingScorer. "
                "Install with: pip install sentence-transformers"
            )

    def score(self, intent: str, candidates: list[str]) -> list[float]:
        from shared.reic.deterministic_utils import cosine_similarity
        intent_emb = self._model.encode(intent).tolist()
        scores = []
        for agent in candidates:
            agent_emb = self._model.encode(agent).tolist()
            scores.append(cosine_similarity(intent_emb, agent_emb))
        return scores


class ExternalScorer:
    """Wraps any callable as a Scorer (for LLM integration)."""

    def __init__(self, fn: Callable[[str, list[str]], list[float]]):
        self._fn = fn

    def score(self, intent: str, candidates: list[str]) -> list[float]:
        return self._fn(intent, candidates)


class ConstrainedAgentSelector:
    """Select an agent with probability-based ranking, constrained by phase.

    Implements REIC Equations 4-5:
      raw_scores = scorer.score(intent, valid_agents)
      P(agent | intent, phase) = softmax(raw_scores / temperature)
    """

    # Phase -> valid agents mapping
    PHASE_CONSTRAINTS: dict[str, list[str]] = {
        "discovery": ["router", "data_onboarding"],
        "validation": ["data_onboarding"],
        "profiling": ["metadata"],
        "build": ["metadata", "transformation", "quality", "dag"],
        "deploy": ["data_onboarding"],
    }

    ALL_AGENTS = [
        "router",
        "data_onboarding",
        "metadata",
        "transformation",
        "quality",
        "dag",
    ]

    def __init__(self, scorer: Scorer | None = None, temperature: float = 1.0):
        self._scorer = scorer or TfIdfScorer()
        self._temperature = temperature

    @property
    def scorer(self) -> Scorer:
        return self._scorer

    def select(
        self, intent: str, phase: str | None = None
    ) -> AgentSelection:
        """Select the best agent for the given intent, optionally constrained by phase.

        Args:
            intent: Natural language description of what the user wants.
            phase: If provided, constrains valid agents to this phase.

        Returns:
            AgentSelection with the top agent, its probability, and the full distribution.

        Raises:
            ValueError: If phase is invalid or constrained set is empty.
        """
        if phase is not None:
            if phase not in self.PHASE_CONSTRAINTS:
                raise ValueError(
                    f"Unknown phase '{phase}'. Valid: {list(self.PHASE_CONSTRAINTS)}"
                )
            candidates = self.PHASE_CONSTRAINTS[phase]
        else:
            candidates = self.ALL_AGENTS

        if not candidates:
            raise ValueError("Constrained agent set is empty")

        raw_scores = self._scorer.score(intent, candidates)
        probabilities = stable_softmax(raw_scores, self._temperature)

        prob_map = dict(zip(candidates, probabilities))
        best_idx = max(range(len(probabilities)), key=lambda i: probabilities[i])

        return AgentSelection(
            agent=candidates[best_idx],
            probability=round(probabilities[best_idx], 4),
            all_probabilities={k: round(v, 4) for k, v in prob_map.items()},
            constrained_set=list(candidates),
        )
