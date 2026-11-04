"""Small authentication adapter shared by local development and AWS deployments.

Local mode deliberately uses a development-only identity header so the UI can be
tested without creating a password database. In AWS, API Gateway validates the
OIDC/JWT token and passes the claims to the Lambda event.
"""

from __future__ import annotations

import os
import json
import ast
from typing import Any

from shared.control_plane.authorization import (
    ROLE_LABELS,
    can_view_scope,
    enrich_identity,
    test_user,
    with_workspace_registry,
)
from shared.control_plane.workspace_context import normalize_workspace

ROLE_GROUPS = ROLE_LABELS


def _groups(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            try:
                decoded = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                decoded = None
        if isinstance(decoded, list):
            return [str(item) for item in decoded if item]
        # API Gateway HTTP API JWT authorizers flatten array claims to "[a b c]".
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        return [
            item.strip().strip("\"'")
            for item in text.replace(",", " ").split()
            if item.strip().strip("\"'")
        ]
    return []


def _cognito_groups(claims: dict[str, Any]) -> list[str]:
    configured_pool = os.getenv("ADOP_COGNITO_USER_POOL_ID", "").strip()
    username = str(
        claims.get("cognito:username")
        or claims.get("username")
        or claims.get("sub")
        or ""
    )
    if not configured_pool or not username:
        return []
    try:
        import boto3

        response = boto3.client("cognito-idp").admin_list_groups_for_user(
            UserPoolId=configured_pool,
            Username=username,
        )
        return [
            str(group["GroupName"])
            for group in response.get("Groups", [])
            if group.get("GroupName")
        ]
    except Exception:
        # A directory lookup failure must not grant access. The caller will
        # continue with the claims already validated by API Gateway.
        return []


def _cognito_email(claims: dict[str, Any]) -> str:
    """Look up the user's email when the token (e.g. a Cognito access token) omits it."""
    configured_pool = os.getenv("ADOP_COGNITO_USER_POOL_ID", "").strip()
    username = str(claims.get("cognito:username") or claims.get("username") or claims.get("sub") or "")
    if not configured_pool or not username:
        return ""
    try:
        import boto3

        response = boto3.client("cognito-idp").admin_get_user(
            UserPoolId=configured_pool, Username=username
        )
        for attribute in response.get("UserAttributes", []):
            if attribute.get("Name") == "email":
                return str(attribute.get("Value") or "")
    except Exception:
        return ""
    return ""


def _scopes(role: str, groups: list[str]) -> list[str]:
    if role == "org-admin" or "adop-org-admins" in groups:
        return ["organization/default", "domain/*", "project/*"]
    if role == "domain-owner":
        return ["organization/default", "domain/sales", "project/*"]
    if role == "project-user":
        return ["organization/default", "project/orders"]
    return ["organization/default"]


def _with_selected_workspace(
    identity: dict[str, Any],
    event: dict[str, Any],
    workspace_parents: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {str(k).lower(): str(v) for k, v in (event.get("headers") or {}).items()}
    value = headers.get("x-adop-workspace")
    if not value:
        return identity
    try:
        selected = normalize_workspace(value)
    except ValueError as exc:
        identity["workspace_error"] = str(exc)
        return identity
    scoped_identity = with_workspace_registry(identity, workspace_parents)
    if not can_view_scope(scoped_identity, selected["level"], selected["name"]):
        identity["workspace_error"] = (
            f"Identity cannot access {selected['level']}/{selected['name']}"
        )
        return identity
    identity["selected_workspace"] = selected
    return identity


def identity_from_event(
    event: dict[str, Any],
    workspace_parents: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Return a normalized identity, or None when the request is anonymous."""

    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    if claims:
        raw_groups = claims.get("cognito:groups") or claims.get("groups")
        groups = _groups(raw_groups)
        if not groups or not any(group.lower().startswith("adop-") for group in groups):
            groups = _cognito_groups(claims) or groups
        role = str(claims.get("custom:adop_role") or claims.get("adop_role") or "")
        if not role:
            role = "org-admin" if "adop-org-admins" in groups else "viewer"
        email = str(
            claims.get("email")
            or claims.get("preferred_username")
            or claims.get("cognito:username")
            or claims.get("username")
            or claims.get("sub")
            or ""
        )
        if email and "@" not in email:
            email = _cognito_email(claims) or email
        if email:
            identity = enrich_identity({
                "sub": str(claims.get("sub") or email),
                "email": email,
                "name": str(
                    claims.get("name")
                    or claims.get("email")
                    or claims.get("preferred_username")
                    or claims.get("cognito:username")
                    or claims.get("username")
                    or email
                ),
                "role": role,
                "role_label": ROLE_GROUPS.get(role, role.replace("-", " ").title()),
                "groups": groups,
                "scopes": _scopes(role, groups),
                "provider": "oidc",
            })
            return _with_selected_workspace(identity, event, workspace_parents)

    if os.getenv("ADOP_ENV", "local").lower() == "local":
        headers = {str(k).lower(): str(v) for k, v in (event.get("headers") or {}).items()}
        email = headers.get("x-adop-actor")
        if email:
            groups = _groups(headers.get("x-adop-groups"))
            role = headers.get("x-adop-role", "domain-owner")
            identity = enrich_identity({
                "sub": f"local:{email}",
                "email": email,
                "name": headers.get("x-adop-name") or email.split("@")[0].replace(".", " ").title(),
                "role": role,
                "role_label": ROLE_GROUPS.get(role, role.replace("-", " ").title()),
                "groups": groups or [f"adop-{role}s"],
                "scopes": _scopes(role, groups),
                "provider": "local-test",
            })
            return _with_selected_workspace(identity, event, workspace_parents)
    return None


def local_login(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a local-only test identity.

    There is intentionally no local user store. A deployment can require a
    passcode through ADOP_LOCAL_TEST_PASSWORD, while an unset value keeps the
    localhost smoke-test flow frictionless.
    """

    if os.getenv("ADOP_ENV", "local").lower() != "local":
        raise PermissionError("Local test login is disabled outside ADOP_ENV=local")
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    expected = os.getenv("ADOP_LOCAL_TEST_PASSWORD", "")
    if "@" not in email:
        raise ValueError("A valid test email is required")
    if expected and password != expected:
        raise PermissionError("Invalid local test passcode")
    fixture = test_user(email)
    if not fixture:
        raise ValueError("Choose one of the seeded local test users")
    return enrich_identity({
        "sub": f"local:{email}",
        "email": email,
        "name": fixture["name"],
        "role": fixture["role"],
        "role_label": fixture["role_label"],
        "groups": [f"adop-{fixture['role']}s"],
        "scopes": _scopes(fixture["role"], [f"adop-{fixture['role']}s"]),
        "provider": "local-test",
        "test_only": True,
    })


def auth_config() -> dict[str, Any]:
    mode = os.getenv("ADOP_AUTH_MODE") or (
        "local" if os.getenv("ADOP_ENV", "local").lower() == "local" else "oidc"
    )
    return {
        "mode": mode,
        "provider": os.getenv("ADOP_AUTH_PROVIDER", "Cognito"),
        "issuer": os.getenv("ADOP_OIDC_ISSUER", ""),
        "client_id": os.getenv("ADOP_OIDC_CLIENT_ID", ""),
        "authorize_url": os.getenv("ADOP_OIDC_AUTHORIZE_URL", ""),
        "token_url": os.getenv("ADOP_OIDC_TOKEN_URL", ""),
        "logout_url": os.getenv("ADOP_OIDC_LOGOUT_URL", ""),
        "redirect_uri": os.getenv("ADOP_OIDC_REDIRECT_URI", ""),
        "provider_hint": os.getenv("ADOP_OIDC_PROVIDER_HINT", ""),
        "local_test_password_required": bool(os.getenv("ADOP_LOCAL_TEST_PASSWORD")),
    }
