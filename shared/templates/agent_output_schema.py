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
from dataclasses import dataclass, field, fields, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


VALID_AGENT_TYPES = {"metadata", "transformation", "quality", "dag", "analysis"}
VALID_STATUSES = {"success", "failed", "partial"}


# Bedrock tool schema that forces sub-agents to return structured JSON output.
# Used with tool_choice={"tool": {"name": "submit_agent_output"}} in converse() calls.
SUBMIT_OUTPUT_TOOL = {
    "toolSpec": {
        "name": "submit_agent_output",
        "description": (
            "Submit your completed work. You MUST call this tool to finish. "
            "Do not respond in plain text — call this tool with a JSON payload."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "agent_name":      {"type": "string", "description": "Your agent name"},
                    "agent_type":      {"type": "string", "enum": ["metadata", "transformation", "quality", "dag", "analysis"]},
                    "workload_name":   {"type": "string", "description": "Workload being processed"},
                    "run_id":          {"type": "string", "description": "UUID for tracing"},
                    "started_at":      {"type": "string", "description": "ISO 8601 timestamp"},
                    "completed_at":    {"type": "string", "description": "ISO 8601 timestamp"},
                    "status":          {"type": "string", "enum": ["success", "failed", "partial"]},
                    "artifacts":       {"type": "array", "items": {"type": "object"}, "description": "List of {path, type, checksum}"},
                    "tests":           {"type": "object", "description": "{unit: {passed, failed, total}, integration: {...}}"},
                    "blocking_issues": {"type": "array", "items": {"type": "string"}, "description": "Issues that must be fixed"},
                    "warnings":        {"type": "array", "items": {"type": "string"}},
                    "next_steps":      {"type": "array", "items": {"type": "string"}},
                    "decisions":       {"type": "array", "items": {"type": "object"}, "description": "Cognitive trace decisions"},
                    "memory_hints":    {"type": "array", "items": {"type": "object"}, "description": "Durable facts to remember"},
                    "input_hash":      {"type": "string"},
                    "output_hash":     {"type": "string"},
                },
                "required": [
                    "agent_name", "agent_type", "workload_name", "run_id",
                    "started_at", "completed_at", "status", "artifacts",
                    "blocking_issues", "tests",
                ],
            }
        },
    }
}


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

    # Cognitive trace — LLM self-reported decisions (Layer 3 logging)
    # Each dict: {decision_id, category, reasoning, choice_made,
    #             alternatives_considered, rejection_reasons, confidence, context}
    decisions: List[Dict[str, Any]] = field(default_factory=list)

    # Memory hints — agent flags what is worth remembering for future runs
    memory_hints: List[Dict[str, str]] = field(default_factory=list)
    # Each hint: {"type": "user|feedback|project|reference", "content": "..."}

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
        """Deserialize from dict, filtering unknown keys for forward compatibility."""
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_json(cls, raw: str) -> "AgentOutput":
        return cls.from_dict(json.loads(raw))

    @classmethod
    def from_bedrock_tool_call(cls, tool_use_block: dict) -> "AgentOutput":
        """
        Parse AgentOutput from a Bedrock converse() toolUse response block.
        Args:
            tool_use_block: The 'toolUse' dict from a Bedrock converse() response
                            e.g. response['output']['message']['content'][0]['toolUse']

        Raises:
            ValueError: if tool name is not 'submit_agent_output'
            KeyError: if required fields are missing
        """
        if tool_use_block.get("name") != "submit_agent_output":
            raise ValueError(
                f"Expected tool 'submit_agent_output', got '{tool_use_block.get('name')}'"
            )
        return cls.from_dict(tool_use_block["input"])

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

    def add_decision(self, category: str, reasoning: str, choice: str,
                     alternatives: Optional[List[str]] = None,
                     rejection_reasons: Optional[Dict[str, str]] = None,
                     confidence: str = "high",
                     context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Add a cognitive trace decision. Returns the decision dict."""
        decision = {
            "decision_id": f"d-{len(self.decisions) + 1:03d}",
            "category": category,
            "reasoning": reasoning,
            "choice_made": choice,
            "alternatives_considered": alternatives or [],
            "rejection_reasons": rejection_reasons or {},
            "confidence": confidence,
            "context": context or {},
        }
        self.decisions.append(decision)
        return decision

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
