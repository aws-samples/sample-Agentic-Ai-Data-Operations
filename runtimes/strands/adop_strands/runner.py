"""Strands-backed agent runner compatible with ADOP's WorkflowDriver."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from shared.orchestration.workflow_driver import AgentInvocation
from shared.templates.agent_output_schema import AgentOutput
from shared.utils.cost_attribution import (
    CostAttribution,
    CostAttributionError,
    append_usage_event,
)

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
        self.cost_attribution = self._load_cost_attribution()

    def _load_cost_attribution(self) -> Optional[CostAttribution]:
        if not self.workload:
            return None
        path = self.repo_root / "workloads" / self.workload / "config" / "cost_attribution.yaml"
        if not path.is_file():
            if not self.dry_run:
                raise RuntimeError(
                    f"missing Bedrock cost attribution config: {path}. "
                    "Record human-approved project, environment, cost center, owner, "
                    "and an Application Inference Profile before live Bedrock execution."
                )
            return None
        try:
            return CostAttribution.from_file(path, require_bedrock_profile=not self.dry_run)
        except CostAttributionError as exc:
            raise RuntimeError(f"invalid cost attribution config: {path}: {exc}") from exc

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
        model_id = self._model_id_for_agent(
            invocation.agent,
            invocation.model or self.model_id or self.model_map.get("standard"),
        )
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
            trace_attributes=self._trace_attributes(definition.name),
        )
        started_at = _now()
        result = agent(invocation.task)
        self._record_result_usage(
            result,
            agent_name=invocation.agent,
            model_id=model_id or "",
            phase=None,
        )
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
            model_id = self._model_id_for_agent(
                "adop-build-metadata",
                self.model_id or self.model_map.get("standard"),
            )
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
                trace_attributes=self._trace_attributes("adop-build-metadata", phase=3),
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
            profile_result = agent(task)
            structured = profile_result.structured_output
            self._record_result_usage(
                profile_result,
                agent_name="adop-build-metadata",
                model_id=model_id or "",
                phase=3,
            )
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

    def _model_id_for_agent(self, agent_name: str, fallback: Optional[str]) -> Optional[str]:
        """Prefer the human-approved project/agent inference profile when present."""
        if self.cost_attribution:
            profile = self.cost_attribution.profile_for_agent(agent_name)
            if profile:
                return profile
        return fallback

    def _trace_attributes(self, agent_name: str, phase: int | str | None = None) -> dict[str, Any]:
        """Return low-cardinality ADOP dimensions for Strands traces."""
        attributes: dict[str, Any] = {
            "adop.runtime": "strands",
            "adop.agent": agent_name,
        }
        if phase is not None:
            attributes["adop.phase"] = str(phase)
        if self.cost_attribution:
            dimensions = self.cost_attribution.dimensions(
                workload=self.workload or "",
                run_id=self.run_id,
                agent=agent_name,
                phase=phase,
            )
            attributes.update(
                {
                    "adop.project": dimensions["project"],
                    "adop.environment": dimensions["environment"],
                    "adop.cost_center": dimensions["cost_center"],
                    "adop.owner": dimensions["owner"],
                    "adop.inference_profile_arn": dimensions[
                        "bedrock_inference_profile_arn"
                    ],
                }
            )
        return attributes

    def _record_result_usage(
        self,
        result: Any,
        *,
        agent_name: str,
        model_id: str,
        phase: int | str | None,
    ) -> None:
        """Best-effort extraction across Strands versions.

        Usage is recorded only when the model response exposes it and a
        human-approved cost attribution contract exists. Missing metrics must
        not turn a successful build into a failure.
        """
        if not self.cost_attribution or self.dry_run or result is None or not self.workload:
            return
        candidates = [
            getattr(result, "metrics", None),
            getattr(result, "usage", None),
        ]
        usage: Optional[dict[str, Any]] = None
        request_id = ""
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            request_id = str(
                candidate.get("request_id")
                or candidate.get("requestId")
                or candidate.get("invocation_id")
                or ""
            )
            for key in ("usage", "accumulated_usage", "token_usage", "tokens"):
                nested = candidate.get(key)
                if isinstance(nested, Mapping):
                    usage = dict(nested)
                    break
            if usage is None and any(
                key in candidate
                for key in (
                    "inputTokens",
                    "outputTokens",
                    "input_tokens",
                    "output_tokens",
                    "prompt_tokens",
                    "completion_tokens",
                )
            ):
                usage = dict(candidate)
            if usage:
                break
        if not usage:
            return
        append_usage_event(
            self.repo_root / "workloads" / self.workload / "run",
            attribution=self.cost_attribution,
            workload=self.workload,
            run_id=self.run_id,
            agent=agent_name,
            phase=phase,
            usage=usage,
            provider="bedrock",
            model_id=model_id,
            request_id=request_id,
            source="strands",
        )

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
