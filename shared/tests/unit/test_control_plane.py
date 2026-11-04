from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.auth import auth_config, identity_from_event
from api.control_plane import ApiError, ControlPlaneService, handler
from shared.control_plane.authorization import has_feature
from shared.control_plane import connectors
from shared.control_plane.config_provider import FileConfigProvider
from shared.control_plane.repository import RepositoryProjection
from shared.control_plane.store import JsonControlPlaneStore


ROOT = Path(__file__).resolve().parents[3]


def _service(tmp_path: Path) -> ControlPlaneService:
    return ControlPlaneService(
        repository=RepositoryProjection(ROOT),
        store=JsonControlPlaneStore(tmp_path / "control-plane.json"),
    )


def _event(method: str, path: str, body: dict | None = None, actor: str = "test-user") -> dict:
    return {
        "httpMethod": method,
        "rawPath": path,
        "headers": {"x-adop-actor": actor, "x-adop-role": "org-admin"},
        "body": json.dumps(body) if body is not None else None,
    }


def test_workload_projection_reads_authoritative_run_context(tmp_path: Path):
    response = handler(
        _event("GET", "/api/v1/workloads/customer_orders"),
        service=_service(tmp_path),
    )

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    assert payload["run_id"] == "regen-20261023-customer-orders"
    assert payload["phase"] == "4.3"
    assert payload["schedule_timezone"] == "America/New_York"


def test_local_test_login_returns_identity_without_creating_a_user(tmp_path: Path):
    login = handler(
        _event(
            "POST",
            "/api/v1/auth/login",
            {
                "name": "Maya Chen",
                "email": "maya.chen@example.com",
                "role": "domain-owner",
            },
        ),
        service=_service(tmp_path),
    )
    assert login["statusCode"] == 200
    identity = json.loads(login["body"])["identity"]
    assert identity["provider"] == "local-test"
    assert identity["test_only"] is True
    assert identity["scopes"] == [
        "organization/default",
        "domain/*",
        "project/*",
    ]

    me = handler(
        _event(
            "GET",
            "/api/v1/auth/me",
            actor="maya.chen@example.com",
        ),
        service=_service(tmp_path),
    )
    assert me["statusCode"] == 200
    assert json.loads(me["body"])["authenticated"] is True


def test_project_membership_soft_isolates_workloads_and_scopes(tmp_path: Path):
    service = _service(tmp_path)
    project_headers = {"x-adop-actor": "oliver.orders@example.com"}

    workloads = handler(
        {
            **_event("GET", "/api/v1/workloads"),
            "headers": project_headers,
        },
        service=service,
    )
    assert workloads["statusCode"] == 200
    assert [item["name"] for item in json.loads(workloads["body"])["items"]] == [
        "customer_orders"
    ]

    hidden_workload = handler(
        {
            **_event("GET", "/api/v1/workloads/claims"),
            "headers": project_headers,
        },
        service=service,
    )
    assert hidden_workload["statusCode"] == 404

    visible_contract = handler(
        {
            **_event(
                "GET",
                "/api/v1/contracts?workload=customer_orders&domain=sales&project=orders",
            ),
            "headers": project_headers,
        },
        service=service,
    )
    assert visible_contract["statusCode"] == 200

    hidden_policy = handler(
        {
            **_event("GET", "/api/v1/policies?scope=domain&scope_name=sales"),
            "headers": project_headers,
        },
        service=service,
    )
    assert hidden_policy["statusCode"] == 403


def test_selected_workspace_filters_admin_workload_views(tmp_path: Path):
    service = _service(tmp_path)
    claims_headers = {
        "x-adop-actor": "hcherian@example.com",
        "x-adop-role": "org-admin",
        "x-adop-workspace": "project/claims",
    }
    response = handler(
        {
            **_event("GET", "/api/v1/workloads"),
            "headers": claims_headers,
        },
        service=service,
    )
    assert response["statusCode"] == 200
    assert [item["name"] for item in json.loads(response["body"])["items"]] == []

    orders_headers = {**claims_headers, "x-adop-workspace": "project/orders"}
    response = handler(
        {
            **_event("GET", "/api/v1/workloads"),
            "headers": orders_headers,
        },
        service=service,
    )
    assert response["statusCode"] == 200
    assert [item["name"] for item in json.loads(response["body"])["items"]] == [
        "customer_orders"
    ]

    hidden_contract = handler(
        {
            **_event(
                "GET",
                "/api/v1/contracts?workload=customer_orders&domain=sales&project=orders",
            ),
            "headers": claims_headers,
        },
        service=service,
    )
    assert hidden_contract["statusCode"] == 404

    service.store.create_contract_proposal(
        contract_id="adop.zone-governance",
        content={"scope": "project", "zones": {}},
        workload_name="customer_orders",
        domain="sales",
        project="orders",
        actor="oliver.orders@example.com",
        expected_version=None,
        required_approvals=2,
        scope="project",
        scope_name="orders",
    )
    changes = handler(
        {
            **_event("GET", "/api/v1/changes"),
            "headers": claims_headers,
        },
        service=service,
    )
    assert changes["statusCode"] == 200
    assert json.loads(changes["body"])["items"] == []


def test_local_cross_origin_identity_headers_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ADOP_ENV", "local")
    monkeypatch.delenv("ADOP_LOCAL_ALLOWED_ORIGINS", raising=False)
    response = handler(
        {
            **_event("GET", "/api/v1/workloads"),
            "headers": {
                "origin": "http://evil.example",
                "x-adop-actor": "hcherian@example.com",
                "x-adop-role": "org-admin",
                "x-adop-groups": "adop-org-admins",
            },
        },
        service=_service(tmp_path),
    )
    assert response["statusCode"] == 403
    assert json.loads(response["body"])["error"]["code"] == "origin_forbidden"


def test_contract_writes_are_project_scoped_for_non_admins(tmp_path: Path):
    service = _service(tmp_path)
    domain_owner = {
        **_event(
            "POST",
            "/api/v1/contracts/proposals",
            {
                "workload_name": "customer_orders",
                "scope": "domain",
                "scope_name": "sales",
                "content": {},
            },
        ),
        "headers": {
            "x-adop-actor": "sara.sales@example.com",
            "x-adop-role": "domain-owner",
            "x-adop-workspace": "domain/sales",
        },
    }
    denied = handler(domain_owner, service=service)
    assert denied["statusCode"] == 403
    assert json.loads(denied["body"])["error"]["code"] == "contract_scope_forbidden"

    project_user = {
        **_event(
            "POST",
            "/api/v1/contracts/proposals",
            {
                "workload_name": "customer_orders",
                "scope": "project",
                "scope_name": "orders",
                "content": {},
            },
        ),
        "headers": {
            "x-adop-actor": "oliver.orders@example.com",
            "x-adop-role": "project-user",
            "x-adop-groups": "adop-project-orders-users",
            "x-adop-workspace": "project/orders",
        },
    }
    project_response = handler(project_user, service=service)
    assert project_response["statusCode"] == 422
    assert json.loads(project_response["body"])["error"]["code"] == "validation_failed"

    valid_content = dict(
        service.repository.get_contract(
            "customer_orders",
            domain="sales",
            project="orders",
        )["layers"]["organization"]["policy"]
    )
    valid_content["scope"] = "project"
    validation = handler(
        {
            **project_user,
            "rawPath": "/api/v1/contracts/validate",
            "body": json.dumps(
                {
                    "workload_name": "customer_orders",
                    "domain": "sales",
                    "project": "orders",
                    "scope": "project",
                    "scope_name": "orders",
                    "content": valid_content,
                }
            ),
        },
        service=service,
    )
    assert validation["statusCode"] == 200
    assert json.loads(validation["body"])["valid"] is True


def test_auth_config_is_safe_to_expose(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ADOP_LOCAL_TEST_PASSWORD", raising=False)
    response = handler(
        _event("GET", "/api/v1/auth/config"),
        service=_service(tmp_path),
    )
    payload = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert payload["mode"] == "local"
    assert payload["local_test_password_required"] is False
    assert "secret" not in json.dumps(payload).lower()


def test_feature_permissions_distinguish_admin_and_regular_users():
    admin = identity_from_event(
        {
            "headers": {
                "x-adop-actor": "hcherian@example.com",
                "x-adop-role": "org-admin",
            }
        }
    )
    project_user = identity_from_event(
        {
            "headers": {
                "x-adop-actor": "oliver.orders@example.com",
                "x-adop-role": "project-user",
                "x-adop-groups": "adop-project-orders-users",
            }
        }
    )
    assert admin is not None and project_user is not None
    assert has_feature(admin, "users.manage")
    assert not has_feature(project_user, "users.manage")
    assert has_feature(project_user, "contracts.read")
    assert not has_feature(project_user, "connectors.create")


def test_access_directory_is_admin_only(tmp_path: Path):
    service = _service(tmp_path)
    admin = handler(
        {
            **_event("GET", "/api/v1/users"),
            "headers": {
                "x-adop-actor": "hcherian@example.com",
                "x-adop-role": "org-admin",
                "x-adop-workspace": "organization/default",
            },
        },
        service=service,
    )
    assert admin["statusCode"] == 200
    assert any(item["email"] == "hcherian@example.com" for item in json.loads(admin["body"])["items"])

    project_user = handler(
        {
            **_event("GET", "/api/v1/users"),
            "headers": {
                "x-adop-actor": "oliver.orders@example.com",
                "x-adop-role": "project-user",
                "x-adop-groups": "adop-project-orders-users",
                "x-adop-workspace": "project/orders",
            },
        },
        service=service,
    )
    assert project_user["statusCode"] == 403


def test_workspace_switch_is_scoped_and_audited(tmp_path: Path):
    service = _service(tmp_path)
    allowed = handler(
        {
            **_event(
                "POST",
                "/api/v1/auth/workspace",
                {"scope": "project", "scope_name": "claims"},
            ),
            "headers": {
                "x-adop-actor": "hcherian@example.com",
                "x-adop-role": "org-admin",
                "x-adop-workspace": "project/orders",
            },
        },
        service=service,
    )
    assert allowed["statusCode"] == 200
    assert json.loads(allowed["body"])["workspace"] == "project/claims"
    assert any(item["event_type"] == "workspace_selected" for item in service.audit(
        identity=identity_from_event({
            "headers": {
                "x-adop-actor": "hcherian@example.com",
                "x-adop-role": "org-admin",
            }
        })
    ))

    denied = handler(
        {
            **_event(
                "POST",
                "/api/v1/auth/workspace",
                {"scope": "project", "scope_name": "claims"},
            ),
            "headers": {
                "x-adop-actor": "oliver.orders@example.com",
                "x-adop-role": "project-user",
                "x-adop-groups": "adop-project-orders-users",
                "x-adop-workspace": "project/orders",
            },
        },
        service=service,
    )
    assert denied["statusCode"] == 403


def test_oidc_claims_map_okta_style_groups_to_project_membership(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ADOP_ENV", "aws")
    identity = identity_from_event(
        {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "00u-test",
                            "email": "oliver.orders@example.com",
                            "name": "Oliver Orders",
                            "groups": "adop-project-orders-users",
                        }
                    }
                }
            }
        }
    )
    assert identity is not None
    assert identity["provider"] == "oidc"
    assert {
        "level": "project",
        "name": "orders",
        "label": "Orders project",
    } in identity["memberships"]


def test_aws_mode_ignores_local_identity_headers(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADOP_ENV", "aws")
    identity = identity_from_event(
        {
            "headers": {
                "x-adop-actor": "attacker@example.com",
                "x-adop-role": "org-admin",
                "x-adop-groups": "adop-org-admins",
            }
        }
    )
    assert identity is None


def test_oidc_provider_configuration_is_runtime_driven(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADOP_ENV", "aws")
    monkeypatch.setenv("ADOP_AUTH_PROVIDER", "Okta")
    monkeypatch.setenv("ADOP_OIDC_PROVIDER_HINT", "Okta")
    monkeypatch.setenv("ADOP_OIDC_AUTHORIZE_URL", "https://example.okta.com/oauth2/default/v1/authorize")
    config = auth_config()
    assert config["mode"] == "oidc"
    assert config["provider"] == "Okta"
    assert config["provider_hint"] == "Okta"
    assert config["authorize_url"].startswith("https://example.okta.com/")


def test_policy_proposal_is_validated_persisted_and_requires_two_approvals(tmp_path: Path):
    service = _service(tmp_path)
    policy_id = "agent_authorization%2Fglobal_protection"
    current = json.loads(
        handler(_event("GET", f"/api/v1/policies/{policy_id}"), service=service)["body"]
    )

    proposal_response = handler(
        _event(
            "POST",
            f"/api/v1/policies/{policy_id}/proposals",
            {"content": current["content"], "expected_version": current["version"]},
            actor="mila@example.com",
        ),
        service=service,
    )
    proposal = json.loads(proposal_response["body"])
    assert proposal_response["statusCode"] == 201
    assert proposal["status"] == "pending_approval"

    self_approval = handler(
        _event(
            "POST",
            f"/api/v1/changes/{proposal['change_id']}/approve",
            {"decision": "approve"},
            actor="mila@example.com",
        ),
        service=service,
    )
    assert self_approval["statusCode"] == 409

    first = handler(
        _event(
            "POST",
            f"/api/v1/changes/{proposal['change_id']}/approve",
            {"decision": "approve"},
            actor="lina@example.com",
        ),
        service=service,
    )
    assert json.loads(first["body"])["status"] == "pending_approval"

    second = handler(
        _event(
            "POST",
            f"/api/v1/changes/{proposal['change_id']}/approve",
            {"decision": "approve"},
            actor="sam@example.com",
        ),
        service=service,
    )
    assert json.loads(second["body"])["status"] == "approved_pending_git"

    policy_file = ROOT / "shared/policies/agent_authorization/global_protection.cedar"
    assert "Human decision" in policy_file.read_text(encoding="utf-8")


def test_invalid_cedar_is_rejected(tmp_path: Path):
    service = _service(tmp_path)
    response = handler(
        _event(
            "POST",
            "/api/v1/policies/agent_authorization%2Fglobal_protection/validate",
            {"content": "not a Cedar policy"},
        ),
        service=service,
    )

    assert response["statusCode"] == 422
    assert json.loads(response["body"])["error"]["code"] == "validation_failed"


def test_file_config_provider_is_deterministic():
    snapshot = FileConfigProvider(ROOT).get_current("customer_orders")

    assert snapshot.source == "git"
    assert snapshot.version == "git-working-tree"
    assert len(snapshot.effective_hash) == 64
    assert snapshot.contracts["source"]["dataset_name"] == "customer_orders"


def test_duplicate_approval_is_conflict(tmp_path: Path):
    service = _service(tmp_path)
    policy_id = "agent_authorization%2Fglobal_protection"
    current = json.loads(
        handler(_event("GET", f"/api/v1/policies/{policy_id}"), service=service)["body"]
    )
    proposal = json.loads(
        handler(
            _event(
                "POST",
                f"/api/v1/policies/{policy_id}/proposals",
                {"content": current["content"], "expected_version": current["version"]},
            ),
            service=service,
        )["body"]
    )
    path = f"/api/v1/changes/{proposal['change_id']}/approve"
    handler(_event("POST", path, {"decision": "approve"}, actor="same-user"), service=service)
    response = handler(
        _event("POST", path, {"decision": "approve"}, actor="same-user"),
        service=service,
    )

    assert response["statusCode"] == 409


def test_policy_proposals_are_scoped_to_domain_and_project(tmp_path: Path):
    service = _service(tmp_path)
    policy_id = "agent_authorization%2Fglobal_protection"
    current = json.loads(
        handler(
            _event(
                "GET",
                f"/api/v1/policies/{policy_id}?scope=domain&scope_name=sales",
            ),
            service=service,
        )["body"]
    )
    response = handler(
        _event(
            "POST",
            f"/api/v1/policies/{policy_id}/proposals",
            {
                "content": current["content"],
                "expected_version": current["version"],
                "scope": "domain",
                "scope_name": "sales",
            },
        ),
        service=service,
    )
    proposal = json.loads(response["body"])
    assert response["statusCode"] == 201
    assert proposal["scope"] == "domain"
    assert proposal["scope_name"] == "sales"
    assert "workload-aware Cedar resolver" in proposal["application_note"]

    scoped = json.loads(
        handler(
            _event("GET", "/api/v1/policies?scope=domain&scope_name=sales"),
            service=service,
        )["body"]
    )
    assert scoped["items"][0]["scope"] == "domain"
    assert any(item["proposal"] for item in scoped["items"])


def test_contract_projection_and_tighten_only_scoped_proposal(tmp_path: Path):
    service = _service(tmp_path)
    projection = json.loads(
        handler(
            _event(
                "GET",
                "/api/v1/contracts?workload=customer_orders&domain=sales&project=orders",
            ),
            service=service,
        )["body"]
    )
    assert projection["scope"] == {
        "organization": "default",
        "domain": "sales",
        "project": "orders",
    }
    assert projection["layers"]["organization"]["policy"]["scope"] == "organization"
    assert projection["layers"]["domain"] is None
    assert projection["effective"]["zones"]["silver"]["minimum_quality_threshold"] == 0.80

    content = dict(projection["effective"])
    content["scope"] = "domain"
    content["zones"] = {key: dict(value) for key, value in content["zones"].items()}
    content["zones"]["silver"]["minimum_quality_threshold"] = 0.85
    response = handler(
        _event(
            "POST",
            "/api/v1/contracts/proposals",
            {
                "workload_name": "customer_orders",
                "domain": "sales",
                "project": "orders",
                "scope": "domain",
                "scope_name": "sales",
                "content": content,
                "expected_version": projection["effective"]["effective_hash"],
            },
        ),
        service=service,
    )
    proposal = json.loads(response["body"])
    assert response["statusCode"] == 201
    assert proposal["change_type"] == "zone_contract"
    assert proposal["scope"] == "domain"

    weaker = dict(content)
    weaker["zones"] = {key: dict(value) for key, value in content["zones"].items()}
    weaker["zones"]["silver"]["minimum_quality_threshold"] = 0.70
    rejected = handler(
        _event(
            "POST",
            "/api/v1/contracts/proposals",
            {
                "workload_name": "customer_orders",
                "scope": "domain",
                "scope_name": "sales",
                "content": weaker,
            },
        ),
        service=service,
    )
    assert rejected["statusCode"] == 422


def test_project_contract_cannot_cross_resolve_another_domain(tmp_path: Path):
    service = _service(tmp_path)
    response = handler(
        {
            **_event(
                "GET",
                "/api/v1/contracts?workload=customer_orders&domain=finance&project=orders",
            ),
            "headers": {
                "x-adop-actor": "oliver.orders@example.com",
                "x-adop-role": "project-user",
                "x-adop-groups": "adop-project-orders-users",
                "x-adop-workspace": "project/orders",
            },
        },
        service=service,
    )
    assert response["statusCode"] == 403
    assert json.loads(response["body"])["error"]["code"] == "scope_forbidden"


def test_contract_proposals_are_filtered_to_visible_scopes(tmp_path: Path):
    service = _service(tmp_path)
    service.store.create_contract_proposal(
        contract_id="adop.zone-governance",
        content={"scope": "project", "zones": {}},
        workload_name="claims",
        domain="sales",
        project="claims",
        actor="sara.sales@example.com",
        expected_version=None,
        required_approvals=2,
        scope="project",
        scope_name="claims",
    )
    response = handler(
        {
            **_event(
                "GET",
                "/api/v1/contracts?workload=customer_orders&domain=sales&project=orders",
            ),
            "headers": {
                "x-adop-actor": "oliver.orders@example.com",
                "x-adop-role": "project-user",
                "x-adop-groups": "adop-project-orders-users",
                "x-adop-workspace": "project/orders",
            },
        },
        service=service,
    )
    assert response["statusCode"] == 200
    assert "project/claims" not in json.dumps(json.loads(response["body"]))


def test_aws_draft_connector_tests_are_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADOP_ENV", "aws")
    service = _service(tmp_path)
    identity = identity_from_event(
        {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "connector-user",
                            "email": "oliver.orders@example.com",
                            "cognito:groups": "[adop-project-users]",
                        }
                    }
                }
            }
        }
    )
    assert identity is not None
    with pytest.raises(ApiError, match="disabled in AWS mode"):
        service.test_connector_draft(
            {
                "name": "probe",
                "type": "jdbc",
                "secret_ref": "arn:aws:secretsmanager:us-east-1:123456789012:secret:adop/dev/test",
                "metadata": {"host": "169.254.169.254", "port": 80},
            },
            identity,
        )


def test_connector_registry_reports_unverified_health_without_faking_success(tmp_path: Path):
    service = _service(tmp_path)
    created = handler(
        _event(
            "POST",
            "/api/v1/connectors",
            {
                "name": "sf_analytics",
                "type": "snowflake",
                "secret_ref": "env://ADOP_TEST_SNOWFLAKE_SECRET",
                "metadata": {
                    "account": "example-account",
                    "warehouse": "analytics",
                    "database": "sales",
                    "schema": "public",
                },
            },
        ),
        service=service,
    )
    assert created["statusCode"] == 201
    connector = json.loads(created["body"])
    assert connector["status"] == "not_tested"
    assert connector["secret_configured"] is True
    assert "secret_ref" not in connector
    assert connector["metadata"] == {}

    tested = handler(
        _event(
            "POST",
            f"/api/v1/connectors/{connector['connector_id']}/test",
        ),
        service=service,
    )
    assert tested["statusCode"] == 200
    result = json.loads(tested["body"])
    assert result["status"] == "not_tested"
    assert result["health"]["error_code"] == "SECRET_UNAVAILABLE"
    assert "password" not in json.dumps(result).lower()


def test_connector_connection_metadata_can_come_from_secret(monkeypatch):
    monkeypatch.setattr(
        connectors,
        "_secret_value",
        lambda _: {
            "engine": "postgres",
            "host": "db.example.internal",
            "port": 5432,
            "database": "analytics",
            "username": "svc_adop",
            "password": "never-return-this",
        },
    )
    captured = {}

    def fake_postgres(profile, secret):
        captured["profile"] = profile
        captured["secret"] = secret
        return {"status": "healthy", "details": {"provider": "postgres"}}

    monkeypatch.setattr(connectors, "_test_postgres", fake_postgres)
    result = connectors.test_connector(
        {
            "type": "jdbc",
            "secret_ref": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
            "host": "",
            "port": 0,
        }
    )

    assert result["status"] == "healthy"
    assert captured["profile"]["type"] == "postgres"
    assert captured["profile"]["host"] == "db.example.internal"
    assert captured["profile"]["port"] == 5432
    assert captured["profile"]["database"] == "analytics"
    assert captured["secret"]["password"] == "never-return-this"
    assert "password" not in json.dumps(result).lower()


@pytest.mark.parametrize("backend", [None, "json"])
def test_non_local_mode_refuses_local_json_store(
    monkeypatch: pytest.MonkeyPatch, backend: str | None
):
    from shared.control_plane.store import create_store_from_environment

    monkeypatch.setenv("ADOP_ENV", "aws")
    if backend is None:
        monkeypatch.delenv("ADOP_CONTROL_PLANE_BACKEND", raising=False)
    else:
        monkeypatch.setenv("ADOP_CONTROL_PLANE_BACKEND", backend)
    with pytest.raises(RuntimeError, match="only allowed when ADOP_ENV=local"):
        create_store_from_environment()


def test_aws_mode_dynamodb_requires_table(monkeypatch: pytest.MonkeyPatch):
    from shared.control_plane.store import create_store_from_environment

    monkeypatch.setenv("ADOP_ENV", "aws")
    monkeypatch.setenv("ADOP_CONTROL_PLANE_BACKEND", "dynamodb")
    monkeypatch.delenv("ADOP_CONTROL_PLANE_TABLE", raising=False)
    with pytest.raises(RuntimeError, match="ADOP_CONTROL_PLANE_TABLE is required"):
        create_store_from_environment()


def test_local_mode_uses_json_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from shared.control_plane.store import create_store_from_environment

    monkeypatch.setenv("ADOP_ENV", "local")
    monkeypatch.delenv("ADOP_CONTROL_PLANE_BACKEND", raising=False)
    monkeypatch.setenv("ADOP_CONTROL_PLANE_FILE", str(tmp_path / "cp.json"))
    assert isinstance(create_store_from_environment(), JsonControlPlaneStore)


def test_json_store_blocks_self_approval(tmp_path: Path):
    from shared.control_plane.store import VersionConflictError

    store = JsonControlPlaneStore(tmp_path / "cp.json")
    change = store.create_policy_proposal(
        policy_id="guardrails/sec_003_pii_masking", content="permit(principal,action,resource);",
        actor="maya@example.com", expected_version=None, required_approvals=2,
    )
    with pytest.raises(VersionConflictError, match="author"):
        store.record_approval(change_id=change["change_id"], actor="maya@example.com", decision="approve")
    rejected = store.record_approval(change_id=change["change_id"], actor="maya@example.com", decision="reject")
    assert rejected["status"] == "rejected"


@pytest.mark.parametrize(
    "raw, expected_role, expected_workspaces",
    [
        ("[adop-domain-owners adop-domain-sales-owners]", "domain-owner", {"domain/sales", "project/orders", "project/claims", "project/sales_daily"}),
        ("[adop-project-orders-users adop-project-users]", "project-user", {"project/orders"}),
        ("[adop-security-admins]", "security-admin", {"organization/default"}),
        ("[adop-org-admins]", "org-admin", {"organization/default", "domain/sales", "project/orders", "project/claims", "project/sales_daily"}),
        ("[]", "viewer", set()),
    ],
)
def test_api_gateway_bracketed_cognito_groups_map_to_roles_and_tenants(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected_role: str, expected_workspaces: set[str]
):
    monkeypatch.setenv("ADOP_ENV", "aws")
    monkeypatch.delenv("ADOP_COGNITO_USER_POOL_ID", raising=False)
    identity = identity_from_event(
        {"requestContext": {"authorizer": {"jwt": {"claims": {
            "sub": "00u-test", "email": "user@example.com", "cognito:groups": raw,
        }}}}}
    )
    assert identity["role"] == expected_role
    assert {f"{w['level']}/{w['name']}" for w in identity["workspaces"]} == expected_workspaces


def test_org_contract_proposal_cannot_lower_quality_floor(tmp_path: Path):
    service = _service(tmp_path)
    org = dict(service.repository.get_contract("customer_orders")["layers"]["organization"]["policy"])
    org["zones"] = {**org["zones"], "gold": {**org["zones"]["gold"], "minimum_quality_threshold": 0.5}}
    response = handler(
        {
            **_event("POST", "/api/v1/contracts/proposals",
                     {"workload_name": "customer_orders", "scope": "organization", "scope_name": "default", "content": org}),
            "headers": {"x-adop-actor": "maya.chen@example.com", "x-adop-role": "org-admin",
                        "x-adop-workspace": "organization/default"},
        },
        service=service,
    )
    assert response["statusCode"] == 422
    assert "minimum_quality_threshold" in json.loads(response["body"])["error"]["message"]


@pytest.mark.parametrize("group, role", [("adop-security-admins", "security-admin"),
                                         ("adop-connector-admins", "connector-admin"),
                                         ("adop-auditors", "auditor")])
def test_specialist_roles_get_organization_membership(monkeypatch: pytest.MonkeyPatch, group: str, role: str):
    from shared.control_plane.authorization import can_edit_scope

    monkeypatch.setenv("ADOP_ENV", "aws")
    monkeypatch.delenv("ADOP_COGNITO_USER_POOL_ID", raising=False)
    identity = identity_from_event({"requestContext": {"authorizer": {"jwt": {"claims": {
        "sub": "x", "email": "s@example.com", "cognito:groups": f"[{group}]"}}}}})
    assert identity["role"] == role
    assert {"level": "organization", "name": "default", "label": "Acme organization"} in identity["workspaces"]
    assert can_edit_scope(identity, "organization", "default") is (role != "auditor")
    assert can_edit_scope(identity, "project", "orders") is False


def test_security_admin_cannot_approve_zone_contract(tmp_path: Path):
    from shared.control_plane.authorization import enrich_identity

    service = _service(tmp_path)
    change = service.store.create_contract_proposal(
        contract_id="adop.zone-governance", content={"scope": "organization"}, workload_name="customer_orders",
        domain="sales", project="orders", actor="maya.chen@example.com", expected_version=None,
        required_approvals=2, scope="organization", scope_name="default",
    )
    security = enrich_identity({"sub": "s", "email": "sec@example.com", "role": "viewer",
                                "groups": ["adop-security-admins"], "provider": "oidc"})
    with pytest.raises(Exception) as denied:
        service.approve_change(change["change_id"], {"decision": "approve"}, "sec@example.com", security)
    assert getattr(denied.value, "status", None) == 403


def test_console_user_pool_disables_self_sign_up():
    template = (Path(__file__).resolve().parents[3] / "infra/cloudformation/template.yaml").read_text()
    pool = template.split("ConsoleUserPool:", 1)[1].split("\n  OrganizationAdmins:", 1)[0]
    assert "AllowAdminCreateUserOnly: true" in pool


def test_aws_connector_secrets_are_environment_scoped_and_workspace_is_forwarded():
    template = (Path(__file__).resolve().parents[3] / "infra/cloudformation/template.yaml").read_text()
    assert "secretsmanager:GetSecretValue" in template
    assert "secret:adop/${EnvironmentName}/*" in template
    assert "- x-adop-workspace" in template


def test_oidc_domain_owner_inherits_domain_projects_like_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from shared.control_plane.authorization import can_edit_scope, can_view_scope

    monkeypatch.setenv("ADOP_ENV", "aws")
    monkeypatch.delenv("ADOP_COGNITO_USER_POOL_ID", raising=False)
    owner = identity_from_event({"requestContext": {"authorizer": {"jwt": {"claims": {
        "sub": "x", "email": "o@example.com", "cognito:groups": "[adop-domain-owners adop-domain-sales-owners]"}}}}})
    assert can_view_scope(owner, "project", "orders") and can_edit_scope(owner, "project", "orders")
    admin = identity_from_event({"requestContext": {"authorizer": {"jwt": {"claims": {
        "sub": "y", "email": "a@example.com", "cognito:groups": "[adop-org-admins]"}}}}})
    names = {(w["level"], w["name"]) for w in _service(tmp_path).workspaces(admin)}
    assert {("domain", "sales"), ("project", "orders"), ("project", "claims")} <= names
