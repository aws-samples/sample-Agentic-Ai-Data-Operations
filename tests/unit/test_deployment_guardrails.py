import pytest

from shared.utils.deployment_guardrails import (
    DeploymentGuardrailError,
    require_tbac_principals,
    require_workload_glue_role,
    validate_deployment_preflight,
    validate_glue_policy,
)


def _answers():
    return {
        "iac_target_framework": "terraform",
        "iac_query_principal_arn": "arn:aws:iam::123456789012:role/orders-query",
        "iac_tbac_principals": [
            {
                "role_arn": "arn:aws:iam::123456789012:role/orders-reader",
                "allowed_classifications": ["NONE", "LOW"],
            }
        ],
    }


def _policy():
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject", "kms:Decrypt"],
                "Resource": [
                    "arn:aws:s3:::lake/bronze/customer-orders/*",
                    "arn:aws:kms:us-east-1:123456789012:key/example",
                ],
            }
        ],
    }


def test_accepts_workload_scoped_glue_role():
    assert (
        require_workload_glue_role(
            "customer_orders",
            "arn:aws:iam::123456789012:role/customer-orders-glue-service-role",
        )
        == "customer-orders-glue-service-role"
    )


def test_rejects_shared_glue_role():
    with pytest.raises(DeploymentGuardrailError, match="workload-scoped"):
        require_workload_glue_role(
            "customer_orders", "adop-workshop-glue-service-role"
        )


def test_rejects_unbounded_iam_wildcards():
    bad = _policy()
    bad["Statement"][0]["Action"] = "s3:*"
    with pytest.raises(DeploymentGuardrailError, match="wildcard Action"):
        validate_glue_policy(bad)

    bad = _policy()
    bad["Statement"][0]["Resource"] = "*"
    with pytest.raises(DeploymentGuardrailError, match="unbounded"):
        validate_glue_policy(bad)


def test_requires_explicit_tbac_principals():
    with pytest.raises(DeploymentGuardrailError, match="cannot be empty"):
        require_tbac_principals({})


def test_preflight_requires_framework_and_validates_all_inputs():
    context = {"workload_name": "customer_orders", "human_answers": _answers()}
    result = validate_deployment_preflight(
        context,
        glue_role_name="customer-orders-glue-service-role",
        glue_policy=_policy(),
    )
    assert result["iac_target_framework"] == "terraform"
    assert result["iac_query_principal_arn"].endswith("orders-query")
    assert result["glue_policy_validated"] is True


def test_preflight_blocks_missing_framework():
    answers = _answers()
    del answers["iac_target_framework"]
    with pytest.raises(DeploymentGuardrailError, match="target_framework"):
        validate_deployment_preflight(
            {"workload_name": "customer_orders", "human_answers": answers}
        )


def test_preflight_requires_explicit_query_principal():
    answers = _answers()
    del answers["iac_query_principal_arn"]
    with pytest.raises(DeploymentGuardrailError, match="query_principal"):
        validate_deployment_preflight(
            {"workload_name": "customer_orders", "human_answers": answers}
        )
