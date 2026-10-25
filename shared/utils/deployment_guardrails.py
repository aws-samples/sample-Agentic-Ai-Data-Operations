"""Pre-deployment guardrails shared by the ADOP deploy path.

These checks are deliberately local and deterministic.  They do not call AWS;
the deployer runs them before any MCP or CLI mutation.

The deployment phase has three human-owned inputs that cannot be inferred:

* the IaC framework;
* the Lake Formation TBAC principals and their classification ceilings.
* the IAM role used for query verification.

Glue execution roles are workload-owned.  A shared platform role must never be
expanded to accommodate a workload, even when the requested permissions look
small.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional


class DeploymentGuardrailError(ValueError):
    """Raised when a deployment input violates an ADOP preflight rule."""


_FRAMEWORKS = {"terraform", "cdk_python", "cdk_typescript", "cloudformation"}
_CLASSIFICATIONS = {"NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
_ROLE_ARN_RE = re.compile(
    r"^arn:(?:aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/[^*]+$"
)
_WORKLOAD_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def workload_glue_role_name(workload_name: str) -> str:
    """Return the only permitted Glue execution-role name for a workload."""
    if not _WORKLOAD_RE.fullmatch(workload_name):
        raise DeploymentGuardrailError(
            f"Invalid workload name for Glue role: {workload_name!r}"
        )
    return f"{workload_name.replace('_', '-')}-glue-service-role"


def _role_name(role_name_or_arn: str) -> str:
    value = str(role_name_or_arn).strip()
    if not value:
        return ""
    return value.rsplit("/", 1)[-1] if value.startswith("arn:") else value


def require_workload_glue_role(workload_name: str, role_name_or_arn: str) -> str:
    """Reject shared or unexpectedly named Glue execution roles."""
    expected = workload_glue_role_name(workload_name)
    actual = _role_name(role_name_or_arn)
    if actual != expected:
        raise DeploymentGuardrailError(
            f"Glue execution role must be workload-scoped: expected "
            f"{expected!r}, received {role_name_or_arn!r}"
        )
    return expected


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def validate_glue_policy(policy_document: Mapping[str, Any]) -> None:
    """Reject wildcard IAM actions/resources in a Glue workload policy.

    A suffix wildcard in an otherwise exact S3 prefix is allowed because it
    scopes access to the objects below that prefix.  Unbounded ``Resource:
    "*"`` and service-wide actions remain blocked.
    """
    statements = _as_list(policy_document.get("Statement"))
    if not statements:
        raise DeploymentGuardrailError("Glue policy must contain Statement entries")

    for index, statement in enumerate(statements):
        if not isinstance(statement, Mapping):
            raise DeploymentGuardrailError(
                f"Glue policy Statement[{index}] must be an object"
            )
        actions = [str(action) for action in _as_list(statement.get("Action"))]
        resources = [str(resource) for resource in _as_list(statement.get("Resource"))]
        if any(action == "*" or action.endswith(":*") for action in actions):
            raise DeploymentGuardrailError(
                f"Glue policy Statement[{index}] contains wildcard Action"
            )
        if any(resource == "*" for resource in resources):
            raise DeploymentGuardrailError(
                f"Glue policy Statement[{index}] contains unbounded Resource '*'"
            )
        if not actions or not resources:
            raise DeploymentGuardrailError(
                f"Glue policy Statement[{index}] must declare Action and Resource"
            )


def require_tbac_principals(human_answers: Mapping[str, Any]) -> list[Dict[str, Any]]:
    """Validate the human-provided TBAC grant list; never infer principals."""
    principals = human_answers.get("iac_tbac_principals")
    if not isinstance(principals, list) or not principals:
        raise DeploymentGuardrailError(
            "human_answers.iac_tbac_principals is required and cannot be empty; "
            "do not derive a principal from PII columns or the current IAM caller"
        )

    validated: list[Dict[str, Any]] = []
    for index, principal in enumerate(principals):
        if not isinstance(principal, Mapping):
            raise DeploymentGuardrailError(
                f"iac_tbac_principals[{index}] must be an object"
            )
        role_arn = principal.get("role_arn")
        ceilings = principal.get("allowed_classifications")
        if not isinstance(role_arn, str) or not _ROLE_ARN_RE.fullmatch(role_arn):
            raise DeploymentGuardrailError(
                f"iac_tbac_principals[{index}].role_arn must be a concrete IAM role ARN"
            )
        if not isinstance(ceilings, list) or not ceilings:
            raise DeploymentGuardrailError(
                f"iac_tbac_principals[{index}].allowed_classifications cannot be empty"
            )
        unknown = set(ceilings) - _CLASSIFICATIONS
        if unknown:
            raise DeploymentGuardrailError(
                f"iac_tbac_principals[{index}] has unknown classifications: "
                f"{sorted(unknown)}"
            )
        validated.append(
            {
                "role_arn": role_arn,
                "allowed_classifications": list(ceilings),
            }
        )
    return validated


def require_query_principal(human_answers: Mapping[str, Any]) -> str:
    """Require the explicit role used for post-deployment query verification."""
    principal = human_answers.get("iac_query_principal_arn")
    if not isinstance(principal, str) or not _ROLE_ARN_RE.fullmatch(principal):
        raise DeploymentGuardrailError(
            "human_answers.iac_query_principal_arn must be a concrete IAM role ARN "
            "for Athena/query verification"
        )
    return principal


def validate_deployment_preflight(
    run_context: Mapping[str, Any],
    *,
    glue_role_name: Optional[str] = None,
    glue_policy: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate all deployment inputs before touching AWS."""
    answers = run_context.get("human_answers")
    if not isinstance(answers, Mapping):
        raise DeploymentGuardrailError("run context is missing human_answers")

    framework = answers.get("iac_target_framework")
    if framework not in _FRAMEWORKS:
        raise DeploymentGuardrailError(
            "human_answers.iac_target_framework is required before deployment"
        )

    principals = require_tbac_principals(answers)
    query_principal = require_query_principal(answers)
    workload_name = str(run_context.get("workload_name", ""))
    result: Dict[str, Any] = {
        "workload_name": workload_name,
        "iac_target_framework": framework,
        "iac_tbac_principals": principals,
        "iac_query_principal_arn": query_principal,
    }

    if glue_role_name is not None:
        result["glue_role_name"] = require_workload_glue_role(
            workload_name, glue_role_name
        )
    if glue_policy is not None:
        validate_glue_policy(glue_policy)
        result["glue_policy_validated"] = True
    return result
