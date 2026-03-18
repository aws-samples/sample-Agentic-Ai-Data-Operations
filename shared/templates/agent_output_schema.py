"""
Enforced output schema for ALL sub-agent responses.

Every sub-agent (Metadata, Transformation, Quality, DAG) MUST return
an AgentOutput instance. The orchestrator parses this to decide:
- Whether to proceed to the next phase
- Whether to retry the current phase
- Whether to escalate to the human

Usage:
    from shared.templates.agent_output_schema import AgentOutput

    output = AgentOutput(
        agent_name="Metadata Agent",
        agent_type="metadata",
        workload_name="customer_master",
        run_id="abc123",
        started_at="2026-03-18T10:00:00Z",
        completed_at="2026-03-18T10:05:00Z",
        status="success",
        artifacts=[{"path": "config/source.yaml", "type": "config", "checksum": "def456..."}],
        tests={"unit": {"passed": 43, "failed": 0, "total": 43}},
        blocking_issues=[],
        warnings=["fund_name flagged as PII — likely false positive"],
        next_steps=["Proceed to Transformation Agent"],
        input_hash="abc123...",
        output_hash="def456...",
    )
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List


VALID_AGENT_TYPES = {"metadata", "transformation", "quality", "dag", "analysis"}
VALID_STATUSES = {"success", "failed", "partial"}


@dataclass
class AgentOutput:
    """Enforced schema for ALL sub-agent responses."""

    agent_name: str
    agent_type: str  # metadata | transformation | quality | dag | analysis
    workload_name: str
    run_id: str  # UUID for tracing
    started_at: str
    completed_at: str
    status: str  # success | failed | partial

    # Artifacts produced
    artifacts: List[Dict[str, str]] = field(default_factory=list)
    # [{path: str, type: str, checksum: str}]

    # Test results
    tests: Dict[str, Dict] = field(default_factory=dict)
    # {"unit": {passed: int, failed: int, total: int}, "integration": {...}}

    # For orchestrator decision-making
    blocking_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)

    # Determinism
    input_hash: str = ""  # SHA-256 of inputs
    output_hash: str = ""  # SHA-256 of all artifacts

    def __post_init__(self):
        if self.agent_type not in VALID_AGENT_TYPES:
            raise ValueError(
                f"agent_type must be one of {VALID_AGENT_TYPES}, got '{self.agent_type}'"
            )
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"status must be one of {VALID_STATUSES}, got '{self.status}'"
            )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentOutput":
        return cls(**data)

    @classmethod
    def from_json(cls, raw: str) -> "AgentOutput":
        return cls.from_dict(json.loads(raw))

    # ------------------------------------------------------------------
    # Orchestrator decision helpers
    # ------------------------------------------------------------------

    @property
    def can_proceed(self) -> bool:
        """Orchestrator calls this to decide whether to advance."""
        return self.status == "success" and len(self.blocking_issues) == 0

    @property
    def needs_retry(self) -> bool:
        return self.status == "failed" and len(self.blocking_issues) > 0

    @property
    def total_tests_passed(self) -> int:
        return sum(phase.get("passed", 0) for phase in self.tests.values())

    @property
    def total_tests_failed(self) -> int:
        return sum(phase.get("failed", 0) for phase in self.tests.values())

    @property
    def total_tests(self) -> int:
        return sum(phase.get("total", 0) for phase in self.tests.values())

    # ------------------------------------------------------------------
    # Display helpers (for console output)
    # ------------------------------------------------------------------

    @staticmethod
    def header(agent_name: str, workload: str, run_id: str) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return (
            "\n"
            "================================================================\n"
            f"  AGENT: {agent_name}\n"
            f"  WORKLOAD: {workload}\n"
            f"  RUN_ID: {run_id}\n"
            f"  STARTED: {now}\n"
            "================================================================\n"
        )

    def footer(self) -> str:
        icon = "PASS" if self.status == "success" else "FAIL"
        return (
            "\n"
            "----------------------------------------------------------------\n"
            f"  STATUS: {icon} ({self.status})\n"
            f"  TESTS: {self.total_tests_passed} passed, {self.total_tests_failed} failed\n"
            f"  ARTIFACTS: {len(self.artifacts)}\n"
            f"  BLOCKING: {len(self.blocking_issues)}\n"
            "----------------------------------------------------------------\n"
        )


# ------------------------------------------------------------------
# Hashing utilities for determinism
# ------------------------------------------------------------------


def compute_input_hash(inputs: dict) -> str:
    """Compute SHA-256 of all inputs for reproducibility."""
    raw = json.dumps(inputs, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def compute_file_checksum(filepath: str) -> str:
    """Compute SHA-256 of a file's contents."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
