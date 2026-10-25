import json
from pathlib import Path


POLICY_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "iam" / "adop-codex-operator-policy.json"
)


def _policy_actions() -> set[str]:
    policy = json.loads(POLICY_PATH.read_text())
    return {
        action
        for statement in policy["Statement"]
        for action in statement["Action"]
    }


def test_operator_policy_has_no_iam_escalation_actions():
    actions = _policy_actions()
    assert not actions.intersection(
        {
            "iam:CreateRole",
            "iam:PutRolePolicy",
            "iam:DeleteRolePolicy",
            "iam:AttachRolePolicy",
            "iam:AttachUserPolicy",
            "iam:AttachGroupPolicy",
            "iam:PassRole",
            "sts:AssumeRole",
        }
    )


def test_operator_policy_has_no_wildcard_service_permissions():
    actions = _policy_actions()
    assert not any(action.endswith(":*") for action in actions)


def test_operator_policy_does_not_retrieve_secrets_or_mutate_s3_objects():
    actions = _policy_actions()
    assert "secretsmanager:GetSecretValue" not in actions
    assert "s3:GetObject" not in actions
    assert "s3:PutObject" not in actions
    assert "s3:DeleteObject" not in actions
