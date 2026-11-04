"""Workspace membership and soft-isolation rules for the ADOP control plane.

The UI uses these records to make the workspace picker useful, but every
visibility decision is repeated by the API. In AWS, the same shape can be
populated from Cognito/Identity Center groups instead of this local fixture.
"""

from __future__ import annotations

from typing import Any


FEATURES: tuple[str, ...] = (
    "workloads.read",
    "runs.read",
    "contracts.read",
    "contracts.propose",
    "policies.read",
    "policies.propose",
    "policies.validate",
    "connectors.read",
    "connectors.create",
    "connectors.test",
    "approvals.read",
    "approvals.decide",
    "audit.read",
    "users.manage",
)

# Built-in workspace hierarchy shared by local and AWS mode. Local test users list
# these explicitly; OIDC users only carry group memberships, so the hierarchy must
# not depend on the identity source.
SYSTEM_WORKSPACES: tuple[dict[str, str], ...] = (
    {"level": "domain", "name": "sales", "label": "Sales domain", "parent_level": "organization", "parent_name": "default"},
    {"level": "project", "name": "orders", "label": "Orders project", "parent_level": "domain", "parent_name": "sales"},
    {"level": "project", "name": "claims", "label": "Claims project", "parent_level": "domain", "parent_name": "sales"},
    {"level": "project", "name": "sales_daily", "label": "Sales daily project", "parent_level": "domain", "parent_name": "sales"},
)
PROJECT_DOMAINS: dict[str, str] = {
    item["name"]: item["parent_name"] for item in SYSTEM_WORKSPACES if item["level"] == "project"
}


def project_domain(
    name: str,
    workspace_parents: dict[str, str] | None = None,
) -> str | None:
    """Return a known project parent; unknown projects are never guessed."""
    return (workspace_parents or {}).get(name) or PROJECT_DOMAINS.get(name)


def with_workspace_registry(
    identity: dict[str, Any],
    records: list[dict[str, Any]] | dict[str, str] | None,
) -> dict[str, Any]:
    """Attach persisted project parents to an internal identity copy."""
    result = dict(identity)
    if isinstance(records, dict):
        parents = {str(key): str(value) for key, value in records.items()}
    else:
        parents = {}
        for item in records or []:
            if item.get("level") == "project" and item.get("name") and item.get("parent_name"):
                parents[str(item["name"])] = str(item["parent_name"])
    result["_workspace_parents"] = parents
    return result


# Generic role groups grant a role, never a tenant membership.
ROLE_GROUP_PRECEDENCE: tuple[tuple[str, str], ...] = (
    ("adop-org-admins", "org-admin"),
    ("adop-security-admins", "security-admin"),
    ("adop-connector-admins", "connector-admin"),
    ("adop-auditors", "auditor"),
    ("adop-domain-owners", "domain-owner"),
    ("adop-project-users", "project-user"),
)
GENERIC_ROLE_GROUPS = frozenset(name for name, _ in ROLE_GROUP_PRECEDENCE)
# Specialist roles operate on organization-level objects (Cedar policies,
# shared connectors, the audit log); their feature set limits what they can do.
ORGANIZATION_WIDE_ROLES = frozenset({"org-admin", "security-admin", "connector-admin", "auditor"})
ORGANIZATION_EDIT_ROLES = frozenset({"security-admin", "connector-admin"})

ROLE_FEATURES: dict[str, frozenset[str]] = {
    "org-admin": frozenset(FEATURES),
    "domain-owner": frozenset(
        {
            "workloads.read",
            "runs.read",
            "contracts.read",
            "contracts.propose",
            "policies.read",
            "policies.propose",
            "policies.validate",
            "connectors.read",
            "connectors.create",
            "connectors.test",
            "approvals.read",
            "approvals.decide",
            "audit.read",
        }
    ),
    "project-user": frozenset(
        {
            "workloads.read",
            "runs.read",
            "contracts.read",
            "contracts.propose",
            "policies.read",
            "connectors.read",
            "connectors.test",
        }
    ),
    "viewer": frozenset(
        {
            "workloads.read",
            "runs.read",
            "contracts.read",
            "policies.read",
            "connectors.read",
            "approvals.read",
            "audit.read",
        }
    ),
    "security-admin": frozenset(
        {
            "workloads.read",
            "runs.read",
            "contracts.read",
            "policies.read",
            "policies.propose",
            "policies.validate",
            "approvals.read",
            "approvals.decide",
            "audit.read",
        }
    ),
    "connector-admin": frozenset(
        {
            "workloads.read",
            "connectors.read",
            "connectors.create",
            "connectors.test",
            "approvals.read",
            "approvals.decide",
            "audit.read",
        }
    ),
    "auditor": frozenset(
        {
            "workloads.read",
            "runs.read",
            "contracts.read",
            "policies.read",
            "connectors.read",
            "approvals.read",
            "audit.read",
        }
    ),
}

ROLE_LABELS: dict[str, str] = {
    "org-admin": "Organization admin",
    "domain-owner": "Domain owner",
    "project-user": "Project user",
    "viewer": "Viewer",
    "security-admin": "Security administrator",
    "connector-admin": "Connector administrator",
    "auditor": "Auditor",
}

LOCAL_TEST_USERS: tuple[dict[str, Any], ...] = (
    {
        "email": "maya.chen@example.com",
        "name": "Maya Chen",
        "role": "org-admin",
        "role_label": "Organization admin",
        "memberships": [
            {"level": "organization", "name": "default", "label": "Acme organization"},
            {"level": "domain", "name": "sales", "label": "Sales domain"},
            {"level": "project", "name": "orders", "label": "Orders project"},
            {"level": "project", "name": "claims", "label": "Claims project"},
            {"level": "project", "name": "sales_daily", "label": "Sales daily project"},
        ],
    },
    {
        "username": "hcherian",
        "email": "hcherian@example.com",
        "name": "H Cherian",
        "role": "org-admin",
        "role_label": "Organization admin",
        "memberships": [
            {"level": "organization", "name": "default", "label": "Acme organization"},
            {"level": "domain", "name": "sales", "label": "Sales domain"},
            {"level": "project", "name": "orders", "label": "Orders project"},
            {"level": "project", "name": "claims", "label": "Claims project"},
            {"level": "project", "name": "sales_daily", "label": "Sales daily project"},
        ],
    },
    {
        "email": "sara.sales@example.com",
        "name": "Sara Sales",
        "role": "domain-owner",
        "role_label": "Domain owner",
        "memberships": [
            {"level": "domain", "name": "sales", "label": "Sales domain"},
            {"level": "project", "name": "orders", "label": "Orders project"},
            {"level": "project", "name": "claims", "label": "Claims project"},
            {"level": "project", "name": "sales_daily", "label": "Sales daily project"},
        ],
    },
    {
        "email": "oliver.orders@example.com",
        "name": "Oliver Orders",
        "role": "project-user",
        "role_label": "Project user",
        "memberships": [
            {"level": "project", "name": "orders", "label": "Orders project"},
        ],
    },
    {
        "email": "lina.claims@example.com",
        "name": "Lina Claims",
        "role": "project-user",
        "role_label": "Project user",
        "memberships": [
            {"level": "project", "name": "claims", "label": "Claims project"},
        ],
    },
)

WORKLOAD_PROJECTS = {
    "customer_orders": "orders",
    "claims": "claims",
    "sales_daily": "sales_daily",
}


def local_test_users() -> list[dict[str, Any]]:
    return [
        {
            "username": user.get("username", ""),
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "role_label": user["role_label"],
            "memberships": list(user["memberships"]),
            "feature_permissions": sorted(
                ROLE_FEATURES.get(user["role"], ROLE_FEATURES["viewer"])
            ),
        }
        for user in LOCAL_TEST_USERS
    ]


def test_user(email: str) -> dict[str, Any] | None:
    value = email.strip().lower()
    return next(
        (
            dict(user)
            for user in LOCAL_TEST_USERS
            if user["email"].lower() == value or user.get("username", "").lower() == value
        ),
        None,
    )


def enrich_identity(identity: dict[str, Any]) -> dict[str, Any]:
    """Attach normalized workspace memberships to an OIDC or local identity."""

    result = dict(identity)
    fixture = test_user(str(result.get("email", "")))
    if fixture and result.get("provider") == "local-test":
        result["memberships"] = list(fixture["memberships"])
        result["role"] = fixture["role"]
        result["role_label"] = fixture["role_label"]
        result["workspaces"] = list(fixture["memberships"])
        result["feature_permissions"] = sorted(
            ROLE_FEATURES.get(fixture["role"], ROLE_FEATURES["viewer"])
        )
        return result

    groups = {str(group).lower() for group in result.get("groups", [])}
    current_role = str(result.get("role") or "viewer")
    if current_role in {"", "viewer"}:
        for group_name, mapped_role in ROLE_GROUP_PRECEDENCE:
            if group_name in groups:
                current_role = mapped_role
                break
        else:
            if any(g.startswith("adop-domain-") and g.endswith("-owners") and g not in GENERIC_ROLE_GROUPS for g in groups):
                current_role = "domain-owner"
            elif any(g.startswith("adop-project-") and g not in GENERIC_ROLE_GROUPS for g in groups):
                current_role = "project-user"
        result["role"] = current_role
    memberships: list[dict[str, str]] = []
    if result.get("role") in ORGANIZATION_WIDE_ROLES or "adop-org-admins" in groups:
        memberships.append({"level": "organization", "name": "default", "label": "Acme organization"})
    for group in sorted(groups):
        if group in GENERIC_ROLE_GROUPS:
            continue
        if group.startswith("adop-domain-"):
            name = group.removeprefix("adop-domain-").removesuffix("-owners").removesuffix("-users")
            if name:
                memberships.append({"level": "domain", "name": name, "label": f"{name.title()} domain"})
        if group.startswith("adop-project-"):
            name = group.removeprefix("adop-project-").removesuffix("-owners").removesuffix("-users")
            if name:
                memberships.append({"level": "project", "name": name, "label": f"{name.title()} project"})
    # Expand inherited scopes so OIDC identities list the same workspaces as the
    # local test users: org admins see the whole hierarchy, domain members see
    # their domain's projects.
    seen = {(item["level"], item["name"]) for item in memberships}
    member_domains = {item["name"] for item in memberships if item["level"] == "domain"}
    for item in SYSTEM_WORKSPACES:
        inherited = result.get("role") == "org-admin" or (
            item["level"] == "project" and item["parent_name"] in member_domains
        )
        if inherited and (item["level"], item["name"]) not in seen:
            memberships.append({"level": item["level"], "name": item["name"], "label": item["label"]})
            seen.add((item["level"], item["name"]))
    result["memberships"] = memberships
    result["workspaces"] = memberships
    role = str(result.get("role") or "viewer")
    result["role_label"] = ROLE_LABELS.get(role, role.replace("-", " ").title())
    result["feature_permissions"] = sorted(
        ROLE_FEATURES.get(role, ROLE_FEATURES["viewer"])
    )
    return result


def feature_permissions(identity: dict[str, Any] | None) -> set[str]:
    if not identity:
        return set()
    configured = identity.get("feature_permissions")
    if isinstance(configured, list):
        return {str(item) for item in configured}
    return set(ROLE_FEATURES.get(str(identity.get("role") or "viewer"), ()))


def has_feature(identity: dict[str, Any] | None, feature: str) -> bool:
    return feature in feature_permissions(identity)


def can_view_scope(identity: dict[str, Any] | None, level: str, name: str) -> bool:
    if not identity:
        return False
    if identity.get("role") == "org-admin":
        return True
    memberships = identity.get("memberships", [])
    if level == "organization":
        # A tenant membership is required. Do not grant an ungrouped OIDC
        # identity organization visibility merely because it is authenticated.
        return bool(memberships)
    if any(item.get("level") == level and item.get("name") == name for item in memberships):
        return True
    if level == "project":
        return any(
            item.get("level") == "domain"
            and item.get("name") == project_domain(name, identity.get("_workspace_parents"))
            for item in memberships
        )
    return False


def can_edit_scope(identity: dict[str, Any] | None, level: str, name: str) -> bool:
    if not identity:
        return False
    if identity.get("role") == "org-admin":
        return True
    memberships = identity.get("memberships", [])
    if level == "organization":
        return identity.get("role") in ORGANIZATION_EDIT_ROLES and any(
            item.get("level") == "organization" for item in memberships
        )
    role = identity.get("role")
    if role not in {"domain-owner", "project-user"}:
        return False
    if any(item.get("level") == level and item.get("name") == name for item in memberships):
        return True
    # Domain owners inherit their domain's projects (same rule as can_view_scope).
    return (
        role == "domain-owner"
        and level == "project"
        and any(
            item.get("level") == "domain"
            and item.get("name") == project_domain(name, identity.get("_workspace_parents"))
            for item in memberships
        )
    )


def can_edit_contract_scope(identity: dict[str, Any] | None, level: str, name: str) -> bool:
    """Contract writes are project-scoped except for organization admins."""
    if not identity:
        return False
    if identity.get("role") == "org-admin":
        return True
    return level == "project" and can_edit_scope(identity, level, name)


def visible_workloads(identity: dict[str, Any] | None, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not identity:
        return []
    selected = identity.get("selected_workspace") or {}
    selected_level = str(selected.get("level") or "")
    selected_name = str(selected.get("name") or "")
    if selected_level == "project" and selected_name:
        visible_projects = {selected_name}
    elif selected_level == "domain" and selected_name:
        visible_projects = {
            project
            for project in WORKLOAD_PROJECTS.values()
            if project_domain(project, identity.get("_workspace_parents")) == selected_name
        }
    elif selected_level == "organization":
        visible_projects = set(WORKLOAD_PROJECTS.values())
    elif identity.get("role") == "org-admin":
        return records
    else:
        visible_projects = {
            item["name"] for item in identity.get("memberships", []) if item.get("level") == "project"
        }
        if any(item.get("level") == "domain" and item.get("name") == "sales" for item in identity.get("memberships", [])):
            visible_projects.update(WORKLOAD_PROJECTS.values())
    return [
        record for record in records
        if WORKLOAD_PROJECTS.get(record.get("name")) in visible_projects
    ]


def workspace_label(identity: dict[str, Any] | None) -> str:
    if not identity:
        return "No workspace"
    memberships = identity.get("memberships", [])
    project = next((item for item in memberships if item.get("level") == "project"), None)
    domain = next((item for item in memberships if item.get("level") == "domain"), None)
    if project and identity.get("role") == "project-user":
        return project["label"]
    if domain:
        return domain["label"]
    return "Acme organization"
