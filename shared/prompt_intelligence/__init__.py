"""
Prompt Intelligence: Self-healing prompt architecture

Analyzes trace logs to extract failure/success patterns across workloads
and generates actionable recommendations for prompt improvements.
"""

from .schemas import (
    FailurePattern,
    SuccessPattern,
    CrossWorkloadPattern,
    BestPractice,
    Correlation
)

__all__ = [
    'FailurePattern',
    'SuccessPattern',
    'CrossWorkloadPattern',
    'BestPractice',
    'Correlation',
]
