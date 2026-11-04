"""CLI workspace identity and scope context for ADOP agent sessions.

This module is deliberately shared by Codex, Claude Code, Kiro, and the
headless runtime.  It provides a small local session contract:

    identity + selected workspace -> agent context -> tool scope check

The session file contains identity and workspace metadata only.  It never
contains an access token or a secret.  Production SSO adapters can populate
the same identity shape through environment variables or a future device-flow
client without changing the scope resolver.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .authorization import (
    WORKLOAD_PROJECTS,
    can_view_scope,
    enrich_identity,
    test_user,
    with_workspace_registry,
)
from .connectors import test_connector as run_connector_test
from .connectors import utc_now as connector_utc_now
from .store import create_store_from_environment

ROOT = Path(__file__).resolve().parents[2]
SESSION_ENV = "ADOP_WORKSPACE_SESSION"
USER_ENV = "ADOP_USER_EMAIL"
TEST_USER_ENV = "ADOP_TEST_USER"
WORKSPACE_ENV = "ADOP_WORKSPACE"

LEVELS = ("organization", "domain", "project")


def repository_root(value: str | Path | None = None) -> Path:
    """Find the repository root from a hook cwd or the current directory."""

    start = Path(value or os.getcwd()).expanduser().resolve()
    candidates = (start, *start.parents)
    for candidate in candidates:
        if (candidate / "shared" / "control_plane" / "authorization.py").is_file():
            return candidate
    return ROOT


def session_path(repo_root: str | Path | None = None) -> Path:
    explicit = os.environ.get(SESSION_ENV)
    if explicit:
        return Path(explicit).expanduser()
    root = repository_root(repo_root)
    repo_key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:20]
    return Path.home() / ".adop" / "sessions" / f"{repo_key}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    for secret_key in ("access_token", "id_token", "refresh_token"):
        value.pop(secret_key, None)
    return value


def load_session(repo_root: str | Path | None = None) -> dict[str, Any] | None:
    """Load the local session, returning None for a missing/invalid session."""

    return _read_json(session_path(repo_root))


def save_session(session: dict[str, Any], repo_root: str | Path | None = None) -> Path:
    path = session_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = dict(session)
    safe.pop("access_token", None)
    safe.pop("id_token", None)
    safe.pop("refresh_token", None)
    path.write_text(json.dumps(safe, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def _identity_from_environment() -> dict[str, Any] | None:
    raw = os.environ.get("ADOP_IDENTITY_JSON")
    if raw:
        try:
            identity = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"ADOP_IDENTITY_JSON is not valid JSON: {exc.msg}") from exc
        if not isinstance(identity, dict):
            raise ValueError("ADOP_IDENTITY_JSON must be a JSON object")
        identity.setdefault("provider", "oidc")
        return enrich_identity(identity)

    email = os.environ.get(USER_ENV) or os.environ.get(TEST_USER_ENV)
    if not email:
        return None
    fixture = test_user(email)
    if fixture:
        identity = {
            "sub": f"local:{fixture['email']}",
            "email": fixture["email"],
            "name": fixture["name"],
            "provider": "local-test",
            "test_only": True,
        }
        return enrich_identity(identity)

    groups = [
        group.strip()
        for group in os.environ.get("ADOP_USER_GROUPS", "").split(",")
        if group.strip()
    ]
    identity = {
        "sub": f"env:{email.strip().lower()}",
        "email": email.strip().lower(),
        "name": os.environ.get("ADOP_USER_NAME") or email.strip(),
        "provider": os.environ.get("ADOP_AUTH_PROVIDER", "oidc"),
        "groups": groups,
        "role": os.environ.get("ADOP_USER_ROLE", ""),
    }
    return enrich_identity(identity)


def identity_from_session(repo_root: str | Path | None = None) -> dict[str, Any] | None:
    session = load_session(repo_root)
    if session and isinstance(session.get("identity"), dict):
        return dict(session["identity"])
    return _identity_from_environment()


def normalize_workspace(value: str | dict[str, Any]) -> dict[str, str]:
    if isinstance(value, dict):
        level = str(value.get("level", "")).strip().lower()
        name = str(value.get("name", "")).strip().lower()
    else:
        text = str(value).strip().lower()
        if "/" not in text:
            raise ValueError("workspace must be level/name, for example project/orders")
        level, name = text.split("/", 1)
    if level not in LEVELS or not name or "/" in name:
        raise ValueError("workspace must be organization/default, domain/name, or project/name")
    if level == "organization" and name != "default":
        raise ValueError("the organization workspace is organization/default")
    return {"level": level, "name": name}


def workspace_key(workspace: dict[str, Any] | None) -> str:
    if not workspace:
        return ""
    return f"{workspace.get('level', '')}/{workspace.get('name', '')}"


def available_workspaces(identity: dict[str, Any] | None) -> list[dict[str, str]]:
    if not identity:
        return []
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in identity.get("memberships", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            workspace = normalize_workspace(item)
        except ValueError:
            continue
        key = (workspace["level"], workspace["name"])
        if key not in seen:
            result.append(
                {
                    **workspace,
                    "label": str(item.get("label") or f"{workspace['name'].title()} {workspace['level']}"),
                }
            )
            seen.add(key)
    return result


def registered_workspaces(
    identity: dict[str, Any] | None,
    store: Any | None = None,
) -> list[dict[str, str]]:
    """Merge identity memberships with the persisted control-plane registry."""

    result = available_workspaces(identity)
    if not identity or store is None:
        return result
    existing = {(item["level"], item["name"]) for item in result}
    for item in store.list_workspaces():
        level = str(item.get("level") or "")
        name = str(item.get("name") or "")
        if not level or not name or not can_view_scope(identity, level, name):
            continue
        key = (level, name)
        if key in existing:
            continue
        result.append(
            {
                "level": level,
                "name": name,
                "label": str(item.get("label") or f"{name.title()} {level}"),
            }
        )
        existing.add(key)
    return sorted(
        result,
        key=lambda item: (
            {"organization": 0, "domain": 1, "project": 2}.get(item["level"], 9),
            item["name"],
        ),
    )


def create_workspace(
    level: str,
    name: str,
    label: str | None = None,
    parent: str | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Create a persisted domain/project workspace as an organization admin."""

    context = current_context(repo_root)
    identity = context.get("identity")
    if not identity or identity.get("role") != "org-admin":
        raise PermissionError("Only organization administrators can create workspaces.")
    normalized = normalize_workspace({"level": level, "name": name})
    if normalized["level"] == "organization":
        raise ValueError("The organization workspace is created with the organization.")
    if normalized["level"] == "project":
        if not parent:
            raise ValueError("Project workspaces require a parent domain, for example domain/sales.")
        parent_workspace = normalize_workspace(parent)
        if parent_workspace["level"] != "domain":
            raise ValueError("Project workspaces must belong to a domain.")
        if not can_view_scope(
            identity,
            parent_workspace["level"],
            parent_workspace["name"],
        ):
            raise PermissionError(
                f"Parent workspace {workspace_key(parent_workspace)} is not accessible."
            )
        parent_level, parent_name = parent_workspace["level"], parent_workspace["name"]
    else:
        parent_level, parent_name = "organization", "default"
    store = create_store_from_environment()
    return store.create_workspace(
        level=normalized["level"],
        name=normalized["name"],
        label=(label or normalized["name"].replace("_", " ").title()).strip(),
        parent_level=parent_level,
        parent_name=parent_name,
        actor=str(identity.get("email") or identity.get("name") or "adop-cli"),
    )


def _session(identity: dict[str, Any], workspace: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "session_id": f"adop-{uuid.uuid4().hex}",
        "created_at": _now(),
        "updated_at": _now(),
        "identity": {
            key: value
            for key, value in identity.items()
            if key not in {"access_token", "id_token", "refresh_token"}
        },
        "workspace": workspace,
    }


def login(
    email: str | None = None,
    workspace: str | None = None,
    repo_root: str | Path | None = None,
    aws_account: str | None = None,
) -> dict[str, Any]:
    if email:
        fixture = test_user(email)
        if not fixture:
            raise ValueError(
                f"{email} is not a seeded local test user. "
                "Use ADOP_IDENTITY_JSON or ADOP_USER_EMAIL with SSO claims for a real identity."
            )
        identity = enrich_identity(
            {
                "sub": f"local:{fixture['email']}",
                "email": fixture["email"],
                "name": fixture["name"],
                "username": fixture.get("username", ""),
                "provider": "local-test",
                "test_only": True,
            }
        )
    else:
        identity = _identity_from_environment()
        if not identity:
            raise ValueError(
                "No identity supplied. Use --user for a local test user, or set "
                "ADOP_USER_EMAIL/ADOP_IDENTITY_JSON for SSO."
            )

    selected = normalize_workspace(workspace) if workspace else None
    if selected and not can_view_scope(identity, selected["level"], selected["name"]):
        raise PermissionError(
            f"{identity.get('email', 'identity')} cannot access {workspace_key(selected)}"
        )
    current = _session(identity, selected)
    if aws_account:
        from .aws_guard import validate_account

        current["aws_account"] = validate_account(aws_account)
    save_session(current, repo_root)
    return current


def logout(repo_root: str | Path | None = None) -> None:
    path = session_path(repo_root)
    try:
        path.unlink()
    except FileNotFoundError:
        return


def current_context(repo_root: str | Path | None = None) -> dict[str, Any]:
    session = load_session(repo_root)
    if session:
        identity = session.get("identity")
        if isinstance(identity, dict):
            try:
                session = dict(session)
                session["identity"] = with_workspace_registry(
                    identity,
                    create_store_from_environment().list_workspaces(),
                )
            except Exception:
                pass
        return session
    identity = _identity_from_environment()
    if identity:
        try:
            identity = with_workspace_registry(
                identity,
                create_store_from_environment().list_workspaces(),
            )
        except Exception:
            pass
        return _session(identity, None)
    return {
        "session_id": "",
        "identity": None,
        "workspace": None,
    }


def select_workspace(
    value: str, repo_root: str | Path | None = None
) -> dict[str, Any]:
    session = load_session(repo_root)
    if not session or not isinstance(session.get("identity"), dict):
        raise PermissionError("Not logged in. Run `adop login --user <email>` first.")
    selected = normalize_workspace(value)
    identity = session["identity"]
    if not can_view_scope(identity, selected["level"], selected["name"]):
        raise PermissionError(
            f"You do not have access to {workspace_key(selected)}. "
            "Run `adop workspace list` to see allowed workspaces."
        )
    session["workspace"] = selected
    session["updated_at"] = _now()
    save_session(session, repo_root)
    return session


def _scope_for_workload(workload: str) -> dict[str, str]:
    project = WORKLOAD_PROJECTS.get(workload)
    return {"level": "project", "name": project} if project else {}


def can_access_workload(
    identity: dict[str, Any] | None,
    workspace: dict[str, Any] | None,
    workload: str,
) -> bool:
    if not identity or not workspace:
        return False
    project = WORKLOAD_PROJECTS.get(workload)
    if not project:
        return False
    level = str(workspace.get("level", ""))
    name = str(workspace.get("name", ""))
    if level == "organization":
        return can_view_scope(identity, "organization", "default")
    if level == "domain":
        return can_view_scope(identity, "domain", name) and can_view_scope(
            identity, "project", project
        )
    return name == project and can_view_scope(identity, "project", project)


def authorize(
    context: dict[str, Any] | None,
    *,
    workload: str | None = None,
    scope: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Authorize an agent action against the selected session workspace."""

    if not context or not context.get("identity"):
        if workload or scope:
            return False, "No ADOP identity is active. Run `adop login` and select a workspace."
        return True, ""
    identity = context["identity"]
    workspace = context.get("workspace")
    if workload:
        if not workspace:
            return False, "No workspace selected. Ask the user to choose an ADOP workspace first."
        if not can_access_workload(identity, workspace, workload):
            return False, (
                f"Workspace {workspace_key(workspace)} cannot access workload {workload}. "
                "Ask the user to choose one of the listed workspaces."
            )
    if scope:
        level = str(scope.get("level", "")).lower()
        name = str(scope.get("name", "")).lower()
        if level in LEVELS and name and not can_view_scope(identity, level, name):
            return False, f"Identity cannot access {level}/{name}."
        if workspace and level in LEVELS and name:
            selected = normalize_workspace(workspace)
            if selected["level"] == "project" and level == "project" and selected["name"] != name:
                return False, (
                    f"Selected workspace {workspace_key(selected)} cannot access "
                    f"{level}/{name}."
                )
    return True, ""


def _scope_hint(tool_input: dict[str, Any]) -> dict[str, str] | None:
    for key in ("workspace", "scope", "scope_name"):
        value = tool_input.get(key)
        if isinstance(value, dict):
            try:
                return normalize_workspace(value)
            except ValueError:
                continue
    level = tool_input.get("scope_level") or tool_input.get("level")
    name = tool_input.get("scope_name") or tool_input.get("name")
    if level and name:
        try:
            return normalize_workspace({"level": level, "name": name})
        except ValueError:
            return None
    return None


def prompt_context(repo_root: str | Path | None = None) -> str:
    context = current_context(repo_root)
    identity = context.get("identity")
    if not identity:
        return (
            "ADOP WORKSPACE: no user session is active. Before changing a workload, "
            "ask the user to sign in and choose an organization, domain, or project. "
            "Commands: `adop login --user <email>`, `adop workspace list`, "
            "`adop workspace use <level/name>`."
        )
    options = available_workspaces(identity)
    current = context.get("workspace")
    lines = [
        "ADOP WORKSPACE CONTEXT",
        f"  signed in as: {identity.get('name') or identity.get('email')} <{identity.get('email', '')}>",
        f"  role:        {identity.get('role_label') or identity.get('role') or 'SSO-managed'}",
        f"  current:     {workspace_key(current) or 'none — selection required before writes'}",
        "  accessible:  " + ", ".join(workspace_key(item) for item in options),
        "  isolation:   workload writes are restricted to the selected workspace.",
        "  switch:      adop workspace use <organization/default|domain/name|project/name>",
    ]
    if identity.get("test_only"):
        lines.insert(3, "  mode:        local test identity")
    from .aws_guard import check as aws_check, context_lines

    session = load_session(repo_root) or {}
    if session.get("aws_account") or os.environ.get("ADOP_EXPECTED_AWS_ACCOUNT"):
        lines.extend(context_lines(aws_check(session)))
    return "\n".join(lines)


def _print_context(context: dict[str, Any]) -> None:
    identity = context.get("identity") or {}
    print(f"Signed in: {identity.get('name', 'no')} <{identity.get('email', '')}>")
    print(f"Role: {identity.get('role_label') or identity.get('role') or 'none'}")
    print(f"Current workspace: {workspace_key(context.get('workspace')) or 'none'}")


def _connector_scope(record: dict[str, Any]) -> dict[str, str]:
    return {
        "level": str(record.get("scope") or "organization"),
        "name": str(record.get("scope_name") or "default"),
    }


def _connector_visible(
    context: dict[str, Any], record: dict[str, Any]
) -> tuple[bool, str]:
    identity = context.get("identity")
    scope = _connector_scope(record)
    allowed, reason = authorize(context, scope=scope)
    if not identity:
        return False, "No ADOP identity is active."
    if not allowed:
        return False, reason
    if not can_view_scope(identity, scope["level"], scope["name"]):
        return False, f"Identity cannot access {workspace_key(scope)}."
    return True, ""


def _safe_connector(record: dict[str, Any]) -> dict[str, Any]:
    health = record.get("health") or {}
    return {
        "connector_id": record.get("connector_id"),
        "name": record.get("name"),
        "type": record.get("type"),
        "scope": _connector_scope(record),
        "access_mode": record.get("access_mode", "read-only"),
        "secret_configured": bool(record.get("secret_ref")),
        "status": record.get("status", "not_tested"),
        "health": {
            key: value
            for key, value in health.items()
            if key not in {"secret", "password", "token", "credential"}
        },
    }


def _connector_command(args: argparse.Namespace, context: dict[str, Any]) -> int:
    store = create_store_from_environment()
    records = store.list_connectors()
    visible: list[dict[str, Any]] = []
    for record in records:
        allowed, _ = _connector_visible(context, record)
        if allowed:
            visible.append(record)

    if args.connector_command == "list":
        result = [_safe_connector(record) for record in visible]
        if args.json:
            print(json.dumps({"items": result}, indent=2, sort_keys=True))
        else:
            for item in result:
                print(
                    f"{item['connector_id']}  {item['name']}  {item['type']}  "
                    f"{item['status']}  secret={'yes' if item['secret_configured'] else 'no'}"
                )
            if not result:
                print("No accessible connectors.")
        return 0

    matches = [
        record
        for record in visible
        if (args.connector_id and record.get("connector_id") == args.connector_id)
        or (args.name and record.get("name") == args.name)
    ]
    if len(matches) != 1:
        raise ValueError("Choose exactly one accessible connector with --id or --name")
    record = matches[0]
    profile = {**record.get("metadata", {}), **record}
    health = run_connector_test(profile)
    updated = store.update_connector_health(record["connector_id"], health)
    result = _safe_connector(updated)
    result["tested_at"] = connector_utc_now()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['name']}: {result['status']}")
        if result["health"].get("error_code"):
            print(f"error: {result['health']['error_code']}")
    return 0 if result["status"] == "healthy" else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adop", description="ADOP agent workspace context")
    sub = parser.add_subparsers(dest="command")

    login_parser = sub.add_parser("login", help="create a local SSO/test session")
    login_parser.add_argument("--user", "--email", dest="email")
    login_parser.add_argument("--workspace")
    login_parser.add_argument("--aws-account", dest="aws_account",
                              help="pin the AWS account this session may use (12 digits)")
    sub.add_parser("aws-check", help="verify AWS credentials match the pinned account")

    sub.add_parser("logout", help="remove the local session")
    sub.add_parser("whoami", help="show the active identity and workspace")
    sub.add_parser("context", help="print the agent context")

    workspace = sub.add_parser("workspace", help="list or select workspaces")
    workspace_sub = workspace.add_subparsers(dest="workspace_command")
    workspace_sub.add_parser("list", help="list accessible workspaces")
    workspace_sub.add_parser("current", help="show the selected workspace")
    create = workspace_sub.add_parser(
        "create",
        help="create a domain or project workspace (organization admin only)",
    )
    create.add_argument("--level", choices=("domain", "project"), required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--label")
    create.add_argument("--parent", help="parent workspace, required for projects")
    use = workspace_sub.add_parser("use", help="select an accessible workspace")
    use.add_argument("workspace")

    check = sub.add_parser("check", help="check workload or scope access")
    check.add_argument("--workload")
    check.add_argument("--scope", help="level/name")
    check.add_argument("--json", action="store_true")

    connector = sub.add_parser("connector", help="list or health-check scoped connectors")
    connector_sub = connector.add_subparsers(dest="connector_command")
    connector_list = connector_sub.add_parser("list", help="list accessible connectors")
    connector_list.add_argument("--json", action="store_true")
    connector_test = connector_sub.add_parser("test", help="run a real connector health check")
    connector_test.add_argument("--id", dest="connector_id")
    connector_test.add_argument("--name")
    connector_test.add_argument("--json", action="store_true")

    hook = sub.add_parser("hook-session", help=argparse.SUPPRESS)
    hook.add_argument("--cwd")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = repository_root(getattr(args, "cwd", None))
    try:
        if args.command == "aws-check":
            from .aws_guard import check as aws_check

            result = aws_check(load_session(repo))
            print(f"{result['status'].upper()}: {result['detail']}")
            return {"ok": 0, "unpinned": 1, "unavailable": 1}.get(result["status"], 2)
        if args.command == "login":
            session = login(args.email, args.workspace, repo, getattr(args, "aws_account", None))
            _print_context(session)
            print("Next: adop workspace list")
            return 0
        if args.command == "logout":
            logout(repo)
            print("ADOP workspace session removed.")
            return 0
        if args.command in {"whoami", "context"}:
            context = current_context(repo)
            if args.command == "context":
                print(json.dumps(context, indent=2, sort_keys=True))
            else:
                _print_context(context)
            return 0
        if args.command == "workspace":
            context = current_context(repo)
            if args.workspace_command == "list":
                store = create_store_from_environment()
                for item in registered_workspaces(context.get("identity"), store):
                    marker = "*" if workspace_key(item) == workspace_key(context.get("workspace")) else " "
                    print(f"{marker} {workspace_key(item):<24} {item['label']}")
                if not registered_workspaces(context.get("identity"), store):
                    print("No accessible workspaces. Sign in first.")
                return 0
            if args.workspace_command == "current":
                print(workspace_key(context.get("workspace")) or "none")
                return 0
            if args.workspace_command == "create":
                record = create_workspace(
                    args.level,
                    args.name,
                    args.label,
                    args.parent,
                    repo,
                )
                print(
                    f"Created {record['level']}/{record['name']} "
                    f"({record['label']})."
                )
                return 0
            if args.workspace_command == "use":
                session = select_workspace(args.workspace, repo)
                print(f"Selected {workspace_key(session['workspace'])}.")
                return 0
            _parser().parse_args(["workspace", "--help"])
            return 2
        if args.command == "check":
            context = current_context(repo)
            scope = normalize_workspace(args.scope) if args.scope else None
            allowed, reason = authorize(context, workload=args.workload, scope=scope)
            result = {"allowed": allowed, "reason": reason, "workspace": context.get("workspace")}
            if args.json:
                print(json.dumps(result, sort_keys=True))
            else:
                print("ALLOWED" if allowed else f"DENIED: {reason}")
            return 0 if allowed else 2
        if args.command == "connector":
            context = current_context(repo)
            if args.connector_command in {"list", "test"}:
                return _connector_command(args, context)
            _parser().parse_args(["connector", "--help"])
            return 2
        if args.command == "hook-session":
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "SessionStart",
                            "additionalContext": prompt_context(repo),
                        }
                    }
                )
            )
            return 0
        _parser().print_help()
        return 0
    except (PermissionError, ValueError) as exc:
        print(f"adop: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
