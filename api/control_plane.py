"""API Gateway/Lambda-compatible ADOP control-plane handler."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import jsonschema

from .github_bridge import GitHubAppBridge, GitHubBridgeError
from .auth import auth_config, identity_from_event, local_login
from shared.codegen.contract_resolver import ContractPolicyError, _merge
from shared.control_plane.connectors import (
    normalize_connector,
    persistent_connector_metadata,
    test_connector as run_connector_test,
    validate_connector_profile,
)
from shared.control_plane.authorization import (
    SYSTEM_WORKSPACES,
    can_edit_contract_scope,
    can_edit_scope,
    can_view_scope,
    has_feature,
    local_test_users,
    project_domain,
    visible_workloads,
    with_workspace_registry,
)
from shared.control_plane.repository import RepositoryProjection
from shared.control_plane.store import (
    ChangeNotFoundError,
    ControlPlaneStore,
    VersionConflictError,
    create_store_from_environment,
)
from shared.control_plane.validation import ValidationFailure, validate_cedar_policy


ROOT = Path(__file__).resolve().parents[1]
SCOPE_LEVELS = {"organization", "domain", "project"}


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str = "bad_request"):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


def _json(status: int, body: Any) -> dict[str, Any]:
    configured_origin = os.getenv("ADOP_ALLOWED_ORIGIN", "").strip()
    if not configured_origin and os.getenv("ADOP_ENV", "local").lower() == "local":
        configured_origin = "http://127.0.0.1:4173"
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "cache-control": "no-store",
            "access-control-allow-origin": configured_origin or "null",
            "access-control-allow-headers": "content-type,authorization,x-adop-actor,x-adop-name,x-adop-role,x-adop-groups,x-adop-workspace",
            "access-control-allow-methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ApiError(400, "Request body must be valid JSON", "invalid_json") from exc
    if not isinstance(value, dict):
        raise ApiError(400, "Request body must be a JSON object", "invalid_body")
    return value


def _actor(event: dict[str, Any]) -> str:
    identity = identity_from_event(event)
    if identity:
        return str(identity["email"])
    if os.getenv("ADOP_ENV", "local").lower() == "local":
        return "local-user"
    raise ApiError(401, "Authenticated SSO identity is required", "unauthorized")


def _query(event: dict[str, Any]) -> dict[str, str]:
    values = event.get("queryStringParameters") or {}
    if values:
        return {str(key): str(value) for key, value in values.items() if value is not None}
    raw_path = event.get("rawPath") or event.get("path") or ""
    return {
        key: value[-1]
        for key, value in parse_qs(urlsplit(raw_path).query).items()
        if value
    }


def _scope(payload: dict[str, Any] | None = None, query: dict[str, str] | None = None) -> tuple[str, str]:
    values = payload or query or {}
    level = str(values.get("scope") or "organization").lower()
    name = str(
        values.get("scope_name")
        or (values.get("name") if "scope" in values else None)
        or "default"
    ).lower()
    if level not in SCOPE_LEVELS:
        raise ApiError(400, "scope must be organization, domain, or project", "invalid_scope")
    if level == "organization" and name != "default":
        raise ApiError(400, "organization scope_name must be default", "invalid_scope")
    if level != "organization" and (
        not name or not name[0].isalpha() or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in name)
    ):
        raise ApiError(400, f"Invalid {level} scope name", "invalid_scope")
    return level, name


def _identity_for_request(
    event: dict[str, Any],
    service: ControlPlaneService | None = None,
) -> dict[str, Any] | None:
    origin = next(
        (
            str(value)
            for key, value in (event.get("headers") or {}).items()
            if str(key).lower() == "origin" and value
        ),
        "",
    )
    if os.getenv("ADOP_ENV", "local").lower() == "local" and origin:
        allowed = {
            value.strip()
            for value in os.getenv(
                "ADOP_LOCAL_ALLOWED_ORIGINS",
                "http://127.0.0.1:4173",
            ).split(",")
            if value.strip()
        }
        if origin not in allowed:
            raise ApiError(403, "Cross-origin local control-plane access is disabled", "origin_forbidden")
    workspace_parents: dict[str, str] = {}
    if service is not None:
        workspace_parents = {
            str(item.get("name")): str(item.get("parent_name"))
            for item in service.store.list_workspaces()
            if item.get("level") == "project"
            and item.get("name")
            and item.get("parent_name")
        }
    identity = identity_from_event(event, workspace_parents=workspace_parents)
    if identity:
        identity = with_workspace_registry(identity, workspace_parents)
    if identity and identity.get("workspace_error"):
        raise ApiError(403, str(identity["workspace_error"]), "workspace_forbidden")
    return identity


def _require_feature(
    identity: dict[str, Any] | None,
    feature: str,
) -> None:
    if not identity:
        raise ApiError(401, "Authenticated identity is required", "unauthorized")
    if not has_feature(identity, feature):
        raise ApiError(403, f"Feature permission required: {feature}", "feature_forbidden")


def _selected_scope(identity: dict[str, Any] | None) -> tuple[str, str] | None:
    selected = identity.get("selected_workspace") if identity else None
    if not selected:
        return None
    return str(selected["level"]), str(selected["name"])


def _record_scope_visible(
    identity: dict[str, Any] | None,
    record: dict[str, Any],
) -> bool:
    if (
        identity
        and identity.get("selected_workspace")
        and record.get("change_type") == "zone_contract"
        and record.get("workload_name")
    ):
        workload = {"name": str(record["workload_name"])}
        if not visible_workloads(identity, [workload]):
            return False
    scope = str(record.get("scope") or "organization")
    scope_name = str(record.get("scope_name") or "default")
    return can_view_scope(identity, scope, scope_name)


# Specialist roles may only decide the change types they own. Roles not listed
# (org-admin, domain-owner) keep their scope-based approval rights.
APPROVABLE_CHANGE_TYPES: dict[str, frozenset[str]] = {
    "security-admin": frozenset({"cedar_policy"}),
    "connector-admin": frozenset({"connector"}),
}


class ControlPlaneService:
    def __init__(
        self,
        repository: RepositoryProjection | None = None,
        store: ControlPlaneStore | None = None,
    ):
        self.repository = repository or RepositoryProjection(
            os.getenv("ADOP_REPO_ROOT", str(ROOT))
        )
        self.store = store or create_store_from_environment()
        self.github = GitHubAppBridge.from_environment()

    def workloads(self, identity: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        _require_feature(identity, "workloads.read")
        return visible_workloads(identity, self.repository.list_workloads())

    def _require_visible_workload(
        self,
        workload_name: str,
        identity: dict[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            record = self.repository.get_workload(workload_name)
        except KeyError as exc:
            raise ApiError(404, f"Workload not found: {workload_name}", "not_found") from exc
        if not visible_workloads(identity, [record]):
            raise ApiError(404, f"Workload not found: {workload_name}", "not_found")
        return record

    def connectors(self, identity: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        _require_feature(identity, "connectors.read")
        return [
            normalize_connector(item)
            for item in self.store.list_connectors()
            if _record_scope_visible(identity, item)
        ]

    def connector(
        self, connector_id: str, identity: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        _require_feature(identity, "connectors.read")
        try:
            record = self.store.get_connector(connector_id)
        except ChangeNotFoundError as exc:
            raise ApiError(404, f"Connector not found: {connector_id}", "not_found") from exc
        if not _record_scope_visible(identity, record):
            raise ApiError(404, f"Connector not found: {connector_id}", "not_found")
        return normalize_connector(record)

    @staticmethod
    def _connector_profile(payload: dict[str, Any]) -> dict[str, Any]:
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {
                key: payload[key]
                for key in (
                    "host",
                    "port",
                    "account",
                    "warehouse",
                    "database",
                    "schema",
                    "role",
                    "http_path",
                )
                if payload.get(key) not in (None, "")
            }
        return {
            "name": payload.get("name"),
            "type": str(payload.get("type") or payload.get("provider") or "").lower(),
            "metadata": metadata,
            "secret_ref": payload.get("secret_ref"),
            "access_mode": payload.get("access_mode", "read-only"),
        }

    def create_connector(
        self,
        payload: dict[str, Any],
        actor: str,
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _require_feature(identity, "connectors.create")
        profile = self._connector_profile(payload)
        scope, scope_name = _scope(payload)
        selected = _selected_scope(identity)
        if "scope" not in payload and selected:
            scope, scope_name = selected
        if not can_edit_scope(identity, scope, scope_name):
            raise ApiError(403, f"Identity cannot edit {scope}/{scope_name}", "scope_forbidden")
        try:
            validate_connector_profile(profile)
            record = self.store.create_connector(
                name=profile["name"],
                provider=profile["type"],
                metadata=persistent_connector_metadata(profile["metadata"]),
                secret_ref=profile["secret_ref"],
                access_mode=str(profile["access_mode"]),
                actor=actor,
                scope=scope,
                scope_name=scope_name,
            )
        except ValueError as exc:
            raise ApiError(400, str(exc), "invalid_connector") from exc
        except VersionConflictError as exc:
            raise ApiError(409, str(exc), "already_exists") from exc
        return normalize_connector(record)

    def test_connector(
        self, connector_id: str, identity: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        _require_feature(identity, "connectors.test")
        try:
            record = self.store.get_connector(connector_id)
        except ChangeNotFoundError as exc:
            raise ApiError(404, f"Connector not found: {connector_id}", "not_found") from exc
        if not _record_scope_visible(identity, record):
            raise ApiError(404, f"Connector not found: {connector_id}", "not_found")
        profile = {**record.get("metadata", {}), **record}
        health = run_connector_test(profile)
        updated = self.store.update_connector_health(connector_id, health)
        return normalize_connector(updated)

    def test_connector_draft(
        self,
        payload: dict[str, Any],
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _require_feature(identity, "connectors.test")
        if os.getenv("ADOP_ENV", "local").lower() != "local":
            raise ApiError(
                403,
                "Draft connector tests are disabled in AWS mode. Save the scoped connector first, then run its health check.",
                "draft_connector_test_forbidden",
            )
        profile = self._connector_profile(payload)
        try:
            validate_connector_profile(profile)
        except ValueError as exc:
            raise ApiError(400, str(exc), "invalid_connector") from exc
        return run_connector_test({**profile["metadata"], **profile})

    def test_all_connectors(self, identity: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        _require_feature(identity, "connectors.test")
        results = []
        for item in self.store.list_connectors():
            if _record_scope_visible(identity, item):
                results.append(self.test_connector(item["connector_id"], identity))
        return results

    def workload(self, name: str, identity: dict[str, Any] | None = None) -> dict[str, Any]:
        _require_feature(identity, "workloads.read")
        try:
            record = self.repository.get_workload(name)
        except KeyError as exc:
            raise ApiError(404, f"Workload not found: {name}", "not_found") from exc
        if not any(item.get("name") == name for item in visible_workloads(identity, [record])):
            raise ApiError(404, f"Workload not found: {name}", "not_found")
        return record

    def _validate_contract_scope_pair(
        self,
        *,
        domain: str | None,
        project: str | None,
    ) -> None:
        """Prevent a project from being resolved through an unrelated domain."""
        if not domain or not project:
            return
        persisted_parent = next(
            (
                str(item.get("parent_name"))
                for item in self.store.list_workspaces()
                if item.get("level") == "project" and item.get("name") == project
            ),
            None,
        )
        expected_domain = persisted_parent or project_domain(project)
        if expected_domain and expected_domain != domain:
            raise ApiError(
                403,
                f"Project {project} belongs to domain {expected_domain}, not {domain}",
                "scope_forbidden",
            )

    def policies(
        self,
        *,
        scope: str = "organization",
        scope_name: str = "default",
        identity: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        _require_feature(identity, "policies.read")
        if not can_view_scope(identity, scope, scope_name):
            raise ApiError(403, f"Identity cannot view {scope}/{scope_name}", "scope_forbidden")
        proposals = self.store.list_policy_proposals()
        latest_by_policy: dict[str, dict[str, Any]] = {}
        for proposal in proposals:
            if (
                proposal.get("change_type", "cedar_policy") == "cedar_policy"
                and proposal.get("scope", "organization") == scope
                and proposal.get("scope_name", "default") == scope_name
            ):
                latest_by_policy.setdefault(proposal["policy_id"], proposal)
        records = []
        for policy in self.repository.list_policies():
            records.append(
                {
                    **policy,
                    "scope": scope,
                    "scope_name": scope_name,
                    "inherits_from": (
                        None if scope == "organization" else "organization/default"
                    ),
                    "proposal": latest_by_policy.get(policy["policy_id"]),
                }
            )
        return records

    def policy(
        self,
        policy_id: str,
        *,
        scope: str = "organization",
        scope_name: str = "default",
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _require_feature(identity, "policies.read")
        if not can_view_scope(identity, scope, scope_name):
            raise ApiError(403, f"Identity cannot view {scope}/{scope_name}", "scope_forbidden")
        try:
            policy = self.repository.get_policy(policy_id)
        except KeyError as exc:
            raise ApiError(404, f"Policy not found: {policy_id}", "not_found") from exc
        proposal = next(
            (
                item
                for item in self.store.list_policy_proposals()
                if item.get("change_type", "cedar_policy") == "cedar_policy"
                and item.get("policy_id") == policy_id
                and item.get("scope", "organization") == scope
                and item.get("scope_name", "default") == scope_name
            ),
            None,
        )
        return {
            **policy,
            "scope": scope,
            "scope_name": scope_name,
            "inherits_from": None if scope == "organization" else "organization/default",
            "proposal": proposal,
        }

    def contracts(
        self,
        *,
        workload_name: str,
        domain: str | None = None,
        project: str | None = None,
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _require_feature(identity, "contracts.read")
        self._require_visible_workload(workload_name, identity)
        self._validate_contract_scope_pair(domain=domain, project=project)
        if domain and not can_view_scope(identity, "domain", domain) and not (
            project and can_view_scope(identity, "project", project)
        ):
            raise ApiError(403, f"Identity cannot view domain/{domain}", "scope_forbidden")
        if project and not can_view_scope(identity, "project", project):
            raise ApiError(403, f"Identity cannot view project/{project}", "scope_forbidden")
        try:
            projection = self.repository.get_contract(
                workload_name,
                domain=domain,
                project=project,
            )
        except (KeyError, ValueError, ContractPolicyError) as exc:
            raise ApiError(404 if isinstance(exc, KeyError) else 422, str(exc), "contract_resolution_failed") from exc
        proposals: dict[str, dict[str, Any]] = {}
        for item in self.store.list_policy_proposals():
            if item.get("change_type") != "zone_contract":
                continue
            if not _record_scope_visible(identity, item):
                continue
            proposals[
                f"{item.get('scope', 'organization')}/{item.get('scope_name', 'default')}"
            ] = item
        projection["proposals"] = proposals
        return projection

    def validate_policy(
        self,
        policy_id: str,
        content: str,
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _require_feature(identity, "policies.validate")
        try:
            return validate_cedar_policy(self.repository, policy_id, content)
        except (KeyError, ValidationFailure) as exc:
            raise ApiError(422, str(exc), "validation_failed") from exc

    def create_policy_proposal(
        self,
        policy_id: str,
        payload: dict[str, Any],
        actor: str,
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _require_feature(identity, "policies.propose")
        content = payload.get("content")
        if not isinstance(content, str):
            raise ApiError(400, "content is required", "invalid_body")
        scope, scope_name = _scope(payload)
        if not can_edit_scope(identity, scope, scope_name):
            raise ApiError(403, f"Identity cannot edit {scope}/{scope_name}", "scope_forbidden")
        validation = self.validate_policy(policy_id, content, identity)
        current = self.policy(policy_id, scope=scope, scope_name=scope_name, identity=identity)
        try:
            record = self.store.create_policy_proposal(
                policy_id=policy_id,
                content=content,
                actor=actor,
                expected_version=payload.get("expected_version") or current["version"],
                required_approvals=2,
                scope=scope,
                scope_name=scope_name,
            )
        except VersionConflictError as exc:
            raise ApiError(409, str(exc), "version_conflict") from exc
        record["validation"] = validation
        if self.github and scope == "organization":
            try:
                reference = self.github.create_policy_pull_request(
                    path=current["path"],
                    content=content,
                    change_id=record["change_id"],
                    policy_id=policy_id,
                )
                record = self.store.attach_external_reference(
                    record["change_id"],
                    {
                        "provider": "github",
                        "number": reference.number,
                        "url": reference.url,
                        "branch": reference.branch,
                        "status": "open",
                    },
                )
            except GitHubBridgeError as exc:
                record["github_error"] = str(exc)
        elif scope != "organization":
            record["application_note"] = (
                "Scoped Cedar is stored and approval-gated in the control plane. "
                "A workload-aware Cedar resolver must be enabled before this scope is applied at runtime."
            )
        return record

    def create_contract_proposal(
        self,
        payload: dict[str, Any],
        actor: str,
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _require_feature(identity, "contracts.propose")
        workload_name = payload.get("workload_name")
        content = payload.get("content")
        if not isinstance(workload_name, str) or not workload_name:
            raise ApiError(400, "workload_name is required", "invalid_body")
        if not isinstance(content, dict):
            raise ApiError(400, "content must be a contract object", "invalid_body")
        self._require_visible_workload(str(workload_name), identity)
        scope, scope_name = _scope(payload)
        self._validate_contract_scope_pair(
            domain=str(payload.get("domain") or "sales"),
            project=str(payload.get("project") or "orders"),
        )
        if not can_edit_contract_scope(identity, scope, scope_name):
            raise ApiError(
                403,
                "Only organization administrators can change organization/domain contracts; "
                "other users may change project contracts.",
                "contract_scope_forbidden",
            )
        domain = str(payload.get("domain") or "sales")
        project = str(payload.get("project") or "orders")
        try:
            projection = self.repository.get_contract(
                workload_name,
                domain=domain if scope in {"domain", "project"} else None,
                project=project if scope == "project" else None,
            )
            if scope == "organization":
                base = {}
            elif scope == "domain":
                base = self.repository.get_contract(workload_name)["effective"]
            else:
                base = projection["effective"]
            schema = json.loads(
                (self.repository.root / "contracts/policies/zone_policy.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            candidate = self._contract_document(dict(content))
            candidate.setdefault("scope", scope)
            if candidate.get("scope") != scope:
                raise ApiError(422, "Contract content scope does not match the selected scope", "validation_failed")
            jsonschema.Draft202012Validator(schema).validate(candidate)
            if scope == "organization":
                # The organization layer is the floor for every domain/project, so a
                # proposal may only tighten the current organization policy.
                current_org = self.repository.get_contract(workload_name)["layers"]["organization"]["policy"]
                merged = _merge(self._contract_document(current_org), candidate, "organization contract")
            else:
                merged = _merge(self._contract_document(base), candidate, f"{scope} contract")
            jsonschema.Draft202012Validator(schema).validate(merged)
            if not merged.get("zones"):
                raise ApiError(422, "Contract must define at least one zone", "validation_failed")
        except (KeyError, ContractPolicyError, jsonschema.ValidationError) as exc:
            raise ApiError(422, str(exc), "validation_failed") from exc
        try:
            record = self.store.create_contract_proposal(
                contract_id="adop.zone-governance",
                content=candidate,
                workload_name=workload_name,
                domain=domain,
                project=project,
                actor=actor,
                expected_version=payload.get("expected_version")
                or projection["effective"].get("effective_hash"),
                required_approvals=2,
                scope=scope,
                scope_name=scope_name,
            )
        except VersionConflictError as exc:
            raise ApiError(409, str(exc), "version_conflict") from exc
        record["validation"] = {
            "valid": True,
            "scope": scope,
            "scope_name": scope_name,
            "effective_hash": self.repository.content_hash(
                json.dumps(merged, sort_keys=True, separators=(",", ":"))
            ),
        }
        return record

    @staticmethod
    def _contract_document(policy: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in policy.items()
            if key
            not in {
                "organization_version",
                "domain_version",
                "project_version",
                "effective_hash",
            }
        }

    def _validate_contract_candidate(
        self,
        *,
        workload_name: str,
        domain: str,
        project: str,
        scope: str,
        content: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Validate a contract and its resolved inherited result."""
        projection = self.repository.get_contract(
            workload_name,
            domain=domain if scope in {"domain", "project"} else None,
            project=project if scope == "project" else None,
        )
        if scope == "organization":
            base = {}
        elif scope == "domain":
            base = self.repository.get_contract(workload_name)["effective"]
        else:
            base = projection["effective"]
        schema = json.loads(
            (self.repository.root / "contracts/policies/zone_policy.schema.json").read_text(
                encoding="utf-8"
            )
        )
        candidate = self._contract_document(dict(content))
        candidate.setdefault("scope", scope)
        if candidate.get("scope") != scope:
            raise ApiError(
                422,
                "Contract content scope does not match the selected scope",
                "validation_failed",
            )
        jsonschema.Draft202012Validator(schema).validate(candidate)
        if not candidate.get("zones"):
            raise ApiError(422, "Contract must define at least one zone", "validation_failed")
        merged = (
            dict(candidate)
            if scope == "organization"
            else _merge(self._contract_document(base), candidate, f"{scope} contract")
        )
        jsonschema.Draft202012Validator(schema).validate(merged)
        return candidate, merged, projection

    def validate_contract(
        self,
        payload: dict[str, Any],
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _require_feature(identity, "contracts.propose")
        workload_name = payload.get("workload_name")
        content = payload.get("content")
        if not isinstance(workload_name, str) or not workload_name:
            raise ApiError(400, "workload_name is required", "invalid_body")
        if not isinstance(content, dict):
            raise ApiError(400, "content must be a contract object", "invalid_body")
        self._require_visible_workload(str(workload_name), identity)
        scope, scope_name = _scope(payload)
        self._validate_contract_scope_pair(
            domain=str(payload.get("domain") or "sales"),
            project=str(payload.get("project") or "orders"),
        )
        if not can_edit_contract_scope(identity, scope, scope_name):
            raise ApiError(
                403,
                "Only organization administrators can change organization/domain contracts; "
                "other users may change project contracts.",
                "contract_scope_forbidden",
            )
        domain = str(payload.get("domain") or "sales")
        project = str(payload.get("project") or "orders")
        try:
            candidate, merged, _ = self._validate_contract_candidate(
                workload_name=workload_name,
                domain=domain,
                project=project,
                scope=scope,
                content=content,
            )
        except (KeyError, ValueError, ContractPolicyError, jsonschema.ValidationError) as exc:
            raise ApiError(422, str(exc), "validation_failed") from exc
        return {
            "valid": True,
            "scope": scope,
            "scope_name": scope_name,
            "candidate": candidate,
            "effective_hash": self.repository.content_hash(
                json.dumps(merged, sort_keys=True, separators=(",", ":"))
            ),
        }

    def _validate_change_for_approval(self, record: dict[str, Any]) -> None:
        """Revalidate stored content immediately before recording approval."""
        if record.get("change_type") == "cedar_policy":
            try:
                validate_cedar_policy(
                    self.repository,
                    str(record["policy_id"]),
                    str(record.get("content") or ""),
                )
            except (KeyError, ValidationFailure) as exc:
                raise ApiError(422, str(exc), "validation_failed") from exc
            return
        if record.get("change_type") != "zone_contract":
            raise ApiError(422, "Unsupported change type", "validation_failed")
        try:
            _, merged, projection = self._validate_contract_candidate(
                workload_name=str(record.get("workload_name") or "customer_orders"),
                domain=str(record.get("domain") or "sales"),
                project=str(record.get("project") or "orders"),
                scope=str(record.get("scope") or "organization"),
                content=dict(record.get("content") or {}),
            )
        except (KeyError, ValueError, ContractPolicyError, jsonschema.ValidationError) as exc:
            raise ApiError(422, str(exc), "validation_failed") from exc
        expected = str(record.get("base_version") or "")
        if expected and expected != "repository":
            current_hash = str(projection.get("effective", {}).get("effective_hash") or "")
            if current_hash and current_hash != expected:
                raise ApiError(
                    409,
                    "Contract changed after this proposal was created; submit a new proposal.",
                    "version_conflict",
                )
        if not merged.get("zones"):
            raise ApiError(422, "Contract must define at least one zone", "validation_failed")

    def changes(self, identity: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        _require_feature(identity, "approvals.read")
        return [
            item
            for item in self.store.list_policy_proposals()
            if _record_scope_visible(identity, item)
        ]

    def change(
        self, change_id: str, identity: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        _require_feature(identity, "approvals.read")
        try:
            record = self.store.get_change(change_id)
        except ChangeNotFoundError as exc:
            raise ApiError(404, f"Change not found: {change_id}", "not_found") from exc
        if not _record_scope_visible(identity, record):
            raise ApiError(404, f"Change not found: {change_id}", "not_found")
        return record

    def approve_change(
        self,
        change_id: str,
        payload: dict[str, Any],
        actor: str,
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _require_feature(identity, "approvals.decide")
        try:
            record = self.store.get_change(change_id)
        except ChangeNotFoundError as exc:
            raise ApiError(404, f"Change not found: {change_id}", "not_found") from exc
        if not _record_scope_visible(identity, record):
            raise ApiError(404, f"Change not found: {change_id}", "not_found")
        allowed_types = APPROVABLE_CHANGE_TYPES.get(str((identity or {}).get("role") or ""))
        if allowed_types is not None and record.get("change_type") not in allowed_types:
            raise ApiError(
                403,
                f"Role {identity.get('role')} cannot decide {record.get('change_type')} changes",
                "approval_type_forbidden",
            )
        decision = payload.get("decision", "approve")
        self._validate_change_for_approval(record)
        try:
            return self.store.record_approval(
                change_id=change_id,
                actor=actor,
                decision=decision,
                comment=str(payload.get("comment", "")),
            )
        except ChangeNotFoundError as exc:
            raise ApiError(404, f"Change not found: {change_id}", "not_found") from exc
        except VersionConflictError as exc:
            raise ApiError(409, str(exc), "approval_conflict") from exc
        except ValueError as exc:
            raise ApiError(400, str(exc), "invalid_decision") from exc

    def audit(
        self,
        identity: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        _require_feature(identity, "audit.read")
        records = self.store.list_audit(limit)
        if identity and identity.get("role") == "org-admin":
            return records
        return [item for item in records if _record_scope_visible(identity, item)]

    def workspaces(self, identity: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if not identity:
            raise ApiError(401, "Authenticated identity is required", "unauthorized")
        records: list[dict[str, Any]] = [
            {
                "level": "organization",
                "name": "default",
                "label": "Acme organization",
                "parent_level": "",
                "parent_name": "",
                "system": True,
            }
        ]
        for item in identity.get("memberships", []) or []:
            if isinstance(item, dict):
                records.append(
                    {
                        "level": str(item.get("level") or ""),
                        "name": str(item.get("name") or ""),
                        "label": str(item.get("label") or ""),
                        "parent_level": "",
                        "parent_name": "",
                        "system": True,
                    }
                )
        for item in SYSTEM_WORKSPACES:
            if can_view_scope(identity, item["level"], item["name"]):
                records.append({**item, "system": True})
        for item in self.store.list_workspaces():
            level = str(item.get("level") or "")
            name = str(item.get("name") or "")
            if level and name and can_view_scope(identity, level, name):
                records.append(dict(item))
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for item in records:
            key = (item["level"], item["name"])
            unique[key] = item
        return sorted(
            unique.values(),
            key=lambda item: (
                {"organization": 0, "domain": 1, "project": 2}.get(item["level"], 9),
                item["name"],
            ),
        )

    def create_workspace(
        self,
        payload: dict[str, Any],
        actor: str,
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _require_feature(identity, "users.manage")
        if not identity or identity.get("role") != "org-admin":
            raise ApiError(
                403,
                "Only organization administrators can create workspaces",
                "workspace_create_forbidden",
            )
        level, name = _scope(
            {
                "scope": payload.get("level"),
                "scope_name": payload.get("name"),
            }
        )
        if level == "organization":
            raise ApiError(
                400,
                "The organization workspace is created with the organization",
                "invalid_scope",
            )
        label = str(payload.get("label") or name.replace("_", " ").title()).strip()
        if not label:
            raise ApiError(400, "Workspace label is required", "invalid_workspace")

        parent_value = str(payload.get("parent") or "").strip().lower()
        if level == "domain":
            parent_level, parent_name = "organization", "default"
        else:
            if not parent_value:
                raise ApiError(
                    400,
                    "Project workspaces require a parent domain",
                    "invalid_parent",
                )
            try:
                parent_level, parent_name = _scope(
                    {
                        "scope": parent_value.split("/", 1)[0],
                        "scope_name": parent_value.split("/", 1)[1],
                    }
                )
            except (IndexError, ApiError) as exc:
                if isinstance(exc, ApiError):
                    raise
                raise ApiError(
                    400,
                    "parent must be a workspace such as domain/sales",
                    "invalid_parent",
                ) from exc
            if parent_level != "domain":
                raise ApiError(
                    400,
                    "Project workspaces must belong to a domain",
                    "invalid_parent",
                )
            known = {
                (item["level"], item["name"])
                for item in self.workspaces(identity)
            }
            if (parent_level, parent_name) not in known:
                raise ApiError(
                    400,
                    f"Parent workspace {parent_level}/{parent_name} does not exist",
                    "invalid_parent",
                )
        try:
            return self.store.create_workspace(
                level=level,
                name=name,
                label=label,
                parent_level=parent_level,
                parent_name=parent_name,
                actor=actor,
            )
        except VersionConflictError as exc:
            raise ApiError(409, str(exc), "workspace_exists") from exc

    def users(self, identity: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        _require_feature(identity, "users.manage")
        if os.getenv("ADOP_ENV", "local").lower() != "local":
            # Production users are owned by the configured IdP. A directory
            # adapter will populate this endpoint without exposing local
            # fixtures in an AWS environment.
            return []
        return local_test_users()

    def record_workspace_switch(
        self,
        *,
        actor: str,
        identity: dict[str, Any] | None,
        scope: str,
        scope_name: str,
    ) -> dict[str, str]:
        if not identity or not can_view_scope(identity, scope, scope_name):
            raise ApiError(403, f"Identity cannot access {scope}/{scope_name}", "scope_forbidden")
        self.store.append_audit(
            {
                "event_type": "workspace_selected",
                "actor": actor,
                "scope": scope,
                "scope_name": scope_name,
                "workspace": f"{scope}/{scope_name}",
            }
        )
        return {"workspace": f"{scope}/{scope_name}", "status": "recorded"}


def _route(event: dict[str, Any]) -> tuple[str, list[str]]:
    path = event.get("rawPath") or event.get("path") or "/"
    path = urlsplit(path).path
    if path.startswith("/api"):
        path = path[4:] or "/"
    parts = [unquote(part) for part in path.strip("/").split("/") if part]
    return path, parts


def handler(
    event: dict[str, Any],
    context: Any = None,
    *,
    service: ControlPlaneService | None = None,
) -> dict[str, Any]:
    method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or "GET"
    ).upper()
    if method == "OPTIONS":
        return _json(204, {})
    service = service or ControlPlaneService()
    _, parts = _route(event)
    query = _query(event)
    try:
        if parts == ["v1", "auth", "config"] and method == "GET":
            return _json(200, auth_config())
        if parts == ["v1", "auth", "test-users"] and method == "GET":
            if os.getenv("ADOP_ENV", "local").lower() != "local":
                raise ApiError(404, "Route not found", "not_found")
            return _json(200, {"items": local_test_users()})
        if parts == ["v1", "auth", "me"] and method == "GET":
            identity = _identity_for_request(event, service)
            public_identity = (
                {key: value for key, value in identity.items() if not key.startswith("_")}
                if identity
                else None
            )
            return _json(
                200,
                {"authenticated": identity is not None, "identity": public_identity},
            )
        if parts == ["v1", "auth", "login"] and method == "POST":
            try:
                return _json(200, {"authenticated": True, "identity": local_login(_body(event))})
            except PermissionError as exc:
                raise ApiError(401, str(exc), "unauthorized") from exc
            except ValueError as exc:
                raise ApiError(400, str(exc), "invalid_login") from exc
        if parts == ["v1", "auth", "logout"] and method == "POST":
            return _json(204, {})

        identity = _identity_for_request(event, service)
        actor = _actor(event)
        if parts == ["v1", "auth", "workspace"] and method == "POST":
            scope, scope_name = _scope(payload=_body(event))
            return _json(
                200,
                service.record_workspace_switch(
                    actor=actor,
                    identity=identity,
                    scope=scope,
                    scope_name=scope_name,
                ),
            )
        if parts == ["v1", "workspaces"] and method == "GET":
            return _json(200, {"items": service.workspaces(identity)})
        if parts == ["v1", "workspaces"] and method == "POST":
            return _json(201, service.create_workspace(_body(event), actor, identity))
        if parts == ["v1", "health"] and method == "GET":
            return _json(200, {"status": "ok", "service": "adop-control-plane"})
        if parts == ["v1", "workloads"] and method == "GET":
            return _json(200, {"items": service.workloads(identity)})
        if len(parts) == 3 and parts[:2] == ["v1", "workloads"] and method == "GET":
            return _json(200, service.workload(parts[2], identity))
        if parts == ["v1", "connectors"] and method == "GET":
            return _json(200, {"items": service.connectors(identity)})
        if parts == ["v1", "connectors"] and method == "POST":
            return _json(201, service.create_connector(_body(event), actor, identity))
        if parts == ["v1", "connectors", "test"] and method == "POST":
            return _json(200, service.test_connector_draft(_body(event), identity))
        if parts == ["v1", "connectors", "test-all"] and method == "POST":
            return _json(200, {"items": service.test_all_connectors(identity)})
        if len(parts) == 3 and parts[:2] == ["v1", "connectors"] and method == "GET":
            return _json(200, service.connector(parts[2], identity))
        if len(parts) == 4 and parts[:2] == ["v1", "connectors"] and parts[3] == "test":
            if method == "POST":
                return _json(200, service.test_connector(parts[2], identity))
        if parts == ["v1", "contracts"] and method == "GET":
            return _json(
                200,
                service.contracts(
                    workload_name=query.get("workload", "customer_orders"),
                    domain=query.get("domain") or "sales",
                    project=query.get("project") or "orders",
                    identity=identity,
                ),
            )
        if len(parts) == 3 and parts[:2] == ["v1", "contracts"] and method == "GET":
            return _json(
                200,
                service.contracts(
                    workload_name=parts[2],
                    domain=query.get("domain") or "sales",
                    project=query.get("project") or "orders",
                    identity=identity,
                ),
            )
        if parts == ["v1", "contracts", "proposals"] and method == "POST":
            return _json(
                201,
                service.create_contract_proposal(
                    _body(event), actor, identity
                ),
            )
        if parts == ["v1", "contracts", "validate"] and method == "POST":
            return _json(200, service.validate_contract(_body(event), identity))
        if parts == ["v1", "policies"] and method == "GET":
            scope, scope_name = _scope(query=query)
            return _json(200, {"items": service.policies(scope=scope, scope_name=scope_name, identity=identity)})
        if len(parts) >= 3 and parts[:2] == ["v1", "policies"]:
            policy_tail = parts[2:]
            if method == "GET":
                scope, scope_name = _scope(query=query)
                return _json(
                    200,
                    service.policy(
                        "/".join(policy_tail),
                        scope=scope,
                        scope_name=scope_name,
                        identity=identity,
                    ),
                )
            if policy_tail[-1] == "validate" and method == "POST":
                policy_id = "/".join(policy_tail[:-1])
                return _json(
                    200,
                    service.validate_policy(
                        policy_id,
                        _body(event).get("content", ""),
                        identity,
                    ),
                )
            if policy_tail[-1] == "proposals" and method == "POST":
                policy_id = "/".join(policy_tail[:-1])
                return _json(
                    201,
                    service.create_policy_proposal(
                        policy_id,
                        _body(event),
                        actor,
                        identity,
                    ),
                )
        if parts == ["v1", "changes"] and method == "GET":
            return _json(200, {"items": service.changes(identity)})
        if len(parts) == 3 and parts[:2] == ["v1", "changes"] and method == "GET":
            return _json(200, service.change(parts[2], identity))
        if len(parts) == 4 and parts[:2] == ["v1", "changes"] and parts[3] == "approve":
            if method == "POST":
                return _json(200, service.approve_change(parts[2], _body(event), actor, identity))
        if parts == ["v1", "audit"] and method == "GET":
            return _json(200, {"items": service.audit(identity)})
        if parts == ["v1", "users"] and method == "GET":
            return _json(200, {"items": service.users(identity)})
        raise ApiError(404, "Route not found", "not_found")
    except ApiError as exc:
        return _json(exc.status, {"error": {"code": exc.code, "message": exc.message}})
    except Exception as exc:
        # Do not expose backend details or secret-bearing exception strings.
        if os.getenv("ADOP_API_DEBUG") == "1":
            return _json(500, {"error": {"code": "internal_error", "message": str(exc)}})
        return _json(
            500,
            {"error": {"code": "internal_error", "message": "Internal server error"}},
        )
