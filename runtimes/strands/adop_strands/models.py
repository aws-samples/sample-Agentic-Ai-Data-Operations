"""Typed boundaries between Strands and ADOP's AgentOutput contract."""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


class AgentOutputModel(BaseModel):
    """Pydantic schema supplied to Strands structured output."""

    agent_name: str
    agent_type: str
    workload_name: str
    run_id: str
    started_at: str
    completed_at: str
    status: Literal["success", "failed", "partial"]
    artifacts: List[Dict[str, str]] = Field(default_factory=list)
    tests: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    blocking_issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    decisions: List[Dict[str, Any]] = Field(default_factory=list)
    memory_hints: List[Dict[str, str]] = Field(default_factory=list)
    input_hash: str = ""
    output_hash: str = ""


class ColumnProfile(BaseModel):
    """One column as observed in the Phase 3 sample."""

    name: str
    type: str
    null_rate: float | None = None
    distinct_count: int | None = None
    sample_values: List[str] = Field(default_factory=list)


class SourceProfileModel(BaseModel):
    """Phase 3 output: what was discovered, for the human to confirm.

    Candidates only. The human decides PK, PII, dedup and quality rules in the
    client; nothing here is applied without that confirmation.
    """

    source_format: str
    row_count: int | None = None
    columns: List[ColumnProfile] = Field(default_factory=list)
    pk_candidates: List[str] = Field(default_factory=list)
    pii_candidates: List[Dict[str, str]] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, str]] = Field(default_factory=list)
    decisions: List[Dict[str, Any]] = Field(default_factory=list)

