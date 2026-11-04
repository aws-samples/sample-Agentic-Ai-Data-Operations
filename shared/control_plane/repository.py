"""Read-only repository projections used by the control-plane API."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from shared.codegen.contract_resolver import resolve_effective_policy


POLICY_FILES = {
    "agent_authorization/global_protection": "shared/policies/agent_authorization/global_protection.cedar",
    "guardrails/sec_003_pii_masking": "shared/policies/guardrails/sec_003_pii_masking.cedar",
    "guardrails/dq_001_quality_gate_threshold": "shared/policies/guardrails/dq_001_quality_gate_threshold.cedar",
}
SCOPE_NAMES = re.compile(r"^[a-z][a-z0-9_-]{0,60}$")


class RepositoryProjection:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def list_workloads(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for context_path in sorted(self.root.glob("workloads/*/run/context.json")):
            try:
                context = json.loads(context_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            workload_dir = context_path.parent.parent
            answers = context.get("human_answers") or {}
            try:
                effective = resolve_effective_policy(workload_dir)
            except Exception:
                effective = {}
            records.append(
                {
                    "name": context.get("workload_name", workload_dir.name),
                    "run_id": context.get("run_id"),
                    "phase": context.get("current_phase"),
                    "started_at": context.get("started_at"),
                    "zones": answers.get("zones", []),
                    "compliance": answers.get("compliance", []),
                    "schedule": answers.get("schedule"),
                    "schedule_timezone": answers.get("schedule_timezone"),
                    "quality_thresholds": answers.get("quality_thresholds", {}),
                    "effective_contract": {
                        "effective_hash": effective.get("effective_hash"),
                        "organization_version": effective.get("organization_version"),
                        "domain_version": effective.get("domain_version"),
                        "project_version": effective.get("project_version"),
                    },
                }
            )
        return records

    def get_workload(self, name: str) -> dict[str, Any]:
        for record in self.list_workloads():
            if record["name"] == name:
                return record
        raise KeyError(name)

    def workload_dir(self, name: str) -> Path:
        path = self.root / "workloads" / name
        if not path.is_dir():
            raise KeyError(name)
        return path

    def get_contract(
        self,
        workload_name: str,
        *,
        domain: str | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Return every contract layer plus the resolver's effective result."""
        if domain and not SCOPE_NAMES.fullmatch(domain):
            raise ValueError("Invalid domain scope name")
        if project and not SCOPE_NAMES.fullmatch(project):
            raise ValueError("Invalid project scope name")
        workload_dir = self.workload_dir(workload_name)
        policy_root = self.root / "contracts" / "policies"
        layers = {
            "organization": self._contract_layer(
                policy_root / "organization" / "default.yaml", "default"
            ),
            "domain": self._contract_layer(
                policy_root / "domains" / f"{domain}.yaml", domain
            )
            if domain
            else None,
            "project": self._contract_layer(
                policy_root / "projects" / f"{project}.yaml", project
            )
            if project
            else None,
        }
        effective = resolve_effective_policy(
            workload_dir,
            scope={"domain": domain, "project": project},
        )
        return {
            "workload_name": workload_name,
            "scope": {
                "organization": "default",
                "domain": domain,
                "project": project,
            },
            "layers": layers,
            "effective": effective,
        }

    def _contract_layer(self, path: Path, scope_name: str | None) -> dict[str, Any] | None:
        if not scope_name or not path.exists():
            return None
        try:
            policy = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return {
                "scope": path.parent.name.removesuffix("s"),
                "scope_name": scope_name,
                "path": str(path),
                "status": "invalid",
            }
        content = json.dumps(policy, sort_keys=True, separators=(",", ":"))
        return {
            "scope": policy.get("scope"),
            "scope_name": scope_name,
            "path": str(path.relative_to(self.root)),
            "version": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "policy": policy,
            "status": "configured",
        }

    def list_policies(self) -> list[dict[str, Any]]:
        records = []
        for policy_id, relative_path in POLICY_FILES.items():
            path = self.root / relative_path
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            records.append(
                {
                    "policy_id": policy_id,
                    "path": relative_path,
                    "version": self.content_hash(content),
                    "size": len(content.encode("utf-8")),
                }
            )
        return records

    def get_policy(self, policy_id: str) -> dict[str, Any]:
        relative_path = POLICY_FILES.get(policy_id)
        if not relative_path:
            raise KeyError(policy_id)
        path = self.root / relative_path
        if not path.exists():
            raise KeyError(policy_id)
        content = path.read_text(encoding="utf-8")
        return {
            "policy_id": policy_id,
            "path": relative_path,
            "version": self.content_hash(content),
            "content": content,
        }

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def cedar_schema(self) -> str:
        return (self.root / "shared/policies/schema.cedarschema").read_text(
            encoding="utf-8"
        )
