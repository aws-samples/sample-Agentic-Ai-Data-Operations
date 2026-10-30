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
from .models import AgentOutputModel, SourceProfileModel
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

        from .cedar_hook import CedarToolGate

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
            # Same Cedar policies as Claude Code, Codex and Kiro (shared/policies/).
            hooks=[CedarToolGate(self.repo_root, invocation.agent)],
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

    def profile(
        self,
        source: dict[str, Any],
        *,
        athena_output: Optional[str] = None,
        athena_workgroup: Optional[str] = None,
        client_factory: Any = None,
    ) -> dict[str, Any]:
        """Phase 3: profile the source with read-only AWS tools; return candidates.

        Runs as the metadata principal (Cedar permits it the aws_ro_* tools and
        nothing else on AWS). The result is written to
        workloads/{name}/run/source_profile.json by this runner, not by the
        model, and contains candidates only: the human confirms PK, PII, dedup
        and quality rules in the client before anything is generated.
        """
        if self.dry_run:
            result = SourceProfileModel(source_format="dry-run", decisions=[{
                "decision_id": "p-001", "category": "runtime",
                "reasoning": "Dry-run: no AWS or Bedrock calls were made.",
                "choice_made": "return_valid_profile", "confidence": "high"}]).model_dump()
        else:
            from strands import Agent
            from strands.models import BedrockModel

            from .aws_readonly import make_readonly_aws_tools
            from .cedar_hook import CedarToolGate

            definition = self.definitions.load("adop-build-metadata")
            model_id = self.model_id or self.model_map.get("standard")
            agent = Agent(
                model=BedrockModel(region_name=self.region,
                                   **({"model_id": model_id} if model_id else {})),
                name="adop-build-metadata",
                description="Phase 3 source profiler (read-only)",
                system_prompt=self.definitions.system_prompt(definition),
                tools=[
                    *make_tools(self.repo_root, (), ("fs_read",)),
                    *make_readonly_aws_tools(self.region or "", athena_output,
                                             athena_workgroup, client_factory),
                ],
                structured_output_model=SourceProfileModel,
                hooks=[CedarToolGate(self.repo_root, "adop-build-metadata")],
                trace_attributes={"adop.runtime": "strands", "adop.agent": "adop-build-metadata",
                                  "adop.phase": "3"},
            )
            task = (
                "Phase 3 profiling. Read-only: use only the aws_ro_* tools.\n"
                f"Source (human-provided): {json.dumps(source, sort_keys=True)}\n"
                "1. Find the schema (Glue table if catalogued, otherwise sample the S3 objects).\n"
                "2. Profile with row-capped SELECTs: row count, null rate and distinct count per column.\n"
                "3. List PK candidates (unique and non-null) and PII candidates with the evidence.\n"
                "4. Record risks you see. Do NOT decide PK, PII handling, dedup or thresholds; "
                "those are the human's decisions. Report candidates only."
            )
            structured = agent(task).structured_output
            if structured is None:
                raise ValueError("profiler returned no structured output")
            result = structured.model_dump()
        record = {
            "phase": "3", "runtime": "strands", "run_id": self.run_id,
            "workload_name": self.workload, "profiled_at": _now(),
            "dry_run": self.dry_run, "status": "candidates_pending_human_confirmation",
            "profile": result,
        }
        if self.workload:
            out = self.repo_root / "workloads" / self.workload / "run" / "source_profile.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return record

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
