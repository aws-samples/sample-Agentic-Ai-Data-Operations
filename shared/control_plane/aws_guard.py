"""Guard against running ADOP agents with AWS credentials for the wrong account.

ADOP identity and AWS identity are separate: MCP servers, the ``aws`` CLI and
boto3 use whatever credentials the machine resolves (``AWS_PROFILE``,
``~/.aws``). On a fresh clone or a shared laptop those can belong to a
different -- possibly production -- account. The expected account is pinned
per user session (``adop login --aws-account``) or through
``ADOP_EXPECTED_AWS_ACCOUNT``; it is never stored in the repository.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable

ACCOUNT_PATTERN = re.compile(r"^\d{12}$")
EXPECTED_ENV = "ADOP_EXPECTED_AWS_ACCOUNT"


def validate_account(value: str) -> str:
    account = str(value or "").strip()
    if not ACCOUNT_PATTERN.fullmatch(account):
        raise ValueError("AWS account must be a 12-digit account ID")
    return account


def expected_account(session: dict[str, Any] | None) -> str:
    """The pinned account: environment first, then the user's session."""
    configured = os.environ.get(EXPECTED_ENV, "").strip()
    if configured:
        return validate_account(configured)
    pinned = str((session or {}).get("aws_account") or "").strip()
    return validate_account(pinned) if pinned else ""


def resolve_current_account() -> tuple[str, str]:
    """Return (account, profile) for the credentials boto3 resolves right now."""
    import boto3
    from botocore.config import Config

    profile = os.environ.get("AWS_PROFILE", "") or "default"
    client = boto3.client(
        "sts",
        config=Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 1}),
    )
    return str(client.get_caller_identity()["Account"]), profile


def check(
    session: dict[str, Any] | None,
    resolver: Callable[[], tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Compare the pinned account with the active credentials.

    status: ``ok`` | ``mismatch`` | ``unpinned`` | ``unavailable``.
    """
    try:
        expected = expected_account(session)
    except ValueError as exc:
        return {"status": "mismatch", "expected": "", "actual": "", "profile": "", "detail": str(exc)}
    if not expected:
        return {"status": "unpinned", "expected": "", "actual": "", "profile": "",
                "detail": "No AWS account pinned; run `adop login --aws-account <id>` or set "
                          f"{EXPECTED_ENV}."}
    try:
        actual, profile = (resolver or resolve_current_account)()
    except Exception as exc:  # no credentials, expired SSO session, network
        return {"status": "unavailable", "expected": expected, "actual": "", "profile": "",
                "detail": f"Could not resolve AWS credentials ({type(exc).__name__})."}
    if actual != expected:
        return {"status": "mismatch", "expected": expected, "actual": actual, "profile": profile,
                "detail": f"AWS credentials (profile {profile}) are for account {actual}, "
                          f"but this ADOP session is pinned to {expected}."}
    return {"status": "ok", "expected": expected, "actual": actual, "profile": profile,
            "detail": f"AWS credentials (profile {profile}) match the pinned account."}


def context_lines(result: dict[str, Any]) -> list[str]:
    """Lines appended to the agent's session-start context."""
    status = result["status"]
    if status == "ok":
        return [f"  aws account: {result['actual']} (matches pinned account)"]
    if status == "unpinned":
        return ["  aws account: not pinned -- run `adop login --aws-account <id>` before AWS work"]
    if status == "unavailable":
        return [f"  aws account: {result['detail']} Do not run AWS or MCP tools until resolved."]
    return [
        "  AWS ACCOUNT MISMATCH -- STOP: " + result["detail"],
        "  Do not run AWS CLI, MCP, deploy, or data tools in this session. Switch AWS_PROFILE "
        "or re-pin with `adop login --aws-account <id>`, then run `adop aws-check`.",
    ]
