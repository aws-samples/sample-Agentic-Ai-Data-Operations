# ADOP Codex IAM role

`adop-codex-operator-policy.json` contains the AWS permissions used by the
repository's MCP servers, onboarding workflow, optional AgentCore deployment,
Bedrock calls, and documented verification/deployment commands.

Create or update the role from an AWS-connected terminal:

```bash
cd /path/to/sample-Agentic-Ai-Data-Operations
export AWS_PROFILE=default
export AWS_REGION=us-east-1
export ADOP_USER_NAME=demo-profile

bash scripts/create_adop_codex_role.sh
```

The script creates or updates `adop-codex-operator`, trusts only the selected
IAM user, attaches the repository policy as an inline role policy, and grants
that user permission to assume the role. It also creates the local AWS CLI
profile `adop-codex`, which chains through `default` without copying keys.

Verify the role after creation:

```bash
aws sts get-caller-identity --profile adop-codex
```

Use the role for Codex and its MCP servers:

```bash
export AWS_PROFILE=adop-codex
export AWS_REGION=us-east-1
```

This policy is intentionally read-only. It does not create IAM roles, attach
policies, assume arbitrary roles, pass roles to services, retrieve secret
values, or mutate data-plane resources. Deployment permissions must be provided
through a separate role with workload-specific ARNs, permissions boundaries,
and explicit `iam:PassedToService` conditions.
