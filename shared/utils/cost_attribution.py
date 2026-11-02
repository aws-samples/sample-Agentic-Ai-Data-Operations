"""ADOP cost attribution and Bedrock usage accounting.

This module keeps billing dimensions separate from pricing. AWS Cost Explorer
and CUR remain the source of billed dollars; ADOP records the project,
workload, agent, run, phase, token usage, and inference profile needed to
reconcile those bills.

The workload contract is human-provided. No project, environment, cost center,
owner, or Bedrock profile is inferred from a workload name or the current
caller.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import yaml


_ENV_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_PROJECT = re.compile(r"^[a-z][a-z0-9_-]{1,60}$")
_ENVIRONMENT = re.compile(r"^[a-z][a-z0-9_-]{1,30}$")
_TAG_KEY = re.compile(r"^[A-Za-z0-9_.:/=+@-]{1,128}$")

CONFIG_NAME = "cost_attribution.yaml"
EVENTS_NAME = "cost_events.jsonl"


class CostAttributionError(ValueError):
    """Raised when required human-approved billing metadata is missing."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_env_ref(value: Any, *, field_name: str) -> Any:
    if not isinstance(value, str):
        return value
    match = _ENV_REF.fullmatch(value.strip())
    if not match:
        return value
    resolved = os.environ.get(match.group(1))
    if not resolved:
        raise CostAttributionError(
            f"{field_name} references {value}, but {match.group(1)} is not set"
        )
    return resolved


def _clean_mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise CostAttributionError(f"{field_name} must be an object")
    return {str(k): _resolve_env_ref(v, field_name=f"{field_name}.{k}") for k, v in value.items()}


@dataclass(frozen=True)
class CostAttribution:
    """Human-approved billing dimensions for one workload."""

    project: str
    environment: str
    cost_center: str
    owner: str
    bedrock_inference_profile_arn: Optional[str] = None
    agent_inference_profiles: Mapping[str, str] = field(default_factory=dict)
    tags: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        require_bedrock_profile: bool = False,
    ) -> "CostAttribution":
        if not isinstance(value, Mapping):
            raise CostAttributionError("cost attribution must be an object")

        required = ("project", "environment", "cost_center", "owner")
        missing = [key for key in required if not str(value.get(key, "")).strip()]
        if missing:
            raise CostAttributionError(
                "missing human-approved cost attribution fields: " + ", ".join(missing)
            )

        project = str(value["project"]).strip()
        environment = str(value["environment"]).strip()
        cost_center = str(value["cost_center"]).strip()
        owner = str(value["owner"]).strip()
        if not _PROJECT.fullmatch(project):
            raise CostAttributionError("project must match ^[a-z][a-z0-9_-]{1,60}$")
        if not _ENVIRONMENT.fullmatch(environment):
            raise CostAttributionError("environment must match ^[a-z][a-z0-9_-]{1,30}$")
        if len(cost_center) > 128 or len(owner) > 256:
            raise CostAttributionError("cost_center or owner exceeds its maximum length")

        profile = _resolve_env_ref(
            value.get("bedrock_inference_profile_arn"),
            field_name="bedrock_inference_profile_arn",
        )
        agent_profiles = _clean_mapping(
            value.get("agent_inference_profiles"),
            field_name="agent_inference_profiles",
        )
        tags = _clean_mapping(value.get("tags"), field_name="tags")
        if profile is not None and not str(profile).strip():
            profile = None
        if require_bedrock_profile and not profile and not agent_profiles:
            raise CostAttributionError(
                "a Bedrock inference profile is required for billed project attribution"
            )

        for agent, agent_profile in agent_profiles.items():
            if not str(agent).strip() or not str(agent_profile).strip():
                raise CostAttributionError("agent_inference_profiles cannot contain empty values")
        for key, tag_value in tags.items():
            if not _TAG_KEY.fullmatch(key):
                raise CostAttributionError(f"invalid AWS tag key: {key!r}")
            if len(str(tag_value)) > 256:
                raise CostAttributionError(f"AWS tag value is too long: {key!r}")

        return cls(
            project=project,
            environment=environment,
            cost_center=cost_center,
            owner=owner,
            bedrock_inference_profile_arn=str(profile) if profile else None,
            agent_inference_profiles={
                str(k): str(v) for k, v in agent_profiles.items()
            },
            tags={str(k): str(v) for k, v in tags.items()},
        )

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        require_bedrock_profile: bool = False,
    ) -> "CostAttribution":
        source = Path(path)
        try:
            value = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        except FileNotFoundError as exc:
            raise CostAttributionError(f"missing cost attribution config: {source}") from exc
        except yaml.YAMLError as exc:
            raise CostAttributionError(f"invalid cost attribution YAML: {source}: {exc}") from exc
        return cls.from_dict(value, require_bedrock_profile=require_bedrock_profile)

    @classmethod
    def from_workload(
        cls,
        workload_dir: str | Path,
        *,
        require_bedrock_profile: bool = False,
    ) -> "CostAttribution":
        return cls.from_file(
            Path(workload_dir) / "config" / CONFIG_NAME,
            require_bedrock_profile=require_bedrock_profile,
        )

    def profile_for_agent(self, agent_name: str = "") -> Optional[str]:
        return (
            self.agent_inference_profiles.get(agent_name)
            or self.agent_inference_profiles.get(agent_name.lower())
            or self.bedrock_inference_profile_arn
        )

    def dimensions(
        self,
        *,
        workload: str,
        run_id: str = "",
        agent: str = "",
        phase: int | str | None = None,
    ) -> dict[str, Any]:
        """Return dimensions safe for JSONL, OTel, and CloudWatch fields."""
        return {
            "project": self.project,
            "environment": self.environment,
            "cost_center": self.cost_center,
            "owner": self.owner,
            "workload": workload,
            "run_id": run_id,
            "agent": agent,
            "phase": phase,
            "bedrock_inference_profile_arn": self.profile_for_agent(agent),
        }

    def resource_tags(self, *, workload: str, agent: str = "") -> dict[str, str]:
        """Return AWS resource tags; reserved ``aws:`` keys are never generated."""
        tags = {
            "adop:project": self.project,
            "adop:environment": self.environment,
            "adop:cost-center": self.cost_center,
            "adop:owner": self.owner,
            "adop:workload": workload,
        }
        if agent:
            tags["adop:agent"] = agent
        tags.update(self.tags)
        return {key: value for key, value in tags.items() if not key.lower().startswith("aws:")}

    def request_metadata(
        self,
        *,
        workload: str,
        run_id: str,
        agent: str,
        phase: int | str | None = None,
    ) -> dict[str, str]:
        """Return low-cardinality Bedrock request metadata for invocation logs."""
        dimensions = self.dimensions(
            workload=workload, run_id=run_id, agent=agent, phase=phase
        )
        return {
            "adop_project": str(dimensions["project"]),
            "adop_environment": str(dimensions["environment"]),
            "adop_workload": str(workload),
            "adop_run_id": str(run_id),
            "adop_agent": str(agent),
            "adop_phase": "" if phase is None else str(phase),
        }


def optional_dimensions_for_workload(
    workload_dir: str | Path,
    *,
    workload: str = "",
    run_id: str = "",
    agent: str = "",
    phase: int | str | None = None,
) -> dict[str, Any]:
    """Load dimensions for hooks without making a missing config a hard failure."""
    path = Path(workload_dir) / "config" / CONFIG_NAME
    if not path.is_file():
        return {}
    try:
        attribution = CostAttribution.from_file(path)
    except CostAttributionError as exc:
        return {"cost_attribution_error": str(exc)}
    return attribution.dimensions(
        workload=workload or Path(workload_dir).name,
        run_id=run_id,
        agent=agent,
        phase=phase,
    )


def _usage_value(usage: Mapping[str, Any], *names: str) -> int:
    for name in names:
        value = usage.get(name)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
    return 0


def append_usage_event(
    run_dir: str | Path,
    *,
    attribution: CostAttribution,
    workload: str,
    run_id: str,
    agent: str,
    phase: int | str | None,
    usage: Mapping[str, Any],
    provider: str = "bedrock",
    model_id: str = "",
    request_id: str = "",
    source: str = "runtime",
    estimated_cost_usd: float | None = None,
) -> dict[str, Any]:
    """Append one model-usage event and return the persisted record."""
    input_tokens = _usage_value(usage, "inputTokens", "input_tokens", "prompt_tokens")
    output_tokens = _usage_value(usage, "outputTokens", "output_tokens", "completion_tokens")
    total_tokens = _usage_value(usage, "totalTokens", "total_tokens")
    if not total_tokens:
        total_tokens = input_tokens + output_tokens
    record = {
        "record_type": "model_usage",
        "timestamp": _now(),
        "provider": provider,
        "model_id": model_id,
        "request_id": request_id,
        "source": source,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "inference_profile_arn": attribution.profile_for_agent(agent),
        **attribution.dimensions(
            workload=workload, run_id=run_id, agent=agent, phase=phase
        ),
    }
    path = Path(run_dir) / EVENTS_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    return record


def _find_usage(value: Any) -> tuple[dict[str, Any], str, str] | None:
    """Find a provider usage object in a hook/client event.

    Claude Code, Codex, Kiro, and Strands expose usage under different
    nesting shapes. This keeps the adapter hooks thin and only records an
    event when a payload actually contains token counters.
    """
    if isinstance(value, Mapping):
        for key in ("usage", "metrics", "model_usage", "token_usage", "usage_metadata"):
            nested = value.get(key)
            if isinstance(nested, Mapping):
                found = _find_usage(nested)
                if found:
                    return found
        token_keys = {
            "inputTokens",
            "outputTokens",
            "totalTokens",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "prompt_tokens",
            "completion_tokens",
        }
        if token_keys.intersection(value):
            return (
                dict(value),
                str(value.get("request_id") or value.get("requestId") or ""),
                str(value.get("model_id") or value.get("modelId") or value.get("model") or ""),
            )
        for nested in value.values():
            found = _find_usage(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_usage(nested)
            if found:
                return found
    return None


def append_usage_event_from_payload(
    run_dir: str | Path,
    *,
    attribution: CostAttribution,
    workload: str,
    run_id: str,
    agent: str,
    phase: int | str | None,
    payload: Any,
    provider: str = "bedrock",
    source: str = "client_hook",
) -> dict[str, Any] | None:
    """Record usage when a Claude/Codex/Kiro hook receives token metadata."""
    found = _find_usage(payload)
    if not found:
        return None
    usage, request_id, model_id = found
    return append_usage_event(
        run_dir,
        attribution=attribution,
        workload=workload,
        run_id=run_id,
        agent=agent,
        phase=phase,
        usage=usage,
        provider=provider,
        model_id=model_id,
        request_id=request_id,
        source=source,
    )


def iter_cost_events(paths: Iterable[str | Path]) -> Iterable[dict[str, Any]]:
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("record_type") == "model_usage":
                record["_source_path"] = str(path)
                record["_line_number"] = line_number
                yield record


def summarize_events(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate by project, workload, and agent for human-facing reporting."""
    groups: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "project": "",
            "environment": "",
            "cost_center": "",
            "owner": "",
            "workload": "",
            "agent": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "estimated_cost_events": 0,
            "events": 0,
            "inference_profiles": set(),
        }
    )
    for event in events:
        key = (
            str(event.get("project", "")),
            str(event.get("environment", "")),
            str(event.get("cost_center", "")),
            str(event.get("owner", "")),
            str(event.get("workload", event.get("workload_name", ""))),
            str(event.get("agent", event.get("agent_name", ""))),
        )
        group = groups[key]
        (
            group["project"],
            group["environment"],
            group["cost_center"],
            group["owner"],
            group["workload"],
            group["agent"],
        ) = key
        for field_name in ("input_tokens", "output_tokens", "total_tokens"):
            group[field_name] += int(event.get(field_name) or 0)
        estimated = event.get("estimated_cost_usd")
        if estimated is not None:
            group["estimated_cost_usd"] += float(estimated)
            group["estimated_cost_events"] += 1
        profile = event.get("inference_profile_arn")
        if profile:
            group["inference_profiles"].add(str(profile))
        group["events"] += 1

    rows = []
    for group in groups.values():
        group["inference_profiles"] = sorted(group["inference_profiles"])
        rows.append(group)
    rows.sort(
        key=lambda row: (
            row["project"],
            row["environment"],
            row["workload"],
            row["agent"],
        )
    )
    return {
        "generated_at": _now(),
        "groups": rows,
        "totals": {
            "input_tokens": sum(row["input_tokens"] for row in rows),
            "output_tokens": sum(row["output_tokens"] for row in rows),
            "total_tokens": sum(row["total_tokens"] for row in rows),
            "estimated_cost_usd": sum(row["estimated_cost_usd"] for row in rows),
            "events": sum(row["events"] for row in rows),
        },
    }


def _format_summary(summary: Mapping[str, Any]) -> str:
    rows = summary.get("groups", [])
    lines = [
        "ADOP BEDROCK COST USAGE",
        "project | environment | cost_center | owner | workload | agent | "
        "input_tokens | output_tokens | total_tokens | estimated_usd",
        "-" * 100,
    ]
    for row in rows:
        lines.append(
            f"{row.get('project', '')} | {row.get('environment', '')} | "
            f"{row.get('cost_center', '')} | {row.get('owner', '')} | "
            f"{row.get('workload', '')} | {row.get('agent', '')} | "
            f"{row.get('input_tokens', 0)} | "
            f"{row.get('output_tokens', 0)} | {row.get('total_tokens', 0)} | "
            f"{float(row.get('estimated_cost_usd', 0.0)):.6f}"
        )
    totals = summary.get("totals", {})
    lines.extend(
        [
            "-" * 100,
            f"TOTAL | | | | | | {totals.get('input_tokens', 0)} | "
            f"{totals.get('output_tokens', 0)} | {totals.get('total_tokens', 0)} | "
            f"{float(totals.get('estimated_cost_usd', 0.0)):.6f}",
            "Estimated dollars are optional; reconcile official billed amounts from AWS CUR.",
        ]
    )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Report ADOP model usage by project/workload/agent.")
    parser.add_argument("command", choices=("summary",))
    parser.add_argument("--workload", help="Workload name under workloads/.")
    parser.add_argument("--run-id", help="Restrict events to one run.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    ns = parser.parse_args(argv)

    root = Path(ns.repo_root).resolve()
    if ns.workload:
        paths = [root / "workloads" / ns.workload / "run" / EVENTS_NAME]
    else:
        paths = root.glob(f"workloads/*/run/{EVENTS_NAME}")
    events = list(iter_cost_events(paths))
    if ns.run_id:
        events = [event for event in events if event.get("run_id") == ns.run_id]
    summary = summarize_events(events)
    print(json.dumps(summary, indent=2, sort_keys=True) if ns.json else _format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
