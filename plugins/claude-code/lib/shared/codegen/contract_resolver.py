"""Vendored ADOP organization/domain/project contract enforcement."""

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
    """Raised when an effective contract is missing or weakened."""


def policy_hash(policy: Mapping[str, Any]) -> str:
    raw = json.dumps(policy, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ContractPolicyError(f"Contract policy not found: {path}") from None
    except yaml.YAMLError as exc:
        raise ContractPolicyError(f"Invalid contract policy {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractPolicyError(f"Contract policy must be an object: {path}")
    return value


def _root(start: Path) -> Path:
    path = Path(start).resolve()
    module_root = Path(__file__).resolve().parents[2]
    for candidate in (path, *path.parents, module_root):
        if (candidate / "contracts" / "policies").is_dir():
            return candidate
    raise ContractPolicyError("Unable to locate contracts/policies")


def _validated(path: Path, schema_path: Path) -> dict[str, Any]:
    policy = _load(path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = [
        error.message
        for error in jsonschema.Draft202012Validator(schema).iter_errors(policy)
    ]
    if errors:
        raise ContractPolicyError("; ".join(errors))
    return policy


def _merge(base: dict[str, Any], overlay: Mapping[str, Any], source: str) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in {"contract_id", "version", "scope"}:
            result[key] = value
        elif isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merge(dict(result[key]), value, source)
        elif key == "minimum_quality_threshold":
            if result.get(key) is not None and value < result[key]:
                raise ContractPolicyError(f"{source} lowers {key}")
            result[key] = value
        elif key == "allowed_source_formats":
            current = result.get(key)
            narrowed = sorted(set(current) & set(value)) if current else list(value)
            if not narrowed:
                raise ContractPolicyError(f"{source} removes every allowed source format")
            result[key] = narrowed
        elif key == "pii_detection_required":
            if result.get(key) is True and value is False:
                raise ContractPolicyError(f"{source} disables mandatory PII detection")
            result[key] = bool(result.get(key)) or bool(value)
        elif key in {"required_format", "mutability", "encryption_at_rest", "encryption_in_transit"}:
            if result.get(key) is not None and result[key] != value:
                raise ContractPolicyError(f"{source} contradicts {key}")
            result[key] = value
        else:
            result[key] = copy.deepcopy(value)
    return result


def _validate_override(override, schema_path):
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


def resolve_effective_policy(workload_dir: Path, *, scope=None, run_overrides=None):
    root = _root(workload_dir)
    schema_path = root / POLICY_SCHEMA_RELATIVE_PATH
    policy = _validated(root / POLICY_RELATIVE_PATH, schema_path)
    policy["organization_version"] = policy["version"]
    values = dict(scope or {})
    context_path = Path(workload_dir) / "run" / "context.json"
    if context_path.exists():
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context_scope = context.get("scope") or {}
        for key in ("organization", "domain", "project"):
            values.setdefault(key, context_scope.get(key))
        if run_overrides is None:
            run_overrides = (context.get("human_answers") or {}).get("contract_overrides")
    for level in ("domain", "project"):
        name = values.get(level)
        if not name:
            continue
        if not _SCOPE_NAME.fullmatch(str(name)):
            raise ContractPolicyError(f"Invalid {level} policy name")
        path = root / "contracts" / "policies" / f"{level}s" / f"{name}.yaml"
        if path.exists():
            overlay = _validated(path, schema_path)
            policy[f"{level}_version"] = overlay["version"]
            policy = _merge(policy, overlay, f"{level} policy")
    if run_overrides:
        policy = _merge(
            policy, _validate_override(run_overrides, schema_path), "workload override"
        )
    policy["effective_hash"] = policy_hash(policy)
    policy["scope"] = "workload"
    return policy


def validate_zone_contract(spec, spec_type, workload_dir=None, *, policy=None):
    if spec_type not in {"bronze", "silver", "gold"}:
        return []
    effective = dict(policy or resolve_effective_policy(workload_dir or Path.cwd()))
    zone = effective.get("zones", {}).get(spec_type, {})
    errors = []
    if spec_type == "bronze":
        allowed = zone.get("allowed_source_formats") or []
        if spec.get("source_format") and spec["source_format"] not in allowed:
            errors.append(f"source_format {spec['source_format']!r} is not allowed")
    else:
        if zone.get("required_format") == "iceberg" and not (
            spec.get("iceberg_database") and spec.get("iceberg_table")
        ):
            errors.append(f"{spec_type} must declare iceberg_database and iceberg_table")
        minimum = zone.get("minimum_quality_threshold")
        if minimum is not None and (
            not isinstance(spec.get("quality_threshold"), (int, float))
            or spec["quality_threshold"] < minimum
        ):
            errors.append(f"{spec_type} quality_threshold must be at least {minimum:.2f}")
    return errors
