"""
Enforced output schema for ALL sub-agent responses.

Every sub-agent (Metadata, Transformation, Quality, DAG) MUST return
an AgentOutput instance. The orchestrator parses this to decide:
- Whether to proceed to the next phase
- Whether to retry the current phase
- Whether to escalate to the human

Two return paths, same schema:
- **Claude Code sub-agents** (spawned via the `Agent` tool) have no tool-call channel.
  They end their final message with a fenced ```json block — parse with
  `AgentOutput.from_agent_message(text)`.
- **Bedrock `converse()`** callers force a tool call with SUBMIT_OUTPUT_TOOL and
  `tool_choice` — parse with `AgentOutput.from_bedrock_tool_call(block)`.

Required fields are declared once in SUBMIT_OUTPUT_TOOL and reused by both paths via
REQUIRED_OUTPUT_FIELDS, so the two cannot drift.

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
import re
from dataclasses import dataclass, field, fields, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


VALID_AGENT_TYPES = {"metadata", "transformation", "quality", "dag", "analysis", "devops"}
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
                    "agent_type":      {"type": "string", "enum": ["metadata", "transformation", "quality", "dag", "analysis", "devops"]},
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
                    "decisions":       {"type": "array", "items": {"type": "object"}, "minItems": 1, "description": "Cognitive trace decisions — at least one. This is the cognitive surface of the trace; an empty array means the run has no recorded reasoning."},
                    "memory_hints":    {"type": "array", "items": {"type": "object"}, "description": "Durable facts to remember"},
                    "input_hash":      {"type": "string"},
                    "output_hash":     {"type": "string"},
                },
                "required": [
                    "agent_name", "agent_type", "workload_name", "run_id",
                    "started_at", "completed_at", "status", "artifacts",
                    "blocking_issues", "tests", "decisions",
                ],
            }
        },
    }
}


# Required fields, derived from SUBMIT_OUTPUT_TOOL so the Bedrock tool-call path and
# the Claude Code message path can never drift apart.
REQUIRED_OUTPUT_FIELDS = frozenset(
    SUBMIT_OUTPUT_TOOL["toolSpec"]["inputSchema"]["json"]["required"]
)


# Matches a fenced code block, with or without a `json` language tag.
_JSON_FENCE_RE = re.compile(r"```(?:json|JSON)?[ \t]*\r?\n?(.*?)```", re.DOTALL)


def _match_brace(text: str, start: int) -> Optional[int]:
    """Index of the `}` closing the `{` at `start`, or None if unbalanced.

    String-aware, so braces inside JSON string literals do not affect depth.
    """
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _scan_last_json_object(text: str) -> Optional[dict]:
    """Last top-level brace-balanced JSON object in raw text.

    Walks forward and skips past each object it parses, so nested objects are
    never mistaken for the payload.
    """
    last = None
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        end = _match_brace(text, i)
        if end is None:
            i += 1
            continue
        try:
            parsed = json.loads(text[i : end + 1])
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(parsed, dict):
            last = parsed
            i = end + 1
        else:
            i += 1
    return last


def extract_output_payload(text: str) -> Optional[dict]:
    """Pull the AgentOutput JSON object out of a sub-agent's final message.

    Prefers fenced ```json blocks (last one wins, so an agent that shows an
    intermediate example still parses); falls back to scanning raw braces.
    """
    for raw in reversed(_JSON_FENCE_RE.findall(text or "")):
        try:
            parsed = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return _scan_last_json_object(text or "")


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

    @classmethod
    def from_agent_message(cls, text: str) -> "AgentOutput":
        """
        Parse AgentOutput from a Claude Code sub-agent's final message.

        Sub-agents spawned via the `Agent` tool have no `submit_agent_output` tool —
        that is the Bedrock `converse()` path (see SUBMIT_OUTPUT_TOOL). They end their
        final message with a fenced ```json block instead, which this parses.

        Args:
            text: The sub-agent's final message, prose and all.

        Raises:
            ValueError: if no JSON object is present, or required fields are missing.
        """
        payload = extract_output_payload(text)
        if payload is None:
            raise ValueError(
                "No JSON object found in sub-agent message. Sub-agents must end their "
                "final message with a fenced ```json block conforming to AgentOutput."
            )
        missing = sorted(REQUIRED_OUTPUT_FIELDS - payload.keys())
        if missing:
            raise ValueError(
                f"AgentOutput missing required field(s): {', '.join(missing)}"
            )
        # `decisions` present but empty is the same failure as absent: rules/07 makes the
        # cognitive surface mandatory, and an empty array records no reasoning at all.
        if not payload.get("decisions"):
            raise ValueError(
                "AgentOutput.decisions is empty. Every sub-agent must record at least one "
                "decision (choice_made + reasoning) — see .claude/rules/07-error-logging.md."
            )
        return cls.from_dict(payload)

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
