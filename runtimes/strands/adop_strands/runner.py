"""Strands-backed agent runner compatible with ADOP's WorkflowDriver."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from shared.orchestration.workflow_driver import AgentInvocation
from shared.templates.agent_output_schema import AgentOutput

from .definitions import DefinitionLoader
from .models import AgentOutputModel
from .tools import make_tools


class StrandsRunner:
    """Invoke ADOP agents in-process through AWS Strands."""

    def __init__(
        self,
        repo_root: Path,
        *,
        region: Optional[str] = None,
        model_map: Optional[dict[str, str]] = None,
        model_id: Optional[str] = None,
        dry_run: bool = False,
        workload: Optional[str] = None,
        run_id: Optional[str] = None,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.workload = workload
        self.run_id = run_id or str(uuid.uuid4())
        self.region = region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        self.model_map = model_map or {}
        self.model_id = model_id
        self.dry_run = dry_run
        self.definitions = DefinitionLoader(self.repo_root)

    def invoke(self, invocation: AgentInvocation) -> AgentOutput:
        if self.dry_run:
            return self._dry_output(invocation)

        try:
            from strands import Agent
            from strands.models import BedrockModel
        except ImportError as exc:
            raise RuntimeError(
                "Strands is not installed. Install with "
                "'pip install -e \".[strands]\"'."
            ) from exc

        definition = self.definitions.load(invocation.agent)
        model_id = invocation.model or self.model_id or self.model_map.get("standard")
        model = BedrockModel(
            region_name=self.region,
            **({"model_id": model_id} if model_id else {}),
        )
        agent = Agent(
            model=model,
            name=definition.name,
            description=definition.description,
            system_prompt=self.definitions.system_prompt(definition),
            tools=make_tools(
                self.repo_root,
                definition.allowed_paths,
                tuple(
                    name for name in definition.tools
                    if name in {"fs_read", "fs_write", "run_pytest_gate", "render_artifact"}
                ),
            ),
            structured_output_model=AgentOutputModel,
            trace_attributes={
                "adop.runtime": "strands",
                "adop.agent": definition.name,
            },
        )
        started_at = _now()
        result = agent(invocation.task)
        structured = result.structured_output
        if structured is None:
            raise ValueError(f"Strands agent {invocation.agent} returned no structured output")
        output = AgentOutput.from_dict(structured.model_dump())
        if not output.decisions:
            raise ValueError(f"Strands agent {invocation.agent} returned no decisions")
        return self._stamp(output, invocation, started_at)

    def _stamp(self, output: AgentOutput, invocation: AgentInvocation,
               started_at: str) -> AgentOutput:
        """Overwrite identity fields with runner-observed values; the model's are untrusted."""
        output.agent_name = invocation.agent
        output.run_id = self.run_id
        if self.workload:
            output.workload_name = self.workload
        output.started_at = started_at
        output.completed_at = _now()
        return output

    def invoke_and_write_handoff(self, invocation: AgentInvocation) -> Path:
        if not self.workload:
            raise ValueError("StrandsRunner needs a workload to write a handoff")
        output = self.invoke(invocation)
        handoff_dir = self.repo_root / "workloads" / self.workload / ".handoffs"
        handoff_dir.mkdir(parents=True, exist_ok=True)
        path = handoff_dir / f"{invocation.handoff_name}.json"
        path.write_text(output.to_json(), encoding="utf-8")
        return path

    def _dry_output(self, invocation: AgentInvocation) -> AgentOutput:
        now = _now()
        return AgentOutput(
            agent_name=invocation.agent,
            agent_type="analysis",
            workload_name=self.workload or "dryrun",
            run_id=self.run_id,
            started_at=now,
            completed_at=now,
            status="success",
            tests={"unit": {"passed": 1, "failed": 0, "total": 1}},
            decisions=[{
                "decision_id": "d-001",
                "category": "runtime",
                "reasoning": "Dry-run execution used the Strands backend contract.",
                "choice_made": "return_valid_agent_output",
                "alternatives_considered": [],
                "rejection_reasons": {},
                "confidence": "high",
                "context": {"agent": invocation.agent},
            }],
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
