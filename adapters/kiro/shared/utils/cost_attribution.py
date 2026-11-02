"""Minimal cost attribution runtime for the standalone Kiro adapter."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml


class CostAttributionError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", value.strip())
    if not match:
        return value
    resolved = os.environ.get(match.group(1))
    if not resolved:
        raise CostAttributionError(f"{match.group(1)} is not set")
    return resolved


class CostAttribution:
    def __init__(self, values: Mapping[str, Any]):
        missing = [key for key in ("project", "environment", "cost_center", "owner") if not values.get(key)]
        if missing:
            raise CostAttributionError("missing: " + ", ".join(missing))
        self.values = {key: str(_resolve(values[key])) for key in values}

    @classmethod
    def from_workload(cls, workload_dir: str | Path) -> "CostAttribution":
        path = Path(workload_dir) / "config" / "cost_attribution.yaml"
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")) or {})

    def profile(self, agent: str) -> str:
        profiles = self.values.get("agent_inference_profiles", {})
        if isinstance(profiles, Mapping) and profiles.get(agent):
            return str(_resolve(profiles[agent]))
        return self.values.get("bedrock_inference_profile_arn", "")

    def dimensions(self, *, workload: str, run_id: str, agent: str, phase: Any) -> dict[str, Any]:
        return {
            "project": self.values["project"],
            "environment": self.values["environment"],
            "cost_center": self.values["cost_center"],
            "owner": self.values["owner"],
            "workload": workload,
            "run_id": run_id,
            "agent": agent,
            "phase": phase,
            "inference_profile_arn": self.profile(agent),
        }


def _find_usage(value: Any) -> tuple[dict[str, Any], str, str] | None:
    if isinstance(value, Mapping):
        for key in ("usage", "metrics", "model_usage", "token_usage"):
            if isinstance(value.get(key), Mapping):
                found = _find_usage(value[key])
                if found:
                    return found
        if any(key in value for key in ("inputTokens", "outputTokens", "input_tokens", "output_tokens")):
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
    phase: Any,
    payload: Any,
) -> dict[str, Any] | None:
    found = _find_usage(payload)
    if not found:
        return None
    usage, request_id, model_id = found
    input_tokens = int(usage.get("inputTokens") or usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("outputTokens") or usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    record = {
        "record_type": "model_usage",
        "timestamp": _now(),
        "provider": "bedrock",
        "source": "client_hook",
        "model_id": model_id,
        "request_id": request_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": int(usage.get("totalTokens") or usage.get("total_tokens") or input_tokens + output_tokens),
        **attribution.dimensions(workload=workload, run_id=run_id, agent=agent, phase=phase),
    }
    path = Path(run_dir) / "cost_events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record
