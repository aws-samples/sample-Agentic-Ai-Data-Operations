"""Control-plane validation shared by local API and Lambda handlers."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from .repository import RepositoryProjection


class ValidationFailure(ValueError):
    """A user-editable proposal failed validation."""


def validate_cedar_policy(
    repository: RepositoryProjection, policy_id: str, content: str
) -> dict[str, Any]:
    if not content.strip():
        raise ValidationFailure("Policy content cannot be empty")
    if len(content.encode("utf-8")) > 256 * 1024:
        raise ValidationFailure("Policy content exceeds the 256 KiB limit")
    if any(token in content.lower() for token in ("password=", "secret=", "private_key")):
        raise ValidationFailure("Secrets are not permitted in policy content")
    relative_path = repository.get_policy(policy_id)["path"]
    normalized = PurePosixPath(relative_path)
    if ".." in normalized.parts or not str(normalized).startswith("shared/policies/"):
        raise ValidationFailure("Policy path is outside shared/policies")
    try:
        import cedarpy

        result = cedarpy.validate_policies(content, repository.cedar_schema())
        if not result.validation_passed:
            errors = getattr(result, "diagnostics", None) or getattr(result, "errors", None)
            raise ValidationFailure(f"Cedar validation failed: {errors or result}")
        return {"valid": True, "engine": "cedarpy"}
    except ImportError:
        # The project declares cedarpy as a required dependency. This fallback
        # keeps the local API useful in a minimal Python environment but never
        # claims full semantic validation.
        if content.count("{") != content.count("}") or content.count("(") != content.count(")"):
            raise ValidationFailure("Policy delimiters are unbalanced")
        if "permit" not in content and "forbid" not in content:
            raise ValidationFailure("Policy must contain permit or forbid")
        return {"valid": True, "engine": "structural-fallback"}
