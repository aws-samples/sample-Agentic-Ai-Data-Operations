"""
Data schemas for Prompt Intelligence system.

Defines pattern structures for failure analysis, success profiling,
and cross-workload learning.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib
import json


@dataclass
class FailurePattern:
    """
    Individual failure captured from trace logs.

    Represents a single failure event with error context,
    agent metadata, and linked decisions.
    """
    workload: str                    # Workload name (e.g., "customer_master")
    signature: str                   # Error signature (e.g., "KeyError: 'primary_key'")
    error_type: str                  # Error class (KeyError, AssertionError, ValidationError)
    error_message: str               # Full error message
    agent_type: str                  # "metadata" | "transformation" | "quality" | "dag"
    phase: int                       # 0-5
    timestamp: str                   # ISO 8601 timestamp
    low_confidence_decisions: List[Dict[str, Any]]  # Decisions with confidence="low" or "medium"
    context: Dict[str, Any]          # Additional context (file, line, function)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'workload': self.workload,
            'signature': self.signature,
            'error_type': self.error_type,
            'error_message': self.error_message,
            'agent_type': self.agent_type,
            'phase': self.phase,
            'timestamp': self.timestamp,
            'low_confidence_decisions': self.low_confidence_decisions,
            'context': self.context,
        }


@dataclass
class SuccessPattern:
    """
    Individual success pattern from trace logs.

    Represents high-confidence decisions from successful runs.
    """
    workload: str                    # Workload name
    agent_type: str                  # Agent that made the decision
    phase: int                       # 0-5
    decision: str                    # Decision text
    reasoning: str                   # Why this decision was made
    confidence: str                  # "high"
    timestamp: str                   # ISO 8601 timestamp
    workload_characteristics: Dict[str, Any]  # source_type, regulation, etc.

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'workload': self.workload,
            'agent_type': self.agent_type,
            'phase': self.phase,
            'decision': self.decision,
            'reasoning': self.reasoning,
            'confidence': self.confidence,
            'timestamp': self.timestamp,
            'workload_characteristics': self.workload_characteristics,
        }


@dataclass
class Correlation:
    """
    Correlation between low-confidence decisions and failures.

    Links specific decisions to error outcomes.
    """
    decision: Dict[str, Any]         # Decision that correlated with failure
    correlation_strength: float      # 0.0-1.0
    explanation: str                 # Why this decision may have caused the failure


@dataclass
class CrossWorkloadPattern:
    """
    Aggregated pattern across multiple workloads.

    Represents a recurring failure or success pattern with
    actionable recommendations.
    """
    pattern_id: str                  # Hash of signature
    pattern_type: str                # "schema_error" | "pii_false_positive" | "quality_threshold"
    signature: str                   # "KeyError: 'primary_key' in schema inference"
    frequency: int                   # Count across all workloads
    workloads_affected: List[str]    # ["customer_master", "product_inventory"]
    agent_type: str                  # "metadata" | "transformation" | "quality" | "dag"
    phase: int                       # 0-5
    recommendation: str              # Human-readable fix
    confidence: float                # Based on frequency and consistency (0.0-1.0)
    impact: str                      # "blocking" | "degraded" | "minor"
    root_cause: str                  # Analysis of why this pattern occurs
    prompt_section: str              # Which prompt section to patch (e.g., "Phase 1: Discovery")
    prompt_patch: Optional[str] = None  # Suggested text to add to prompt
    examples: List[Dict[str, Any]] = field(default_factory=list)  # Concrete examples

    @staticmethod
    def generate_pattern_id(signature: str, agent_type: str, phase: int) -> str:
        """Generate deterministic pattern ID from signature."""
        key = f"{signature}:{agent_type}:{phase}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'pattern_id': self.pattern_id,
            'pattern_type': self.pattern_type,
            'signature': self.signature,
            'frequency': self.frequency,
            'workloads_affected': self.workloads_affected,
            'agent_type': self.agent_type,
            'phase': self.phase,
            'recommendation': self.recommendation,
            'confidence': self.confidence,
            'impact': self.impact,
            'root_cause': self.root_cause,
            'prompt_section': self.prompt_section,
            'prompt_patch': self.prompt_patch,
            'examples': self.examples,
        }

    def to_markdown(self) -> str:
        """Format as markdown for report."""
        lines = [
            f"### Pattern: {self.signature}",
            f"**Type**: {self.pattern_type}",
            f"**Frequency**: {self.frequency} across {len(self.workloads_affected)} workloads",
            f"**Workloads**: {', '.join(self.workloads_affected)}",
            f"**Agent**: {self.agent_type.title()} Agent (Phase {self.phase})",
            f"**Impact**: {self.impact.upper()}",
            f"**Confidence**: {self.confidence:.2f}",
            "",
            "**Root Cause:**",
            self.root_cause,
            "",
            "**Recommendation:**",
            self.recommendation,
            "",
        ]

        if self.prompt_patch:
            lines.extend([
                f"**Prompt Section to Update**: `{self.prompt_section}`",
                "",
                "**Suggested Patch:**",
                "```markdown",
                self.prompt_patch,
                "```",
                "",
            ])

        if self.examples:
            lines.extend([
                "**Examples:**",
                "",
            ])
            for i, example in enumerate(self.examples[:3], 1):  # Show max 3 examples
                lines.append(f"{i}. Workload: `{example.get('workload', 'unknown')}`")
                lines.append(f"   Error: `{example.get('error_message', 'N/A')}`")
                lines.append("")

        return "\n".join(lines)


@dataclass
class BestPractice:
    """
    Validated best practice extracted from success patterns.

    Represents a decision pattern that consistently leads to success
    across multiple workloads.
    """
    practice_id: str                 # Hash of decision pattern
    description: str                 # What the best practice is
    agent_type: str                  # Agent that applies this practice
    phase: int                       # 0-5
    workload_types: List[str]        # Which workload types benefit (e.g., ["CSV", "Parquet"])
    frequency: int                   # How many times observed
    success_rate: float              # 0.0-1.0
    context: str                     # When to apply this practice
    example_decisions: List[str]     # Concrete decision examples

    @staticmethod
    def generate_practice_id(description: str, agent_type: str) -> str:
        """Generate deterministic practice ID."""
        key = f"{description}:{agent_type}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'practice_id': self.practice_id,
            'description': self.description,
            'agent_type': self.agent_type,
            'phase': self.phase,
            'workload_types': self.workload_types,
            'frequency': self.frequency,
            'success_rate': self.success_rate,
            'context': self.context,
            'example_decisions': self.example_decisions,
        }

    def to_markdown(self) -> str:
        """Format as markdown for report."""
        lines = [
            f"### Best Practice: {self.description}",
            f"**Agent**: {self.agent_type.title()} Agent (Phase {self.phase})",
            f"**Observed**: {self.frequency} times",
            f"**Success Rate**: {self.success_rate:.1%}",
            f"**Applies To**: {', '.join(self.workload_types)}",
            "",
            "**Context:**",
            self.context,
            "",
            "**Example Decisions:**",
        ]

        for i, decision in enumerate(self.example_decisions[:3], 1):
            lines.append(f"{i}. {decision}")

        lines.append("")
        return "\n".join(lines)


# Pattern type constants
PATTERN_TYPES = {
    'SCHEMA_ERROR': 'schema_error',
    'PII_FALSE_POSITIVE': 'pii_false_positive',
    'QUALITY_THRESHOLD': 'quality_threshold',
    'TRANSFORMATION_LOGIC': 'transformation_logic',
    'ORCHESTRATION_CONFIG': 'orchestration_config',
}

# Impact levels
IMPACT_LEVELS = {
    'BLOCKING': 'blocking',      # Test gate failure, pipeline stops
    'DEGRADED': 'degraded',      # Pipeline completes but quality/performance issues
    'MINOR': 'minor',            # Cosmetic or one-off issues
}

# Agent types
AGENT_TYPES = {
    'METADATA': 'metadata',
    'TRANSFORMATION': 'transformation',
    'QUALITY': 'quality',
    'DAG': 'dag',
    'ORCHESTRATOR': 'orchestrator',
}
