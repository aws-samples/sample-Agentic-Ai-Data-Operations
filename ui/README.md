# ADOP Console prototype

This is the ADOP control-plane UI. It mirrors the repository's current
contract model and the authoritative `customer_orders` run context, and can
connect to the local Python control-plane API.

Start the UI and API together from the repository root:

```bash
python3 -m api.local_server
```

Then open `http://127.0.0.1:4173`.

The UI is static in both modes. In Local mode, `api.local_server` serves the
static files and the Python control-plane API from the same localhost origin.
In AWS mode, the same `ui/` files are uploaded to the private S3 origin behind
CloudFront, and `/api/*` is routed to API Gateway and Lambda. This keeps the
browser contract the same while changing only the deployment adapters.

## Chromium validation

Install the test dependency and run the local suite from a fresh clone:

```bash
npm install
npm run test:chromium:local
```

The Playwright configuration starts or reuses `127.0.0.1:4173`. AWS mode tests
are opt-in:

```bash
ADOP_AWS_CONSOLE_URL=https://<cloudfront-domain> \
ADOP_AWS_TEST_USER=<email> \
ADOP_AWS_TEST_PASSWORD=<temporary-password> \
npm run test:chromium -- chromium.aws.spec.js
```

The default local backend persists control-plane proposals atomically in
`/tmp/adop-control-plane.json`. Use DynamoDB instead by setting:

```bash
ADOP_CONTROL_PLANE_BACKEND=dynamodb \
ADOP_CONTROL_PLANE_TABLE=adop-control-plane-dev \
python3 -m api.local_server
```

The local API never writes `shared/policies/**`. Cedar edits are stored as
approval-gated proposals. Each policy proposal is explicitly scoped to
`organization/default`, a domain, or a project. Domain and project policies
inherit the organization policy and are held in the control plane until a
workload-aware Cedar resolver is enabled.

Contracts use the same hierarchy. `GET /api/v1/contracts` returns the
organization layer, optional domain/project overlays, and the resolver's
effective policy. `POST /api/v1/contracts/proposals` validates a scoped
contract against the schema and tighten-only rules before storing a
two-approver proposal. A production GitHub App bridge can consume approved
Cedar proposals and create the required pull requests; approved contract
snapshots can be promoted to DynamoDB `CURRENT` records for future runs.
The current console does not silently make those records active in an
already-running workload: Local and AWS run bootstraps still need to select the
corresponding file or DynamoDB snapshot provider and record its hash.

Connector health is not seeded or simulated. Configure a connector in the UI
with a Secrets Manager reference, then use `Test connection` or `Test all`.
The backend runs a provider query when its driver is installed:

```bash
pip install -e '.[control-plane,connector-drivers]'
```

Snowflake secrets must contain JSON such as
`{"username":"...","password":"..."}`. The API returns only status, timing,
and a redacted error class; it never returns secret values. A connector with
no configured secret or missing provider driver is shown as `Not tested`, not
`Healthy`.

In AWS mode, save the connector before testing it. Draft tests are disabled in
AWS mode so the API cannot be used to probe arbitrary host/port combinations;
the saved connector health check resolves endpoint details from its
environment-scoped Secrets Manager secret.

## Login, workspaces, and feature permissions

After login, the workspace selector sends the selected
`organization/default`, `domain/<name>`, or `project/<name>` scope with every
API request. The API repeats the membership check and records workspace
selection in the audit stream. This is soft isolation: it protects UI/API
actions and agent context inside a shared checkout, but hard tenant isolation
still requires separate AWS accounts, roles, or environments.

Organization administrators have a **Workspaces** section for creating
persisted domain and project scopes. The UI calls `POST /api/v1/workspaces`;
the CLI uses the same registry with:

```bash
adop workspace create --level domain --name finance --label "Finance domain"
adop workspace create --level project --name billing --parent domain/finance
```

Local deployments persist the registry in the local control-plane JSON store.
AWS deployments persist it in the configured DynamoDB control-plane table.
Creating a workspace does not automatically grant access to other users;
membership is still managed through Cognito, Okta, Entra, or the configured
identity provider.

The Access page is visible to organization administrators and shows directory
users, workspace memberships, and feature grants. Roles currently map to:

```text
org-admin        all governance, connector, approval, audit, and user features
domain-owner     domain governance, connectors, proposals, and approvals
project-user     assigned workloads, contracts, policies, and connector tests
security-admin   Cedar policies, validation, approvals, and audit
connector-admin  connector registration, health checks, and approvals
auditor/viewer   read-only governance and audit access
```

In production, user creation and membership assignment remain owned by the
configured Cognito/Okta/Entra directory. The console consumes role and group
claims and enforces feature permissions again in the API.
