"""GitHub App bridge for Cedar policy proposals.

The bridge is disabled unless all GitHub App settings are present. It uses
short-lived installation tokens and never stores a GitHub credential in a
control-plane record.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class GitHubBridgeError(RuntimeError):
    """Raised when a GitHub App operation cannot be completed."""


@dataclass(frozen=True)
class PullRequestRef:
    number: int
    url: str
    branch: str


class GitHubAppBridge:
    def __init__(
        self,
        *,
        repository: str,
        app_id: str,
        installation_id: str,
        private_key: str,
        api_base: str = "https://api.github.com",
    ):
        self.repository = repository
        self.app_id = app_id
        self.installation_id = installation_id
        self.private_key = private_key
        self.api_base = api_base.rstrip("/")

    @classmethod
    def from_environment(cls) -> "GitHubAppBridge | None":
        repository = os.getenv("ADOP_GITHUB_REPOSITORY")
        app_id = os.getenv("ADOP_GITHUB_APP_ID")
        installation_id = os.getenv("ADOP_GITHUB_INSTALLATION_ID")
        secret_id = os.getenv("ADOP_GITHUB_PRIVATE_KEY_SECRET_ID")
        if not all((repository, app_id, installation_id, secret_id)):
            return None
        try:
            import boto3

            response = boto3.client("secretsmanager").get_secret_value(
                SecretId=secret_id
            )
            secret = response.get("SecretString") or ""
            value = json.loads(secret) if secret.startswith("{") else {"private_key": secret}
            private_key = value.get("private_key")
        except Exception as exc:
            raise GitHubBridgeError("Unable to load GitHub App private key") from exc
        if not private_key:
            raise GitHubBridgeError("GitHub App secret does not contain private_key")
        return cls(
            repository=repository,
            app_id=app_id,
            installation_id=installation_id,
            private_key=private_key,
            api_base=os.getenv("ADOP_GITHUB_API_BASE", "https://api.github.com"),
        )

    def create_policy_pull_request(
        self,
        *,
        path: str,
        content: str,
        change_id: str,
        policy_id: str,
        base: str = "main",
    ) -> PullRequestRef:
        self._validate_path(path)
        token = self._installation_token()
        repository = urllib.parse.quote(self.repository, safe="/")
        base_ref = self._request(
            "GET", f"/repos/{repository}/git/ref/heads/{urllib.parse.quote(base)}", token
        )
        base_sha = base_ref["object"]["sha"]
        branch = f"adop/policy-{change_id}"
        self._request(
            "POST",
            f"/repos/{repository}/git/refs",
            token,
            {"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        encoded_path = urllib.parse.quote(path, safe="/")
        existing = self._request(
            "GET",
            f"/repos/{repository}/contents/{encoded_path}?ref={urllib.parse.quote(base)}",
            token,
        )
        self._request(
            "PUT",
            f"/repos/{repository}/contents/{encoded_path}",
            token,
            {
                "message": f"adop: propose Cedar policy update {policy_id}",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": branch,
                "sha": existing.get("sha"),
            },
        )
        pull_request = self._request(
            "POST",
            f"/repos/{repository}/pulls",
            token,
            {
                "title": f"ADOP policy proposal: {policy_id}",
                "head": branch,
                "base": base,
                "body": (
                    f"Control-plane change `{change_id}`.\n\n"
                    "Cedar validation and ADOP approval checks are required before merge."
                ),
            },
        )
        return PullRequestRef(
            number=int(pull_request["number"]),
            url=str(pull_request["html_url"]),
            branch=branch,
        )

    def _installation_token(self) -> str:
        try:
            import jwt

            now = int(time.time())
            app_jwt = jwt.encode(
                {"iat": now - 30, "exp": now + 540, "iss": self.app_id},
                self.private_key,
                algorithm="RS256",
            )
        except ImportError as exc:
            raise GitHubBridgeError(
                "GitHub App support requires the control-plane dependency extra"
            ) from exc
        except Exception as exc:
            raise GitHubBridgeError("Unable to sign GitHub App token") from exc
        response = self._request(
            "POST",
            f"/app/installations/{self.installation_id}/access_tokens",
            app_jwt,
            None,
            app_token=True,
        )
        return str(response["token"])

    def _request(
        self,
        method: str,
        path: str,
        token: str,
        body: dict[str, Any] | None = None,
        *,
        app_token: bool = False,
    ) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_base}{path}",
            data=payload,
            method=method,
            headers={
                "accept": "application/vnd.github+json",
                "authorization": f"Bearer {token}",
                "content-type": "application/json",
                "user-agent": "adop-control-plane",
                "x-github-api-version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            # Keep GitHub response bodies out of the API error because they may
            # contain repository metadata or token-adjacent diagnostics.
            raise GitHubBridgeError(
                f"GitHub App request failed ({exc.code})"
            ) from exc
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise GitHubBridgeError("GitHub App request could not be completed") from exc

    @staticmethod
    def _validate_path(path: str) -> None:
        if not path.startswith("shared/policies/") or ".." in path.split("/"):
            raise GitHubBridgeError("GitHub bridge may only edit shared/policies/**")
