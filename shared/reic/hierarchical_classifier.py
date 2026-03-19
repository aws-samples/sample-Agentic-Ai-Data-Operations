"""
Hierarchical 3-level intent classifier: Phase -> Agent -> Action.

Loads agent_hierarchy.yaml and routes intents through three levels:
  Level 1: Identify the phase (discovery, validation, profiling, build, deploy)
  Level 2: Select the agent (constrained by phase, uses ConstrainedAgentSelector)
  Level 3: Match the action (intent lists from hierarchy YAML)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from shared.reic.constrained_selector import (
    AgentSelection,
    ConstrainedAgentSelector,
    TfIdfScorer,
)
from shared.reic.deterministic_utils import deterministic_embed, stable_softmax


@dataclass
class ClassificationResult:
    """Result of 3-level hierarchical classification."""
    phase: str
    phase_confidence: float
    agent: str
    agent_confidence: float
    action: str
    action_confidence: float
    tool_routing_entry: str = ""


class HierarchicalClassifier:
    """3-level intent classifier using the agent hierarchy."""

    def __init__(
        self,
        hierarchy_path: str | None = None,
        selector: ConstrainedAgentSelector | None = None,
    ):
        if hierarchy_path is None:
            hierarchy_path = str(
                Path(__file__).parent / "agent_hierarchy.yaml"
            )
        with open(hierarchy_path) as f:
            self._hierarchy = yaml.safe_load(f)

        self._phases = self._hierarchy.get("phases", {})
        self._selector = selector or self._build_default_selector()

    def _build_default_selector(self) -> ConstrainedAgentSelector:
        """Build a TfIdfScorer from the hierarchy's intent keywords."""
        agent_keywords: dict[str, list[str]] = {}
        for phase_info in self._phases.values():
            for agent_name, agent_info in phase_info.get("agents", {}).items():
                if agent_name not in agent_keywords:
                    agent_keywords[agent_name] = []
                for action_info in agent_info.get("actions", {}).values():
                    agent_keywords[agent_name].extend(
                        action_info.get("intents", [])
                    )

        scorer = TfIdfScorer(agent_keywords)
        return ConstrainedAgentSelector(scorer=scorer)

    def classify(self, intent: str) -> ClassificationResult:
        """Classify an intent through 3 levels: Phase -> Agent -> Action."""
        # Level 1: Phase
        phase, phase_confidence = self._classify_phase(intent)

        # Level 2: Agent (constrained by phase)
        agent_selection = self._selector.select(intent, phase=phase)

        # Level 3: Action (within the selected agent in the selected phase)
        action, action_confidence, tool_ref = self._classify_action(
            intent, phase, agent_selection.agent
        )

        return ClassificationResult(
            phase=phase,
            phase_confidence=round(phase_confidence, 4),
            agent=agent_selection.agent,
            agent_confidence=agent_selection.probability,
            action=action,
            action_confidence=round(action_confidence, 4),
            tool_routing_entry=tool_ref,
        )

    def _classify_phase(self, intent: str) -> tuple[str, float]:
        """Level 1: Score intent against each phase's keywords."""
        intent_norm = deterministic_embed(intent)
        intent_tokens = set(intent_norm.split())

        phase_names = sorted(self._phases.keys())
        scores = []

        for phase_name in phase_names:
            phase_info = self._phases[phase_name]
            keywords = phase_info.get("keywords", [])
            keyword_tokens = set()
            for kw in keywords:
                keyword_tokens.update(deterministic_embed(kw).split())

            if not keyword_tokens:
                scores.append(0.0)
                continue

            overlap = len(intent_tokens & keyword_tokens)
            scores.append(overlap / len(keyword_tokens) if keyword_tokens else 0.0)

        probs = stable_softmax(scores)
        best_idx = max(range(len(probs)), key=lambda i: probs[i])
        return phase_names[best_idx], probs[best_idx]

    def _classify_action(
        self, intent: str, phase: str, agent: str
    ) -> tuple[str, float, str]:
        """Level 3: Match intent against action intent lists."""
        phase_info = self._phases.get(phase, {})
        agent_info = phase_info.get("agents", {}).get(agent, {})
        actions = agent_info.get("actions", {})

        if not actions:
            return "unknown", 0.0, ""

        intent_norm = deterministic_embed(intent)
        intent_tokens = set(intent_norm.split())

        action_names = sorted(actions.keys())
        scores = []

        for action_name in action_names:
            action_info = actions[action_name]
            action_intents = action_info.get("intents", [])
            action_tokens = set()
            for ai in action_intents:
                action_tokens.update(deterministic_embed(ai).split())

            if not action_tokens:
                scores.append(0.0)
                continue

            overlap = len(intent_tokens & action_tokens)
            scores.append(overlap / len(action_tokens) if action_tokens else 0.0)

        probs = stable_softmax(scores)
        best_idx = max(range(len(probs)), key=lambda i: probs[i])
        best_action = action_names[best_idx]
        tool_ref = actions[best_action].get("tool_routing_ref", "")

        return best_action, probs[best_idx], tool_ref

    @property
    def phases(self) -> list[str]:
        return sorted(self._phases.keys())

    @property
    def hierarchy(self) -> dict:
        return self._hierarchy

    def agents_for_phase(self, phase: str) -> list[str]:
        phase_info = self._phases.get(phase, {})
        return sorted(phase_info.get("agents", {}).keys())

    def actions_for_agent(self, phase: str, agent: str) -> list[str]:
        phase_info = self._phases.get(phase, {})
        agent_info = phase_info.get("agents", {}).get(agent, {})
        return sorted(agent_info.get("actions", {}).keys())
