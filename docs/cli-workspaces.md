# ADOP CLI workspaces

ADOP keeps the organization/domain/project selection in a local session outside
the repository. Codex, Claude Code, Kiro, and the Strands runtime use the same
resolver and the same session shape.

The session contains the signed-in identity, memberships, selected workspace,
and a session identifier. It does not contain OAuth access, ID, refresh tokens,
connector passwords, or other secrets. The default location is:

```text
~/.adop/sessions/<repository-hash>.json
```

Set `ADOP_WORKSPACE_SESSION` when a CI runner or an isolated environment needs
an explicit session path.

## Local test login

After installing the repository in editable mode:

```bash
pip install -e .
adop login --user oliver.orders@example.com
adop workspace list
adop workspace use project/orders
adop whoami
adop check --workload customer_orders
```

Organization administrators can create persisted domain and project workspaces
from the CLI. The command uses the same control-plane store as the UI:

```bash
adop workspace create \
  --level domain \
  --name finance \
  --label "Finance data domain"

adop workspace create \
  --level project \
  --name billing \
  --label "Billing project" \
  --parent domain/finance
```

In local mode this writes to the configured JSON control-plane store. In AWS
mode, set `ADOP_ENV=aws`, `ADOP_CONTROL_PLANE_BACKEND=dynamodb`, and
`ADOP_CONTROL_PLANE_TABLE` so the command writes to the same DynamoDB table
used by the console. Only an identity with the `org-admin` role can create
workspaces; assigning other users to a new scope remains an identity-provider
membership operation.

The seeded local identities are:

```text
hcherian@example.com         organization admin
maya.chen@example.com       organization admin
sara.sales@example.com      sales domain owner
oliver.orders@example.com   orders project user
lina.claims@example.com     claims project user
```

The `hcherian` username is also accepted as an alias:

```bash
adop login --user hcherian
```

For a source checkout without installing the entry point, use:

```bash
python3 -m shared.control_plane.workspace_context login \
  --user oliver.orders@example.com --workspace project/orders
```

## SSO or CI identity

The UI uses Cognito/OIDC. A CLI integration can pass the normalized claims to
the same resolver without copying a browser token into the repository:

```bash
export ADOP_IDENTITY_JSON='{"sub":"00u-example","email":"user@example.com","name":"User","provider":"oidc","groups":["adop-project-orders-users"]}'
python3 -m shared.control_plane.workspace_context login
```

The supported group names are:

```text
adop-org-admins
adop-domain-<name>-owners
adop-domain-<name>-users
adop-project-<name>-owners
adop-project-<name>-users
```

An actual Okta, Entra, or another OIDC device/browser login can populate these
claims; the scope resolver does not depend on the identity provider.

## Agent behavior

At SessionStart/AgentSpawn, each platform receives the current identity,
accessible workspaces, and a prompt to select one if none is active:

```text
ADOP WORKSPACE CONTEXT
  signed in as: Oliver Orders <oliver.orders@example.com>
  current:     project/orders
  accessible:  project/orders
  isolation:   workload writes are restricted to the selected workspace.
```

The shared Cedar gate then enforces the selection for workload paths. It
restricts path-based reads/searches and writes, so an orders project agent
cannot read or edit `workloads/claims/**`. A missing selection blocks workload
access and tells the agent to ask the user to choose a workspace.

This is soft isolation inside a shared checkout. It prevents agent/tool
operations through the ADOP hooks, but it is not an operating-system boundary.
For hard isolation, run each project in a separate checkout/container and use
project-scoped IAM roles.

## AWS account guard

ADOP identity and AWS identity are separate: MCP servers, the `aws` CLI, and
boto3 use whatever credentials the machine resolves (`AWS_PROFILE`,
`~/.aws`). On a fresh clone or a shared laptop those may belong to a different
account. Pin the account your session is allowed to use:

```bash
adop login --user <email> --workspace project/orders --aws-account <12-digit-id>
adop aws-check        # exit 0 = match, 1 = not pinned/unavailable, 2 = mismatch
```

`ADOP_EXPECTED_AWS_ACCOUNT` overrides the session pin (useful in CI). The pin
lives only in `~/.adop/sessions/`, never in the repository. When the pinned and
active accounts differ, the session-start context for Claude Code, Codex, and
Kiro shows an `AWS ACCOUNT MISMATCH -- STOP` instruction.
