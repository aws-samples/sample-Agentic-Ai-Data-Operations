"""AWS-mode control-plane tests against moto (no real AWS).

Covers the DynamoDB store, the DynamoDB config snapshot provider, and Secrets
Manager connector-secret resolution.
"""

from __future__ import annotations

import json

import pytest

moto = pytest.importorskip("moto")
boto3 = pytest.importorskip("boto3")

from shared.control_plane import connectors  # noqa: E402
from shared.control_plane.config_provider import DynamoConfigProvider  # noqa: E402
from shared.control_plane.store import (  # noqa: E402
    ChangeNotFoundError,
    DynamoDBControlPlaneStore,
    VersionConflictError,
    create_store_from_environment,
)

REGION = "us-east-1"
TABLE = "adop-control-plane-test"


@pytest.fixture()
def aws(monkeypatch: pytest.MonkeyPatch):
    for key in ("AWS_PROFILE", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_REGION", REGION)
    with moto.mock_aws():
        boto3.client("dynamodb", region_name=REGION).create_table(
            TableName=TABLE,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


@pytest.fixture()
def store(aws):
    return DynamoDBControlPlaneStore(TABLE, region_name=REGION)


def _contract(store, actor="maya@example.com", threshold=0.97):
    return store.create_contract_proposal(
        contract_id="domain/sales",
        content={"zones": {"gold": {"minimum_quality_threshold": threshold}}},
        workload_name="customer_orders",
        domain="sales",
        project="orders",
        actor=actor,
        expected_version=None,
        required_approvals=2,
        scope="domain",
        scope_name="sales",
    )


def test_aws_mode_factory_builds_dynamodb_store(aws, monkeypatch):
    monkeypatch.setenv("ADOP_ENV", "aws")
    monkeypatch.setenv("ADOP_CONTROL_PLANE_BACKEND", "dynamodb")
    monkeypatch.setenv("ADOP_CONTROL_PLANE_TABLE", TABLE)
    assert isinstance(create_store_from_environment(), DynamoDBControlPlaneStore)


def test_contract_proposal_with_float_threshold_round_trips(store):
    record = _contract(store, threshold=0.97)
    loaded = store.get_change(record["change_id"])
    assert loaded["content"]["zones"]["gold"]["minimum_quality_threshold"] == 0.97
    json.dumps(loaded)  # API responses must be JSON-serializable


def test_policy_proposal_and_two_person_approval(store):
    change = store.create_policy_proposal(
        policy_id="guardrails/sec_003_pii_masking",
        content="forbid (principal, action, resource);",
        actor="maya@example.com",
        expected_version=None,
        required_approvals=2,
    )
    assert change["status"] == "pending_approval"
    first = store.record_approval(change_id=change["change_id"], actor="sara@example.com", decision="approve")
    assert first["status"] == "pending_approval"
    with pytest.raises(VersionConflictError):
        store.record_approval(change_id=change["change_id"], actor="sara@example.com", decision="approve")
    second = store.record_approval(change_id=change["change_id"], actor="lina@example.com", decision="approve")
    assert second["status"] == "approved_pending_git"
    assert store.get_change(change["change_id"])["status"] == "approved_pending_git"


def test_author_cannot_self_approve(store):
    change = _contract(store, actor="maya@example.com")
    with pytest.raises((VersionConflictError, PermissionError, ValueError)):
        store.record_approval(change_id=change["change_id"], actor="maya@example.com", decision="approve")


def test_rejected_change_is_terminal(store):
    change = _contract(store)
    store.record_approval(change_id=change["change_id"], actor="sara@example.com", decision="reject")
    with pytest.raises(VersionConflictError):
        store.record_approval(change_id=change["change_id"], actor="lina@example.com", decision="approve")


def test_unknown_change_raises(store):
    with pytest.raises(ChangeNotFoundError):
        store.get_change("chg-missing")


def test_audit_records_actor_and_returns_latest_first(store):
    for index in range(30):
        store.create_connector(
            name=f"conn{index}", provider="jdbc", metadata={"host": "db.internal"},
            secret_ref="adop/sales/conn", access_mode="read-only", actor="ops@example.com",
        )
    _contract(store, actor="maya@example.com")
    audit = store.list_audit(limit=5)
    assert len(audit) == 5
    assert audit[0]["event_type"] == "contract_proposal_created"
    assert audit[0]["actor"] == "maya@example.com"


def test_listing_paginates_past_one_scan_page(store):
    # moto honours Limit-style paging; write enough items to need several pages.
    blob = "x" * 350_000
    for index in range(4):
        store.create_connector(
            name=f"big{index}", provider="jdbc", metadata={"notes": blob},
            secret_ref="adop/sales/big", access_mode="read-only", actor="ops@example.com",
        )
    assert len(store.list_connectors()) == 4
    target = store.list_connectors()[-1]
    assert store.get_connector(target["connector_id"])["name"] == target["name"]


def test_connector_record_never_stores_secret_values(store):
    record = store.create_connector(
        name="sf", provider="snowflake", metadata={"account": "acme"},
        secret_ref="adop/sales/sf", access_mode="read-only", actor="ops@example.com",
    )
    raw = boto3.client("dynamodb", region_name=REGION).scan(TableName=TABLE)
    assert "password" not in json.dumps(raw).lower()
    assert record["secret_ref"] == "adop/sales/sf"


def test_dynamo_config_provider_current_pointer(aws):
    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    from decimal import Decimal

    table.put_item(Item={"PK": "WORKLOAD#customer_orders", "SK": "CONFIG#v2", "effective_hash": "abc",
                         "contracts": {"gold": {"minimum_quality_threshold": Decimal("0.95")}}})
    table.put_item(Item={"PK": "WORKLOAD#customer_orders", "SK": "CURRENT", "version": "v2"})
    snapshot = DynamoConfigProvider(TABLE, region_name=REGION).get_current("customer_orders")
    assert snapshot.version == "v2"
    assert snapshot.effective_hash == "abc"
    assert snapshot.source == "dynamodb"
    json.dumps(snapshot.contracts)
    with pytest.raises(KeyError):
        DynamoConfigProvider(TABLE, region_name=REGION).get_current("missing")


def test_secrets_manager_connector_secret_resolution(aws):
    client = boto3.client("secretsmanager", region_name=REGION)
    client.create_secret(Name="adop/sales/sf", SecretString=json.dumps({"username": "u", "password": "p"}))
    assert connectors._secret_value("adop/sales/sf")["username"] == "u"
    client.create_secret(Name="adop/sales/bad", SecretString="not-json")
    with pytest.raises(connectors.ConnectorTestError) as bad:
        connectors._secret_value("adop/sales/bad")
    assert bad.value.code == "SECRET_FORMAT_INVALID"
    with pytest.raises(connectors.ConnectorTestError) as missing:
        connectors._secret_value("adop/sales/missing")
    assert missing.value.code == "SECRET_UNAVAILABLE"
    with pytest.raises(connectors.ConnectorTestError) as invalid:
        connectors._secret_value("plaintext-password")
    assert invalid.value.code == "INVALID_SECRET_REFERENCE"


def test_concurrent_approval_is_rejected(store):
    change = _contract(store, actor="maya@example.com")
    stale = store.get_change(change["change_id"])
    store.record_approval(change_id=change["change_id"], actor="sara@example.com", decision="approve")
    original = store.get_change
    store.get_change = lambda change_id: stale  # simulate a second writer holding a stale read
    try:
        with pytest.raises(VersionConflictError, match="concurrently"):
            store.record_approval(change_id=change["change_id"], actor="lina@example.com", decision="approve")
    finally:
        store.get_change = original
    assert len(store.get_change(change["change_id"])["approvals"]) == 1


def test_duplicate_connector_name_rejected_like_json_store(store):
    kwargs = dict(name="dup", provider="jdbc", metadata={}, secret_ref="adop/x", access_mode="read-only", actor="a@example.com")
    store.create_connector(**kwargs)
    with pytest.raises(VersionConflictError, match="already exists"):
        store.create_connector(**kwargs)
