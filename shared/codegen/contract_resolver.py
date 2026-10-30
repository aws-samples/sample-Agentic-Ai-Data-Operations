"""Resolve and enforce ADOP's organization/domain/project zone contracts.

JSON Schemas define the shape of a spec. This module defines the effective
governance policy applied to that spec:

    organization -> domain -> project -> workload run

Lower scopes may add stricter requirements, never weaken or contradict a
higher-scope policy. The organization policy is always present; optional
domain/project files and per-run answers are layered on top when available.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

import jsonschema
import yaml


POLICY_RELATIVE_PATH = Path("contracts/policies/organization/default.yaml")
POLICY_SCHEMA_RELATIVE_PATH = Path("contracts/policies/zone_policy.schema.json")
_SCOPE_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,60}$")


class ContractPolicyError(ValueError):
    """Raised when an effective contract is missing or attempts to weaken policy."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def policy_hash(policy: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(policy).encode("utf-8")).hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ContractPolicyError(f"Contract policy not found: {path}") from None
    except yaml.YAMLError as exc:
        raise ContractPolicyError(f"Invalid contract policy {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractPolicyError(f"Contract policy must be an object: {path}")
    return value


def _policy_root(start: Path) -> Path:
    path = Path(start).resolve()
    module_root = Path(__file__).resolve().parents[2]
    candidates = [path, *path.parents, module_root]
    for candidate in candidates:
        if (candidate / "contracts" / "policies").is_dir():
            return candidate
    raise ContractPolicyError("Unable to locate contracts/policies from the workload path")


def _load_and_validate(path: Path, schema_path: Path) -> dict[str, Any]:
    policy = _load_yaml(path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = [
        error.message
        for error in jsonschema.Draft202012Validator(schema).iter_errors(policy)
    ]
    if errors:
        raise ContractPolicyError(
            f"Contract policy failed validation against {schema_path}: "
            + "; ".join(errors)
        )
    return policy


def _scope_path(root: Path, scope: str, name: str | None) -> Path | None:
    if not name:
        return None
    path = root / "contracts" / "policies" / f"{scope}s" / f"{name}.yaml"
    return path if path.exists() else None


def _merge(base: dict[str, Any], overlay: Mapping[str, Any], source: str) -> dict[str, Any]:
    """Merge an overlay while rejecting weakening changes."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in {"contract_id", "version", "scope"}:
            if key == "scope":
                result[key] = value
            elif key == "version":
                result[key] = value
            else:
                result[key] = value
            continue
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merge(dict(result[key]), value, source)
            continue
        if key == "minimum_quality_threshold":
            current = result.get(key)
            if current is not None and value < current:
                raise ContractPolicyError(
                    f"{source} lowers minimum_quality_threshold from {current} to {value}"
                )
            result[key] = value
            continue
        if key == "allowed_source_formats":
            current = result.get(key)
            if current is not None:
                narrowed = sorted(set(current) & set(value))
                if not narrowed:
                    raise ContractPolicyError(
                        f"{source} removes every allowed source format"
                    )
                result[key] = narrowed
            else:
                result[key] = list(value)
            continue
        if key == "pii_detection_required":
            if result.get(key) is True and value is False:
                raise ContractPolicyError(
                    f"{source} disables mandatory PII detection"
                )
            result[key] = bool(result.get(key)) or bool(value)
            continue
        if key in {"required_format", "mutability", "encryption_at_rest", "encryption_in_transit"}:
            current = result.get(key)
            if current is not None and current != value:
                raise ContractPolicyError(
                    f"{source} contradicts {key}: {current!r} vs {value!r}"
                )
            result[key] = value
            continue
        result[key] = copy.deepcopy(value)
    return result


def _load_optional_policy(
    root: Path, scope: str, name: str | None, schema_path: Path
) -> dict[str, Any] | None:
    path = _scope_path(root, scope, name)
    return _load_and_validate(path, schema_path) if path else None


def _validate_run_override(
    override: Mapping[str, Any], schema_path: Path
) -> dict[str, Any]:
    unknown = set(override) - {"zones", "controls"}
    if unknown:
        raise ContractPolicyError(
            f"workload override contains unsupported keys: {sorted(unknown)}"
        )
    candidate = {
        "contract_id": "adop.workload.override",
        "version": "1.0.0",
        "scope": "workload",
        **dict(override),
    }
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = [
        error.message
        for error in jsonschema.Draft202012Validator(schema).iter_errors(candidate)
    ]
    if errors:
        raise ContractPolicyError("Invalid workload contract override: " + "; ".join(errors))
    return dict(override)


def resolve_effective_policy(
    workload_dir: Path,
    *,
    scope: Mapping[str, str | None] | None = None,
    run_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve the organization baseline and optional stricter overlays."""
    root = _policy_root(workload_dir)
    schema_path = root / POLICY_SCHEMA_RELATIVE_PATH
    policy = _load_and_validate(root / POLICY_RELATIVE_PATH, schema_path)
    policy["organization_version"] = policy["version"]

    values = dict(scope or {})
    context_path = Path(workload_dir) / "run" / "context.json"
    if context_path.exists():
        try:
            context = json.loads(context_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractPolicyError(f"Invalid run context for contract resolution: {exc}") from exc
        context_scope = context.get("scope") or {}
        if isinstance(context_scope, Mapping):
            for key in ("organization", "domain", "project"):
                values.setdefault(key, context_scope.get(key))
        answers = context.get("human_answers") or {}
        if run_overrides is None and isinstance(answers, Mapping):
            run_overrides = answers.get("contract_overrides")

    for level in ("domain", "project"):
        if values.get(level) and not _SCOPE_NAME.fullmatch(str(values[level])):
            raise ContractPolicyError(f"Invalid {level} policy name")
        overlay = _load_optional_policy(root, level, values.get(level), schema_path)
        if overlay:
            policy[f"{level}_version"] = overlay["version"]
            policy = _merge(policy, overlay, f"{level} policy")
    if run_overrides:
        policy = _merge(
            policy,
            _validate_run_override(run_overrides, schema_path),
            "workload contract override",
        )

    policy["effective_hash"] = policy_hash(policy)
    policy["scope"] = "workload"
    return policy


def validate_zone_contract(
    spec: Mapping[str, Any],
    spec_type: str,
    workload_dir: Path | None = None,
    *,
    policy: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return governance errors for a zone spec after JSON Schema validation."""
    if spec_type not in {"bronze", "silver", "gold"}:
        return []
    effective = dict(policy or resolve_effective_policy(workload_dir or Path.cwd()))
    zone = effective.get("zones", {}).get(spec_type, {})
    errors: list[str] = []

    if spec_type == "bronze":
        source_format = spec.get("source_format")
        allowed = zone.get("allowed_source_formats") or []
        if source_format and allowed and source_format not in allowed:
            errors.append(
                f"source_format {source_format!r} is not allowed by the effective Bronze contract"
            )
    else:
        required_format = zone.get("required_format")
        if required_format == "iceberg" and not (
            spec.get("iceberg_database") and spec.get("iceberg_table")
        ):
            errors.append(
                f"{spec_type} must declare iceberg_database and iceberg_table"
            )
        threshold = spec.get("quality_threshold")
        minimum = zone.get("minimum_quality_threshold")
        if minimum is not None and (not isinstance(threshold, (int, float)) or threshold < minimum):
            errors.append(
                f"{spec_type} quality_threshold must be at least {minimum:.2f}"
            )

    return errors
