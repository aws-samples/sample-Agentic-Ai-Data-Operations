"""
REIC: RAG-Enhanced Intent Classification.

Vector similarity search, constrained agent selection, and hierarchical
3-level routing (Phase -> Agent -> Action) for the data onboarding platform.
"""

from shared.reic.workload_index import WorkloadIndex, WorkloadMatch
from shared.reic.constrained_selector import (
    ConstrainedAgentSelector,
    AgentSelection,
    Scorer,
    TfIdfScorer,
)
from shared.reic.hierarchical_classifier import HierarchicalClassifier, ClassificationResult

__all__ = [
    "WorkloadIndex",
    "WorkloadMatch",
    "ConstrainedAgentSelector",
    "AgentSelection",
    "Scorer",
    "TfIdfScorer",
    "HierarchicalClassifier",
    "ClassificationResult",
]
