"""Cedar policy evaluator for the Agentic Data Onboarding Platform.

Dual-mode evaluation:
  - CEDAR_MODE=local  (default): Uses cedarpy to evaluate .cedar files from shared/policies/
  - CEDAR_MODE=avp:              Uses boto3 verifiedpermissions.is_authorized() API

Replaces GuardrailTracker from run_pipeline.py with Cedar-based policy evaluation
while maintaining backward-compatible .check() signature.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Policy file locations
# ---------------------------------------------------------------------------
POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"
GUARDRAILS_DIR = POLICIES_DIR / "guardrails"
AGENT_AUTH_DIR = POLICIES_DIR / "agent_authorization"
SCHEMA_FILE = POLICIES_DIR / "schema.cedarschema"

# ---------------------------------------------------------------------------
# Cedar mode: "local" (cedarpy) or "avp" (Amazon Verified Permissions)
# ---------------------------------------------------------------------------
CEDAR_MODE = os.environ.get("CEDAR_MODE", "local")


# ---------------------------------------------------------------------------
# Data classes for Cedar entities
# ---------------------------------------------------------------------------
@dataclass
class AgentPrincipal:
    """Represents a DataOnboarding::AgentPrincipal entity."""

    agent_type: str
    execution_context: str = "main_conversation"
    workload_name: str = ""

    def to_cedar(self) -> dict:
        return {
            "entityType": "DataOnboarding::AgentPrincipal",
            "entityId": self.agent_type,
        }

    def to_entity_record(self) -> dict:
        """AVP format for is_authorized API."""
        return {
            "identifier": self.to_cedar(),
            "attributes": {
                "agentType": {"String": self.agent_type},
                "executionContext": {"String": self.execution_context},
                "workloadName": {"String": self.workload_name},
            },
            "parents": [],
        }

    def to_cedarpy_entity(self) -> dict:
        """cedarpy format for local evaluation."""
        return {
            "uid": {"type": "DataOnboarding::AgentPrincipal", "id": self.agent_type},
            "attrs": {
                "agentType": self.agent_type,
                "executionContext": self.execution_context,
                "workloadName": self.workload_name,
            },
            "parents": [],
        }


@dataclass
class UserPrincipal:
    """Represents a DataOnboarding::UserPrincipal entity."""

    email: str
    role: str = "data_engineer"

    def to_cedar(self) -> dict:
        return {
            "entityType": "DataOnboarding::UserPrincipal",
            "entityId": self.email,
        }

    def to_entity_record(self) -> dict:
        return {
            "identifier": self.to_cedar(),
            "attributes": {
                "email": {"String": self.email},
                "role": {"String": self.role},
            },
            "parents": [],
        }

    def to_cedarpy_entity(self) -> dict:
        return {
            "uid": {"type": "DataOnboarding::UserPrincipal", "id": self.email},
            "attrs": {"email": self.email, "role": self.role},
            "parents": [],
        }


@dataclass
class DataZone:
    """Represents a DataOnboarding::DataZone entity."""

    zone: str
    workload_name: str = ""
    encryption_key_alias: str = ""

    def to_cedar(self) -> dict:
        return {
            "entityType": "DataOnboarding::DataZone",
            "entityId": f"{self.workload_name}_{self.zone}" if self.workload_name else self.zone,
        }

    def to_entity_record(self) -> dict:
        return {
            "identifier": self.to_cedar(),
            "attributes": {
                "zone": {"String": self.zone},
                "workloadName": {"String": self.workload_name},
                "encryptionKeyAlias": {"String": self.encryption_key_alias},
            },
            "parents": [],
        }

    def to_cedarpy_entity(self) -> dict:
        eid = f"{self.workload_name}_{self.zone}" if self.workload_name else self.zone
        return {
            "uid": {"type": "DataOnboarding::DataZone", "id": eid},
            "attrs": {"zone": self.zone, "workloadName": self.workload_name, "encryptionKeyAlias": self.encryption_key_alias},
            "parents": [],
        }


@dataclass
class WorkloadFile:
    """Represents a DataOnboarding::WorkloadFile entity."""

    entity_id: str
    file_type: str
    zone: str = ""

    def to_cedar(self) -> dict:
        return {
            "entityType": "DataOnboarding::WorkloadFile",
            "entityId": self.entity_id,
        }

    def to_entity_record(self) -> dict:
        return {
            "identifier": self.to_cedar(),
            "attributes": {
                "fileType": {"String": self.file_type},
                "zone": {"String": self.zone},
            },
            "parents": [],
        }

    def to_cedarpy_entity(self) -> dict:
        return {
            "uid": {"type": "DataOnboarding::WorkloadFile", "id": self.entity_id},
            "attrs": {"fileType": self.file_type, "zone": self.zone},
            "parents": [],
        }


@dataclass
class McpTool:
    """Represents a DataOnboarding::McpTool entity."""

    server_name: str
    tool_name: str

    def to_cedar(self) -> dict:
        return {
            "entityType": "DataOnboarding::McpTool",
            "entityId": f"{self.server_name}::{self.tool_name}",
        }

    def to_entity_record(self) -> dict:
        return {
            "identifier": self.to_cedar(),
            "attributes": {
                "serverName": {"String": self.server_name},
                "toolName": {"String": self.tool_name},
            },
            "parents": [],
        }

    def to_cedarpy_entity(self) -> dict:
        eid = f"{self.server_name}::{self.tool_name}"
        return {
            "uid": {"type": "DataOnboarding::McpTool", "id": eid},
            "attrs": {"serverName": self.server_name, "toolName": self.tool_name},
            "parents": [],
        }


@dataclass
class PipelineStep:
    """Represents a DataOnboarding::PipelineStep entity."""

    step_number: int
    step_name: str = ""
    source_zone: str = ""
    target_zone: str = ""

    def to_cedar(self) -> dict:
        return {
            "entityType": "DataOnboarding::PipelineStep",
            "entityId": f"step_{self.step_number}",
        }

    def to_entity_record(self) -> dict:
        return {
            "identifier": self.to_cedar(),
            "attributes": {
                "stepNumber": {"Long": self.step_number},
                "stepName": {"String": self.step_name},
                "sourceZone": {"String": self.source_zone},
                "targetZone": {"String": self.target_zone},
            },
            "parents": [],
        }

    def to_cedarpy_entity(self) -> dict:
        return {
            "uid": {"type": "DataOnboarding::PipelineStep", "id": f"step_{self.step_number}"},
            "attrs": {
                "stepNumber": self.step_number,
                "stepName": self.step_name,
                "sourceZone": self.source_zone,
                "targetZone": self.target_zone,
            },
            "parents": [],
        }


# ---------------------------------------------------------------------------
# Guardrail code -> Cedar action mapping
# ---------------------------------------------------------------------------
GUARDRAIL_ACTION_MAP = {
    "SEC-001": "PassSecurityCheck",
    "SEC-002": "PassSecurityCheck",
    "SEC-003": "PassSecurityCheck",
    "SEC-004": "PassSecurityCheck",
    "DQ-001": "PassQualityGate",
    "DQ-002": "PassQualityGate",
    "DQ-003": "PassQualityGate",
    "DQ-004": "PassQualityGate",
    "INT-001": "PassIntegrityCheck",
    "INT-002": "PassIntegrityCheck",
    "INT-003": "PassIntegrityCheck",
    "INT-004": "PassIntegrityCheck",
    "OPS-001": "PassOperationalCheck",
    "OPS-002": "PassOperationalCheck",
    "OPS-003": "PassOperationalCheck",
    "OPS-004": "PassOperationalCheck",
}


# ---------------------------------------------------------------------------
# Local Cedar evaluator (cedarpy)
# ---------------------------------------------------------------------------
class _LocalEvaluator:
    """Evaluates Cedar policies locally using cedarpy."""

    def __init__(self):
        self._policies = None
        self._schema = None
        self._cedarpy = None

    def _load(self):
        if self._policies is not None:
            return

        try:
            import cedarpy
            self._cedarpy = cedarpy
        except ImportError:
            self._cedarpy = None
            self._policies = []
            return

        self._policies = []
        for policy_dir in [GUARDRAILS_DIR, AGENT_AUTH_DIR]:
            if policy_dir.is_dir():
                for cedar_file in sorted(policy_dir.glob("*.cedar")):
                    self._policies.append(cedar_file.read_text())

        if SCHEMA_FILE.is_file():
            self._schema = SCHEMA_FILE.read_text()

    @staticmethod
    def _entity_ref(entity_dict: dict) -> str:
        """Convert {'entityType': 'Ns::Type', 'entityId': 'id'} to Cedar ref string."""
        return f'{entity_dict["entityType"]}::"{entity_dict["entityId"]}"'

    def is_authorized(
        self,
        principal: dict,
        action: str,
        resource: dict,
        context: dict,
        entities: list,
    ) -> tuple[bool, str]:
        """Evaluate Cedar policies locally.

        Returns (allowed: bool, reason: str).
        """
        self._load()

        if self._cedarpy is None:
            return self._fallback_evaluate(action, context)

        # cedarpy expects Cedar entity reference strings, not dicts
        cedar_request = {
            "principal": self._entity_ref(principal),
            "action": f'DataOnboarding::Action::"{action}"',
            "resource": self._entity_ref(resource),
            "context": context,
        }

        try:
            response = self._cedarpy.is_authorized(
                cedar_request,
                "\n\n".join(self._policies),
                entities,
            )
            allowed = str(response.decision) == "Decision.Allow"
            reason = "Cedar: ALLOW" if allowed else "Cedar: DENY"
            return allowed, reason
        except Exception as exc:
            return self._fallback_evaluate(action, context, str(exc))

    def _fallback_evaluate(
        self, action: str, context: dict, error: str = ""
    ) -> tuple[bool, str]:
        """JSON-based fallback when cedarpy is unavailable.

        Implements the same forbid logic as the Cedar policies by inspecting
        context attributes directly. This ensures guardrails work without
        the native Cedar engine.
        """
        code = context.get("guardrailCode", "")
        reason_prefix = "Fallback"
        if error:
            reason_prefix = f"Fallback (cedarpy error: {error})"

        # SEC guardrails
        if code == "SEC-001" and context.get("secretPatternFound") is True:
            return False, f"{reason_prefix}: hardcoded secret found"
        if code == "SEC-002" and context.get("kmsAliasValid") is False:
            return False, f"{reason_prefix}: KMS alias invalid"
        if code == "SEC-003" and context.get("piiColumnsMasked") is False:
            return False, f"{reason_prefix}: PII not masked"
        if code == "SEC-004" and context.get("tlsEnforced") is False:
            return False, f"{reason_prefix}: TLS not enforced"

        # DQ guardrails
        if code == "DQ-001":
            score = context.get("qualityScore", 100)
            threshold = context.get("qualityThreshold", 0)
            if score < threshold:
                return False, f"{reason_prefix}: quality {score} < {threshold}"
        if code == "DQ-002" and context.get("criticalFailureCount", 0) > 0:
            return False, f"{reason_prefix}: {context['criticalFailureCount']} critical failures"
        if code == "DQ-003" and context.get("rowAccountingBalances") is False:
            return False, f"{reason_prefix}: rows silently dropped"
        if code == "DQ-004" and context.get("rowCountAboveZero") is False:
            return False, f"{reason_prefix}: zero output rows"

        # INT guardrails
        if code == "INT-001" and context.get("landingFileWritten") is False:
            return False, f"{reason_prefix}: landing file not written"
        if code == "INT-002":
            rate = context.get("fkPassRate", 100)
            threshold = context.get("fkThreshold", 0)
            if rate < threshold:
                return False, f"{reason_prefix}: FK rate {rate} < {threshold}"
        if code == "INT-003" and context.get("formulaVerified") is False:
            return False, f"{reason_prefix}: formula not verified"
        if code == "INT-004" and context.get("schemaMatches") is False:
            return False, f"{reason_prefix}: schema mismatch"

        # OPS guardrails
        if code == "OPS-001" and context.get("checksumMatch") is False:
            return False, f"{reason_prefix}: checksum mismatch"
        if code == "OPS-002" and context.get("keysAreDifferent") is False:
            return False, f"{reason_prefix}: encryption not re-keyed"
        if code == "OPS-003" and context.get("auditLogWritten") is False:
            return False, f"{reason_prefix}: audit log missing"
        if code == "OPS-004" and context.get("icebergMetadataExists") is False:
            return False, f"{reason_prefix}: iceberg metadata missing"

        return True, f"{reason_prefix}: ALLOW"

    def is_agent_authorized(
        self,
        agent: AgentPrincipal,
        action: str,
        resource,
    ) -> tuple[bool, str]:
        """Check if an agent is authorized for a specific action on a resource."""
        self._load()

        entities = [agent.to_cedarpy_entity(), resource.to_cedarpy_entity()]

        if self._cedarpy is None:
            return self._fallback_agent_auth(agent, action, resource)

        cedar_request = {
            "principal": self._entity_ref(agent.to_cedar()),
            "action": f'DataOnboarding::Action::"{action}"',
            "resource": self._entity_ref(resource.to_cedar()),
            "context": {},
        }

        try:
            response = self._cedarpy.is_authorized(
                cedar_request,
                "\n\n".join(self._policies),
                entities,
            )
            allowed = str(response.decision) == "Decision.Allow"
            reason = "Cedar: ALLOW" if allowed else "Cedar: DENY"
            return allowed, reason
        except Exception as exc:
            return self._fallback_agent_auth(agent, action, resource, str(exc))

    def _fallback_agent_auth(
        self,
        agent: AgentPrincipal,
        action: str,
        resource,
        error: str = "",
    ) -> tuple[bool, str]:
        """Fallback agent authorization when cedarpy is unavailable."""
        a = agent.agent_type
        reason_prefix = "Fallback"

        # Router: read-only
        if a == "router":
            if action in ("ReadFile", "ReadData"):
                return True, f"{reason_prefix}: router can read"
            return False, f"{reason_prefix}: router is read-only"

        # Onboarding: full access in main conversation
        if a == "onboarding" and agent.execution_context == "main_conversation":
            return True, f"{reason_prefix}: onboarding has full access"

        # Sub-agents cannot invoke MCP tools
        if action == "InvokeTool" and a not in ("onboarding",):
            return False, f"{reason_prefix}: sub-agent cannot invoke MCP"

        # Metadata: config writes only
        if a == "metadata":
            if action == "WriteFile" and hasattr(resource, "file_type"):
                if resource.file_type != "config":
                    return False, f"{reason_prefix}: metadata can only write config"
            if action == "WriteData" and hasattr(resource, "zone"):
                if resource.zone == "publish":
                    return False, f"{reason_prefix}: metadata cannot write publish"

        # Transformation: no publish writes
        if a == "transformation":
            if action == "WriteData" and hasattr(resource, "zone"):
                if resource.zone == "publish":
                    return False, f"{reason_prefix}: transformation cannot write publish"
            if action == "WriteFile" and hasattr(resource, "file_type"):
                if resource.file_type not in ("script", "sql"):
                    return False, f"{reason_prefix}: transformation can only write scripts/sql"

        # Quality: read-only for data
        if a == "quality":
            if action in ("WriteData", "PromoteData"):
                return False, f"{reason_prefix}: quality cannot modify data"
            if action == "WriteFile" and hasattr(resource, "file_type"):
                if resource.file_type != "config":
                    return False, f"{reason_prefix}: quality can only write config"

        # DAG: dag files only, no data access
        if a == "dag":
            if action in ("ReadData", "WriteData"):
                return False, f"{reason_prefix}: dag cannot access data directly"
            if action == "WriteFile" and hasattr(resource, "file_type"):
                if resource.file_type != "dag":
                    return False, f"{reason_prefix}: dag can only write dag files"

        # Analysis: publish read-only
        if a == "analysis":
            if action in ("WriteData", "WriteFile", "PromoteData"):
                return False, f"{reason_prefix}: analysis is read-only"
            if action == "ReadData" and hasattr(resource, "zone"):
                if resource.zone in ("landing", "staging"):
                    return False, f"{reason_prefix}: analysis can only read publish"

        return True, f"{reason_prefix}: ALLOW"


# ---------------------------------------------------------------------------
# AVP evaluator (Amazon Verified Permissions)
# ---------------------------------------------------------------------------
class _AvpEvaluator:
    """Evaluates Cedar policies via Amazon Verified Permissions."""

    def __init__(self):
        self._client = None
        self._policy_store_id = os.environ.get("AVP_POLICY_STORE_ID", "")

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("verifiedpermissions")
        return self._client

    def _cedar_value(self, val: Any) -> dict:
        """Convert a Python value to AVP EntityAttributeValue format."""
        if isinstance(val, bool):
            return {"boolean": val}
        if isinstance(val, int):
            return {"long": val}
        if isinstance(val, str):
            return {"string": val}
        return {"string": str(val)}

    def is_authorized(
        self,
        principal: dict,
        action: str,
        resource: dict,
        context: dict,
        entities: list,
    ) -> tuple[bool, str]:
        """Evaluate via AVP is_authorized API."""
        client = self._get_client()

        context_map = {}
        for k, v in context.items():
            context_map[k] = self._cedar_value(v)

        try:
            response = client.is_authorized(
                policyStoreId=self._policy_store_id,
                principal={
                    "entityType": principal["entityType"],
                    "entityId": principal["entityId"],
                },
                action={
                    "actionType": "DataOnboarding::Action",
                    "actionId": action,
                },
                resource={
                    "entityType": resource["entityType"],
                    "entityId": resource["entityId"],
                },
                context={"contextMap": context_map},
                entities={"entityList": entities},
            )
            allowed = response["decision"] == "ALLOW"
            reason = f"AVP: {response['decision']}"
            if response.get("errors"):
                reason += f" (errors: {response['errors']})"
            return allowed, reason
        except Exception as exc:
            return True, f"AVP error (defaulting to ALLOW): {exc}"

    def is_agent_authorized(
        self,
        agent: AgentPrincipal,
        action: str,
        resource,
    ) -> tuple[bool, str]:
        entities = [agent.to_entity_record(), resource.to_entity_record()]
        return self.is_authorized(
            principal=agent.to_cedar(),
            action=action,
            resource=resource.to_cedar(),
            context={},
            entities=entities,
        )


# ---------------------------------------------------------------------------
# CedarPolicyEvaluator — drop-in replacement for GuardrailTracker
# ---------------------------------------------------------------------------
class CedarPolicyEvaluator:
    """Cedar-based guardrail evaluator.

    Backward-compatible with GuardrailTracker.check() signature.
    Adds Cedar policy evaluation when context/principal/resource are provided.
    """

    def __init__(self, mode: Optional[str] = None):
        self._mode = mode or CEDAR_MODE
        self._evaluator = _AvpEvaluator() if self._mode == "avp" else _LocalEvaluator()
        self.results: list[dict] = []
        self.audit_log: list[dict] = []

    def check(
        self,
        code: str,
        description: str,
        passed: bool,
        detail: str = "",
        context: Optional[dict] = None,
        principal: Optional[AgentPrincipal] = None,
        resource: Optional[PipelineStep] = None,
    ) -> bool:
        """Record a guardrail check result with optional Cedar evaluation.

        When context, principal, and resource are provided, the check is also
        evaluated against Cedar policies. The Cedar decision overrides the
        `passed` parameter to ensure policy-as-code is authoritative.

        Returns the final pass/fail result.
        """
        cedar_decision = None
        cedar_reason = ""

        if context is not None:
            # Ensure guardrailCode is in context
            if "guardrailCode" not in context:
                context["guardrailCode"] = code

            action = GUARDRAIL_ACTION_MAP.get(code, "PassSecurityCheck")

            if principal is None:
                principal = AgentPrincipal("onboarding")
            if resource is None:
                resource = PipelineStep(step_number=0, step_name=description)

            if self._mode == "avp":
                entities = [principal.to_entity_record(), resource.to_entity_record()]
            else:
                entities = [principal.to_cedarpy_entity(), resource.to_cedarpy_entity()]

            cedar_decision, cedar_reason = self._evaluator.is_authorized(
                principal=principal.to_cedar(),
                action=action,
                resource=resource.to_cedar(),
                context=context,
                entities=entities,
            )

            # Cedar decision is authoritative when provided
            passed = cedar_decision

        self.results.append({
            "code": code,
            "description": description,
            "passed": passed,
            "detail": detail,
            "cedar_decision": cedar_decision,
            "cedar_reason": cedar_reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Audit log entry
        self.audit_log.append({
            "guardrail": code,
            "description": description,
            "decision": "ALLOW" if passed else "DENY",
            "cedar_evaluated": cedar_decision is not None,
            "cedar_reason": cedar_reason,
            "mode": self._mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Print output (same format as GuardrailTracker)
        status = "PASS" if passed else "FAIL"
        label = f"[GUARDRAIL {code}] {description}"
        dots = "." * max(1, 60 - len(label))
        engine = f" [{self._mode}]" if cedar_decision is not None else ""
        print(f"  {label} {dots} {status}{engine}")
        if not passed and detail:
            print(f"  >>> Guardrail violation logged. {detail}")
        if not passed and cedar_reason:
            print(f"  >>> Cedar: {cedar_reason}")

        return passed

    def authorize_agent(
        self,
        agent: AgentPrincipal,
        action: str,
        resource,
    ) -> tuple[bool, str]:
        """Check if an agent is authorized for an action on a resource.

        Used by the orchestrator to validate sub-agent outputs.
        """
        allowed, reason = self._evaluator.is_agent_authorized(agent, action, resource)

        self.audit_log.append({
            "agent": agent.agent_type,
            "action": action,
            "resource_type": type(resource).__name__,
            "decision": "ALLOW" if allowed else "DENY",
            "reason": reason,
            "mode": self._mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return allowed, reason

    def all_passed(self) -> bool:
        """Return True if every guardrail passed."""
        return all(r["passed"] for r in self.results)

    def print_summary(self):
        """Print a final summary table of all guardrails."""
        print()
        print("=" * 78)
        print("  GUARDRAIL SUMMARY (Cedar Policy Engine)")
        print(f"  Mode: {self._mode} | Evaluated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 78)
        print(f"  {'Code':<12} {'Description':<42} {'Result':<6} {'Engine':<8}")
        print(f"  {'-'*10:<12} {'-'*40:<42} {'-'*6:<6} {'-'*8:<8}")
        for r in self.results:
            status = "PASS" if r["passed"] else "FAIL"
            engine = self._mode if r["cedar_decision"] is not None else "inline"
            desc = r["description"][:40]
            print(f"  {r['code']:<12} {desc:<42} {status:<6} {engine:<8}")
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed
        cedar_count = sum(1 for r in self.results if r["cedar_decision"] is not None)
        print(f"  {'-'*10:<12} {'-'*40:<42} {'-'*6:<6} {'-'*8:<8}")
        print(f"  Total: {total}   Passed: {passed}   Failed: {failed}   Cedar-evaluated: {cedar_count}")
        if failed > 0:
            print("  >>> PIPELINE HAS GUARDRAIL VIOLATIONS <<<")
        else:
            print("  >>> ALL GUARDRAILS PASSED <<<")
        print("=" * 78)

    def export_audit_log(self, path: Optional[str] = None) -> str:
        """Export audit log to JSON file. Returns the file path."""
        if path is None:
            path = f"audit_log_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        with open(path, "w") as f:
            json.dump(self.audit_log, f, indent=2)
        return path
