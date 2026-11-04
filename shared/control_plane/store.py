"""Versioned control-plane storage.

The JSON store is the local-development implementation. The DynamoDB store
uses the same record model so the API and UI do not change when deployed.
    Secrets and connection metadata are deliberately represented only by
    references in connector records.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


class VersionConflictError(ValueError):
    """Raised when an update is based on a stale version."""


class ChangeNotFoundError(KeyError):
    """Raised when an approval/change identifier is unknown."""


SELF_APPROVAL_MESSAGE = "The author of a change cannot approve it; a second person must approve"


def _to_dynamo(value: Any) -> Any:
    """DynamoDB (boto3 resource API) rejects floats; store them as Decimal."""
    from decimal import Decimal

    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _to_dynamo(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_dynamo(item) for item in value]
    return value


def _from_dynamo(value: Any) -> Any:
    """Convert DynamoDB Decimals back to int/float so records stay JSON-serializable."""
    from decimal import Decimal

    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _from_dynamo(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_dynamo(item) for item in value]
    return value


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class ControlPlaneStore(Protocol):
    def list_workspaces(self) -> list[dict[str, Any]]: ...

    def create_workspace(
        self,
        *,
        level: str,
        name: str,
        label: str,
        parent_level: str,
        parent_name: str,
        actor: str,
    ) -> dict[str, Any]: ...

    def list_policy_proposals(self) -> list[dict[str, Any]]: ...

    def list_connectors(self) -> list[dict[str, Any]]: ...

    def create_connector(
        self,
        *,
        name: str,
        provider: str,
        metadata: dict[str, Any],
        secret_ref: str,
        access_mode: str,
        actor: str,
        scope: str = "organization",
        scope_name: str = "default",
    ) -> dict[str, Any]: ...

    def get_connector(self, connector_id: str) -> dict[str, Any]: ...

    def update_connector_health(
        self, connector_id: str, health: dict[str, Any]
    ) -> dict[str, Any]: ...

    def create_policy_proposal(
        self,
        *,
        policy_id: str,
        content: str,
        actor: str,
        expected_version: str | None,
        required_approvals: int,
        scope: str = "organization",
        scope_name: str = "default",
    ) -> dict[str, Any]: ...

    def create_contract_proposal(
        self,
        *,
        contract_id: str,
        content: dict[str, Any],
        workload_name: str,
        domain: str,
        project: str,
        actor: str,
        expected_version: str | None,
        required_approvals: int,
        scope: str,
        scope_name: str,
    ) -> dict[str, Any]: ...

    def get_change(self, change_id: str) -> dict[str, Any]: ...

    def attach_external_reference(
        self, change_id: str, reference: dict[str, Any]
    ) -> dict[str, Any]: ...

    def record_approval(
        self,
        *,
        change_id: str,
        actor: str,
        decision: str,
        comment: str = "",
    ) -> dict[str, Any]: ...

    def append_audit(self, event: dict[str, Any]) -> None: ...

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]: ...


def _empty_state() -> dict[str, Any]:
    return {"workspaces": {}, "policy_proposals": {}, "connectors": {}, "audit": []}


class JsonControlPlaneStore:
    """Atomic JSON persistence used by the local server and unit tests."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return _empty_state()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Control-plane store is unreadable: {self.path}") from exc
        if not isinstance(value, dict):
            raise RuntimeError("Control-plane store must contain a JSON object")
        value.setdefault("workspaces", {})
        value.setdefault("policy_proposals", {})
        value.setdefault("connectors", {})
        value.setdefault("audit", [])
        return value

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._read()["workspaces"].values())
        return sorted(records, key=lambda item: (item.get("level", ""), item.get("name", "")))

    def create_workspace(
        self,
        *,
        level: str,
        name: str,
        label: str,
        parent_level: str,
        parent_name: str,
        actor: str,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            if any(
                item.get("level") == level and item.get("name") == name
                for item in state["workspaces"].values()
            ):
                raise VersionConflictError(f"Workspace {level}/{name} already exists")
            record = {
                "workspace_id": new_id("ws"),
                "level": level,
                "name": name,
                "label": label,
                "parent_level": parent_level,
                "parent_name": parent_name,
                "created_by": actor,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            state["workspaces"][record["workspace_id"]] = record
            self._append_audit_locked(
                state,
                {
                    "event_type": "workspace_created",
                    "actor": actor,
                    "workspace": f"{level}/{name}",
                    "scope": level,
                    "scope_name": name,
                },
            )
            self._write(state)
            return dict(record)

    def list_policy_proposals(self) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._read()["policy_proposals"].values())
        return sorted(records, key=lambda item: item["created_at"], reverse=True)

    def list_connectors(self) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._read()["connectors"].values())
        return sorted(records, key=lambda item: item["created_at"])

    def create_connector(
        self,
        *,
        name: str,
        provider: str,
        metadata: dict[str, Any],
        secret_ref: str,
        access_mode: str,
        actor: str,
        scope: str = "organization",
        scope_name: str = "default",
    ) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            if any(item["name"] == name for item in state["connectors"].values()):
                raise VersionConflictError(f"Connector {name} already exists")
            record = {
                "connector_id": new_id("conn"),
                "name": name,
                "type": provider,
                "metadata": dict(metadata),
                "secret_ref": secret_ref,
                "access_mode": access_mode,
                "scope": scope,
                "scope_name": scope_name,
                "status": "not_tested",
                "health": None,
                "created_by": actor,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            state["connectors"][record["connector_id"]] = record
            self._append_audit_locked(
                state,
                {
                    "event_type": "connector_created",
                    "actor": actor,
                    "connector_id": record["connector_id"],
                    "connector_name": name,
                },
            )
            self._write(state)
            return dict(record)

    def get_connector(self, connector_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._read()["connectors"].get(connector_id)
        if not record:
            raise ChangeNotFoundError(connector_id)
        return dict(record)

    def update_connector_health(
        self, connector_id: str, health: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            record = state["connectors"].get(connector_id)
            if not record:
                raise ChangeNotFoundError(connector_id)
            record["health"] = dict(health)
            record["status"] = health.get("status", "not_tested")
            record["updated_at"] = utc_now()
            self._append_audit_locked(
                state,
                {
                    "event_type": "connector_health_checked",
                    "actor": "control-plane",
                    "connector_id": connector_id,
                    "status": record["status"],
                    "error_code": health.get("error_code"),
                },
            )
            self._write(state)
            return dict(record)

    def create_policy_proposal(
        self,
        *,
        policy_id: str,
        content: str,
        actor: str,
        expected_version: str | None,
        required_approvals: int,
        scope: str = "organization",
        scope_name: str = "default",
    ) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            proposals = state["policy_proposals"]
            current = next(
                (
                    item
                    for item in proposals.values()
                    if item.get("policy_id") == policy_id
                    and item.get("scope", "organization") == scope
                    and item.get("scope_name", "default") == scope_name
                    and item["status"] in {"pending_approval", "approved_pending_git"}
                ),
                None,
            )
            if current and expected_version and current["base_version"] != expected_version:
                raise VersionConflictError(
                    f"Policy {policy_id} changed after version {expected_version}"
                )
            record = {
                "change_id": new_id("chg"),
                "change_type": "cedar_policy",
                "policy_id": policy_id,
                "subject_id": policy_id,
                "scope": scope,
                "scope_name": scope_name,
                "content": content,
                "base_version": expected_version or "repository",
                "version": new_id("v"),
                "status": "pending_approval",
                "required_approvals": max(1, required_approvals),
                "approvals": [],
                "created_by": actor,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            proposals[record["change_id"]] = record
            self._append_audit_locked(
                state,
                {
                    "event_type": "policy_proposal_created",
                    "actor": actor,
                    "change_id": record["change_id"],
                    "policy_id": policy_id,
                    "scope": scope,
                    "scope_name": scope_name,
                },
            )
            self._write(state)
            return dict(record)

    def create_contract_proposal(
        self,
        *,
        contract_id: str,
        content: dict[str, Any],
        workload_name: str,
        domain: str,
        project: str,
        actor: str,
        expected_version: str | None,
        required_approvals: int,
        scope: str,
        scope_name: str,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            proposals = state["policy_proposals"]
            current = next(
                (
                    item
                    for item in proposals.values()
                    if item.get("change_type") == "zone_contract"
                    and item.get("contract_id") == contract_id
                    and item.get("scope") == scope
                    and item.get("scope_name") == scope_name
                    and item["status"] in {"pending_approval", "approved_pending_git"}
                ),
                None,
            )
            if current and expected_version and current["base_version"] != expected_version:
                raise VersionConflictError(
                    f"Contract {contract_id} changed after version {expected_version}"
                )
            record = {
                "change_id": new_id("chg"),
                "change_type": "zone_contract",
                "contract_id": contract_id,
                "subject_id": contract_id,
                "workload_name": workload_name,
                "domain": domain,
                "project": project,
                "scope": scope,
                "scope_name": scope_name,
                "content": content,
                "base_version": expected_version or "repository",
                "version": new_id("v"),
                "status": "pending_approval",
                "required_approvals": max(1, required_approvals),
                "approvals": [],
                "created_by": actor,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            proposals[record["change_id"]] = record
            self._append_audit_locked(
                state,
                {
                    "event_type": "contract_proposal_created",
                    "actor": actor,
                    "change_id": record["change_id"],
                    "contract_id": contract_id,
                    "scope": scope,
                    "scope_name": scope_name,
                },
            )
            self._write(state)
            return dict(record)

    def get_change(self, change_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._read()["policy_proposals"].get(change_id)
        if not record:
            raise ChangeNotFoundError(change_id)
        return dict(record)

    def attach_external_reference(
        self, change_id: str, reference: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            record = state["policy_proposals"].get(change_id)
            if not record:
                raise ChangeNotFoundError(change_id)
            record["external_reference"] = dict(reference)
            record["updated_at"] = utc_now()
            self._append_audit_locked(
                state,
                {
                    "event_type": "external_change_linked",
                    "actor": "control-plane",
                    "change_id": change_id,
                    "subject_id": record.get("subject_id")
                    or record.get("policy_id")
                    or record.get("contract_id"),
                },
            )
            self._write(state)
            return dict(record)

    def record_approval(
        self,
        *,
        change_id: str,
        actor: str,
        decision: str,
        comment: str = "",
    ) -> dict[str, Any]:
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        with self._lock:
            state = self._read()
            record = state["policy_proposals"].get(change_id)
            if not record:
                raise ChangeNotFoundError(change_id)
            if record.get("status") in {"rejected", "applied"}:
                raise VersionConflictError(
                    f"Change {change_id} is already {record['status']}"
                )
            if decision == "approve" and actor == record.get("created_by"):
                raise VersionConflictError(SELF_APPROVAL_MESSAGE)
            if any(item["actor"] == actor for item in record["approvals"]):
                raise VersionConflictError("An actor can approve a change only once")
            approval = {
                "actor": actor,
                "decision": decision,
                "comment": comment,
                "created_at": utc_now(),
            }
            record["approvals"].append(approval)
            if decision == "reject":
                record["status"] = "rejected"
            elif len(
                [item for item in record["approvals"] if item["decision"] == "approve"]
            ) >= record["required_approvals"]:
                record["status"] = "approved_pending_git"
            record["updated_at"] = utc_now()
            self._append_audit_locked(
                state,
                {
                    "event_type": f"policy_{decision}d",
                    "actor": actor,
                    "change_id": change_id,
                    "subject_id": record.get("subject_id")
                    or record.get("policy_id")
                    or record.get("contract_id"),
                },
            )
            self._write(state)
            return dict(record)

    def append_audit(self, event: dict[str, Any]) -> None:
        with self._lock:
            state = self._read()
            self._append_audit_locked(state, event)
            self._write(state)

    def _append_audit_locked(
        self, state: dict[str, Any], event: dict[str, Any]
    ) -> None:
        state["audit"].append({"event_id": new_id("evt"), "timestamp": utc_now(), **event})

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._read()["audit"])
        return list(reversed(records[-max(1, limit) :]))


class DynamoDBControlPlaneStore:
    """DynamoDB implementation.

    boto3 is imported only when this backend is selected. The table uses
    ``PK``/``SK`` keys and stores immutable proposal records. A production
    deployment should provision a GSI for change status and audit queries.
    """

    def __init__(self, table_name: str, region_name: str | None = None):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "DynamoDB backend requires boto3; install the avp/control-plane extra"
            ) from exc
        self.table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    def _scan(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Scan every page; a single Scan call stops at 1 MB."""
        items: list[dict[str, Any]] = []
        while True:
            response = self.table.scan(**kwargs)
            items.extend(_from_dynamo(item) for item in response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return items
            kwargs["ExclusiveStartKey"] = last_key

    def _put(self, item: dict[str, Any], **kwargs: Any) -> None:
        self.table.put_item(Item=_to_dynamo(item), **kwargs)

    def list_workspaces(self) -> list[dict[str, Any]]:
        items = self._scan(
            FilterExpression="begins_with(SK, :prefix)",
            ExpressionAttributeValues={":prefix": "WORKSPACE#"},
        )
        return sorted(items, key=lambda item: (item.get("level", ""), item.get("name", "")))

    def create_workspace(
        self,
        *,
        level: str,
        name: str,
        label: str,
        parent_level: str,
        parent_name: str,
        actor: str,
    ) -> dict[str, Any]:
        record = {
            "workspace_id": new_id("ws"),
            "level": level,
            "name": name,
            "label": label,
            "parent_level": parent_level,
            "parent_name": parent_name,
            "created_by": actor,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "PK": f"WORKSPACE#{level}#{name}",
            "SK": "WORKSPACE",
        }
        try:
            self._put(
                record,
                ConditionExpression="attribute_not_exists(PK)",
            )
        except Exception as exc:
            if "ConditionalCheckFailed" in str(exc):
                raise VersionConflictError(
                    f"Workspace {level}/{name} already exists"
                ) from exc
            raise
        self.append_audit(
            {
                "event_type": "workspace_created",
                "actor": actor,
                "workspace": f"{level}/{name}",
                "scope": level,
                "scope_name": name,
            }
        )
        return record

    def list_policy_proposals(self) -> list[dict[str, Any]]:
        items = self._scan(
            FilterExpression="begins_with(SK, :prefix)",
            ExpressionAttributeValues={":prefix": "CHANGE#"},
        )
        return sorted(
            items,
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )

    def list_connectors(self) -> list[dict[str, Any]]:
        items = self._scan(
            FilterExpression="begins_with(SK, :prefix)",
            ExpressionAttributeValues={":prefix": "CONNECTOR#"},
        )
        return sorted(items, key=lambda item: item.get("created_at", ""))

    def create_connector(
        self,
        *,
        name: str,
        provider: str,
        metadata: dict[str, Any],
        secret_ref: str,
        access_mode: str,
        actor: str,
        scope: str = "organization",
        scope_name: str = "default",
    ) -> dict[str, Any]:
        from boto3.dynamodb.conditions import Key

        existing = self.table.query(
            KeyConditionExpression=Key("PK").eq(f"CONNECTOR#{name}") & Key("SK").begins_with("CONNECTOR#"),
            Limit=1,
        )
        if existing.get("Items"):
            raise VersionConflictError(f"Connector {name} already exists")
        record = {
            "connector_id": new_id("conn"),
            "name": name,
            "type": provider,
            "metadata": metadata,
            "secret_ref": secret_ref,
            "access_mode": access_mode,
            "scope": scope,
            "scope_name": scope_name,
            "status": "not_tested",
            "health": None,
            "created_by": actor,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "PK": f"CONNECTOR#{name}",
            "SK": f"CONNECTOR#{utc_now()}#{uuid.uuid4().hex}",
        }
        self._put(
            record,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
        self.append_audit(
            {
                "event_type": "connector_created",
                "actor": actor,
                "connector_id": record["connector_id"],
                "connector_name": name,
            }
        )
        return record

    def get_connector(self, connector_id: str) -> dict[str, Any]:
        items = self._scan(
            FilterExpression="connector_id = :connector_id AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={":connector_id": connector_id, ":prefix": "CONNECTOR#"},
        )
        if not items:
            raise ChangeNotFoundError(connector_id)
        return items[0]

    def update_connector_health(
        self, connector_id: str, health: dict[str, Any]
    ) -> dict[str, Any]:
        record = self.get_connector(connector_id)
        self.table.update_item(
            Key={"PK": record["PK"], "SK": record["SK"]},
            UpdateExpression="SET health = :health, #status = :status, updated_at = :updated",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues=_to_dynamo({
                ":health": health,
                ":status": health.get("status", "not_tested"),
                ":updated": utc_now(),
            }),
        )
        updated = dict(record)
        updated.update(
            {
                "health": health,
                "status": health.get("status", "not_tested"),
                "updated_at": utc_now(),
            }
        )
        self.append_audit(
            {
                "event_type": "connector_health_checked",
                "actor": "control-plane",
                "connector_id": connector_id,
                "status": updated["status"],
                "error_code": health.get("error_code"),
            }
        )
        return updated

    def create_policy_proposal(
        self,
        *,
        policy_id: str,
        content: str,
        actor: str,
        expected_version: str | None,
        required_approvals: int,
        scope: str = "organization",
        scope_name: str = "default",
    ) -> dict[str, Any]:
        record = {
            "change_id": new_id("chg"),
            "change_type": "cedar_policy",
            "policy_id": policy_id,
            "subject_id": policy_id,
            "scope": scope,
            "scope_name": scope_name,
            "content": content,
            "base_version": expected_version or "repository",
            "version": new_id("v"),
            "status": "pending_approval",
            "required_approvals": max(1, required_approvals),
            "approvals": [],
            "created_by": actor,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "PK": f"POLICY#{policy_id}",
            "SK": f"CHANGE#{utc_now()}#{uuid.uuid4().hex}",
        }
        self._put(
            record,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
        self.append_audit(
            {
                "event_type": "policy_proposal_created",
                "actor": actor,
                "change_id": record["change_id"],
                "policy_id": policy_id,
                "scope": scope,
                "scope_name": scope_name,
            }
        )
        return record

    def create_contract_proposal(
        self,
        *,
        contract_id: str,
        content: dict[str, Any],
        workload_name: str,
        domain: str,
        project: str,
        actor: str,
        expected_version: str | None,
        required_approvals: int,
        scope: str,
        scope_name: str,
    ) -> dict[str, Any]:
        record = {
            "change_id": new_id("chg"),
            "change_type": "zone_contract",
            "contract_id": contract_id,
            "subject_id": contract_id,
            "workload_name": workload_name,
            "domain": domain,
            "project": project,
            "scope": scope,
            "scope_name": scope_name,
            "content": content,
            "base_version": expected_version or "repository",
            "version": new_id("v"),
            "status": "pending_approval",
            "required_approvals": max(1, required_approvals),
            "approvals": [],
            "created_by": actor,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "PK": f"CONTRACT#{contract_id}",
            "SK": f"CHANGE#{utc_now()}#{uuid.uuid4().hex}",
        }
        self._put(
            record,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
        self.append_audit(
            {
                "event_type": "contract_proposal_created",
                "actor": actor,
                "change_id": record["change_id"],
                "contract_id": contract_id,
                "scope": scope,
                "scope_name": scope_name,
            }
        )
        return record

    def get_change(self, change_id: str) -> dict[str, Any]:
        items = self._scan(
            FilterExpression="change_id = :change_id AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={":change_id": change_id, ":prefix": "CHANGE#"},
        )
        if not items:
            raise ChangeNotFoundError(change_id)
        return items[0]

    def record_approval(
        self,
        *,
        change_id: str,
        actor: str,
        decision: str,
        comment: str = "",
    ) -> dict[str, Any]:
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        record = self.get_change(change_id)
        if record.get("status") in {"rejected", "applied"}:
            raise VersionConflictError(
                f"Change {change_id} is already {record['status']}"
            )
        if decision == "approve" and actor == record.get("created_by"):
            raise VersionConflictError(SELF_APPROVAL_MESSAGE)
        approvals = list(record.get("approvals", []))
        if any(item["actor"] == actor for item in approvals):
            raise VersionConflictError("An actor can approve a change only once")
        approvals.append(
            {
                "actor": actor,
                "decision": decision,
                "comment": comment,
                "created_at": utc_now(),
            }
        )
        status = "rejected" if decision == "reject" else "pending_approval"
        if decision == "approve" and len(
            [item for item in approvals if item["decision"] == "approve"]
        ) >= int(record["required_approvals"]):
            status = "approved_pending_git"
        try:
            self._update_approvals(record, approvals, status)
        except self.table.meta.client.exceptions.ConditionalCheckFailedException as exc:
            raise VersionConflictError(
                f"Change {change_id} was modified concurrently; reload and retry"
            ) from exc
        updated = dict(record)
        updated.update({"approvals": approvals, "status": status})
        self.append_audit(
            {
                "event_type": f"policy_{decision}d",
                "actor": actor,
                "change_id": change_id,
                "subject_id": record.get("subject_id")
                or record.get("policy_id")
                or record.get("contract_id"),
            }
        )
        return updated

    def _update_approvals(
        self, record: dict[str, Any], approvals: list[dict[str, Any]], status: str
    ) -> None:
        self.table.update_item(
            Key={"PK": record["PK"], "SK": record["SK"]},
            UpdateExpression="SET approvals = :approvals, #status = :status, updated_at = :updated",
            ConditionExpression="updated_at = :previous",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues=_to_dynamo({
                ":approvals": approvals,
                ":status": status,
                ":updated": utc_now(),
                ":previous": record.get("updated_at"),
            }),
        )

    def attach_external_reference(
        self, change_id: str, reference: dict[str, Any]
    ) -> dict[str, Any]:
        record = self.get_change(change_id)
        self.table.update_item(
            Key={"PK": record["PK"], "SK": record["SK"]},
            UpdateExpression="SET external_reference = :reference, updated_at = :updated",
            ExpressionAttributeValues=_to_dynamo({
                ":reference": reference,
                ":updated": utc_now(),
            }),
        )
        updated = dict(record)
        updated["external_reference"] = reference
        return updated

    def append_audit(self, event: dict[str, Any]) -> None:
        timestamp = utc_now()
        self._put(
            {
                "PK": "AUDIT",
                "SK": f"{timestamp}#{uuid.uuid4().hex}",
                "event_id": new_id("evt"),
                "timestamp": timestamp,
                **event,
            }
        )

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key

        response = self.table.query(
            KeyConditionExpression=Key("PK").eq("AUDIT"),
            ScanIndexForward=False,
            Limit=max(1, limit),
        )
        return [_from_dynamo(item) for item in response.get("Items", [])]


def create_store_from_environment() -> ControlPlaneStore:
    env = os.getenv("ADOP_ENV", "local").lower()
    backend = os.getenv("ADOP_CONTROL_PLANE_BACKEND", "json").lower()
    if env != "local" and backend == "json":
        # Fail closed: a shared/AWS deployment must never fall back to a local file,
        # or approved policies and connectors would silently diverge from DynamoDB.
        raise RuntimeError(
            f"ADOP_ENV={env} requires ADOP_CONTROL_PLANE_BACKEND=dynamodb and "
            "ADOP_CONTROL_PLANE_TABLE; the local JSON store is only allowed when ADOP_ENV=local"
        )
    if backend == "dynamodb":
        table_name = os.getenv("ADOP_CONTROL_PLANE_TABLE")
        if not table_name:
            raise RuntimeError("ADOP_CONTROL_PLANE_TABLE is required for DynamoDB backend")
        return DynamoDBControlPlaneStore(
            table_name,
            region_name=os.getenv("AWS_REGION"),
        )
    if backend != "json":
        raise RuntimeError(f"Unsupported ADOP_CONTROL_PLANE_BACKEND: {backend}")
    return JsonControlPlaneStore(
        os.getenv("ADOP_CONTROL_PLANE_FILE", "/tmp/adop-control-plane.json")
    )
