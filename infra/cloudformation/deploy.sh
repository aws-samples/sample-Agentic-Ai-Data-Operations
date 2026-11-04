#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./infra/cloudformation/deploy.sh \
#     --stack adop-console-dev \
#     --region us-east-1 \
#     --callback-url https://console.example.com/ \
#     --logout-url https://console.example.com/ \
#     --hosted-ui-prefix adop-example-dev
#
# This script owns packaging and publishing only. CloudFormation remains the
# source of truth for infrastructure, and all environment-specific values are
# command-line parameters or AWS configuration.

STACK=""
REGION="${AWS_REGION:-us-east-1}"
CALLBACK_URL=""
LOGOUT_URL=""
HOSTED_UI_PREFIX=""
ENVIRONMENT="dev"
ALLOWED_ORIGIN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stack) STACK="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --callback-url) CALLBACK_URL="$2"; shift 2 ;;
    --logout-url) LOGOUT_URL="$2"; shift 2 ;;
    --hosted-ui-prefix) HOSTED_UI_PREFIX="$2"; shift 2 ;;
    --environment) ENVIRONMENT="$2"; shift 2 ;;
    --allowed-origin) ALLOWED_ORIGIN="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$STACK" || -z "$CALLBACK_URL" || -z "$LOGOUT_URL" || -z "$HOSTED_UI_PREFIX" || -z "$ALLOWED_ORIGIN" ]]; then
  echo "stack, callback-url, logout-url, hosted-ui-prefix, and allowed-origin are required" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if ! command -v sam >/dev/null 2>&1; then
  echo "The AWS deployment requires the AWS SAM CLI (sam)." >&2
  exit 2
fi

BUILD_DIR="${ADOP_SAM_BUILD_DIR:-$ROOT/.aws-sam/adop-console-build}"
rm -rf "$BUILD_DIR"
sam build \
  --template-file "$ROOT/infra/cloudformation/template.yaml" \
  --build-dir "$BUILD_DIR" \
  --no-cached

sam deploy \
  --template-file "$BUILD_DIR/template.yaml" \
  --region "$REGION" \
  --stack-name "$STACK" \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    EnvironmentName="$ENVIRONMENT" \
    CallbackUrl="$CALLBACK_URL" \
    LogoutUrl="$LOGOUT_URL" \
    HostedUiDomainPrefix="$HOSTED_UI_PREFIX" \
    AllowedOrigin="$ALLOWED_ORIGIN"

BUCKET="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='UiBucketName'].OutputValue" --output text)"
aws s3 sync "$ROOT/ui" "s3://$BUCKET" --region "$REGION" \
  --exclude "chromium.*" \
  --exclude "README.md" \
  --exclude ".gitignore" \
  --exclude "test-results/*" \
  --exclude "*.map" \
  --delete

echo "Console deployed. Upload target: s3://$BUCKET"
aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='ConsoleUrl'].OutputValue" --output text
