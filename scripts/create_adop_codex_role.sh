#!/usr/bin/env bash
set -euo pipefail

# Run this from an AWS-connected terminal. It creates the operator role used
# by local Codex/MCP tools and grants the selected IAM user permission to
# assume it. No credentials are read or printed by this script.

ADOP_PROFILE="${AWS_PROFILE:-default}"
ADOP_REGION="${AWS_REGION:-us-east-1}"
ADOP_ROLE_NAME="${ADOP_ROLE_NAME:-adop-codex-operator}"
ADOP_USER_NAME="${ADOP_USER_NAME:-demo-profile}"
ADOP_ROLE_PROFILE="${ADOP_ROLE_PROFILE:-adop-codex}"
ADOP_POLICY_FILE="${ADOP_POLICY_FILE:-docs/iam/adop-codex-operator-policy.json}"

if [[ ! -f "${ADOP_POLICY_FILE}" ]]; then
  echo "Policy file not found: ${ADOP_POLICY_FILE}" >&2
  echo "Run this script from the repository root." >&2
  exit 1
fi

ADOP_ACCOUNT_ID="$(
  aws sts get-caller-identity \
    --profile "${ADOP_PROFILE}" \
    --query Account \
    --output text
)"
ADOP_USER_ARN="arn:aws:iam::${ADOP_ACCOUNT_ID}:user/${ADOP_USER_NAME}"
ADOP_TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "${ADOP_TEMP_DIR}"' EXIT

cat > "${ADOP_TEMP_DIR}/trust-policy.json" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustAdopOperator",
      "Effect": "Allow",
      "Principal": {
        "AWS": "${ADOP_USER_ARN}"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

cat > "${ADOP_TEMP_DIR}/assume-role-policy.json" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeAdopCodexOperator",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::${ADOP_ACCOUNT_ID}:role/${ADOP_ROLE_NAME}"
    }
  ]
}
EOF

echo "Using AWS profile: ${ADOP_PROFILE}"
echo "Using region: ${ADOP_REGION}"
echo "Target account: ${ADOP_ACCOUNT_ID}"
echo "Creating role: ${ADOP_ROLE_NAME}"

if aws iam get-role \
  --profile "${ADOP_PROFILE}" \
  --role-name "${ADOP_ROLE_NAME}" \
  >/dev/null 2>&1; then
  aws iam update-assume-role-policy \
    --profile "${ADOP_PROFILE}" \
    --role-name "${ADOP_ROLE_NAME}" \
    --policy-document "file://${ADOP_TEMP_DIR}/trust-policy.json"
else
  aws iam create-role \
    --profile "${ADOP_PROFILE}" \
    --region "${ADOP_REGION}" \
    --role-name "${ADOP_ROLE_NAME}" \
    --description "ADOP Codex operator access to repository AWS tools" \
    --assume-role-policy-document "file://${ADOP_TEMP_DIR}/trust-policy.json" \
    --tags Key=Project,Value=ADOP Key=ManagedBy,Value=Codex
fi

aws iam put-role-policy \
  --profile "${ADOP_PROFILE}" \
  --role-name "${ADOP_ROLE_NAME}" \
  --policy-name adop-codex-tool-access \
  --policy-document "file://${ADOP_POLICY_FILE}"

aws iam put-user-policy \
  --profile "${ADOP_PROFILE}" \
  --user-name "${ADOP_USER_NAME}" \
  --policy-name adop-assume-codex-operator \
  --policy-document "file://${ADOP_TEMP_DIR}/assume-role-policy.json"

aws configure set role_arn \
  "arn:aws:iam::${ADOP_ACCOUNT_ID}:role/${ADOP_ROLE_NAME}" \
  --profile "${ADOP_ROLE_PROFILE}"
aws configure set source_profile \
  "${ADOP_PROFILE}" \
  --profile "${ADOP_ROLE_PROFILE}"
aws configure set region \
  "${ADOP_REGION}" \
  --profile "${ADOP_ROLE_PROFILE}"

aws iam get-role \
  --profile "${ADOP_PROFILE}" \
  --role-name "${ADOP_ROLE_NAME}" \
  --query 'Role.[RoleName,Arn]' \
  --output table

echo
echo "Role created/updated."
echo "Role profile created: ${ADOP_ROLE_PROFILE}"
echo "Verify it with:"
echo "  aws sts get-caller-identity --profile ${ADOP_ROLE_PROFILE}"
echo "Use it for Codex/MCP:"
echo "  export AWS_PROFILE=${ADOP_ROLE_PROFILE}"
