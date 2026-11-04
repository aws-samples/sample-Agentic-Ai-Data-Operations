# ADOP Console deployment modes

This document is the deployment contract for the ADOP control plane. It keeps
the local POC path simple while making the AWS path safe enough to become a
shared sandbox or production foundation.

## 1. Local mode

Local mode is for developers, POCs, demos, and offline CLI onboarding.

```bash
python3 -m api.local_server
```

Open `http://127.0.0.1:4173`.

Default behavior:

- the Python API and static UI run on the same machine;
- the control-plane store is `/tmp/adop-control-plane.json`;
- local test identities exercise organization, domain, project, security, and
  connector roles;
- workspace selection is sent with each request and checked by the API;
- policies and contracts are proposal/approval gated in the local store;
- connector tests are real only when the required driver, network, and
  credential reference are available;
- the CLI uses the same normalized workspace and authorization decisions as
  the UI, but local mode is still soft isolation inside one checkout.

Local mode must not be used with production credentials. For local connector
tests, prefer a disposable database or a local test service and use
environment-variable references. Do not commit a password, token, private key,
or cloud resource identifier.

The local server binds to `127.0.0.1` by default and rejects browser requests
from origins other than the local console origin. The local test identity
headers are a development adapter, not a portable authentication mechanism.
Use AWS mode for shared users or any real tenant boundary.

To exercise the DynamoDB adapter locally without deploying the browser, set:

```bash
ADOP_CONTROL_PLANE_BACKEND=dynamodb \
ADOP_CONTROL_PLANE_TABLE=adop-control-plane-dev \
python3 -m api.local_server
```

That command is an adapter test, not a complete AWS deployment. IAM, KMS,
Secrets Manager, VPC networking, OIDC, and CloudTrail still need the AWS mode.

## 2. AWS mode

AWS mode is for a shared sandbox, staging, or production environment. The
current CloudFormation foundation creates the environment-neutral control
plane:

```text
CloudFront → private S3 UI
          → API Gateway HTTP API
          → Lambda control-plane API
          → DynamoDB configuration, approvals, and audit
          → Cognito or external OIDC claims
```

The deployment script is:

```bash
./infra/cloudformation/deploy.sh \
  --stack adop-console-dev \
  --region us-east-1 \
  --environment dev \
  --callback-url https://console.example.com/ \
  --logout-url https://console.example.com/ \
  --hosted-ui-prefix adop-example-dev \
  --allowed-origin https://console.example.com
```

For Okta or Entra, Cognito can broker the external OIDC provider. The
provider's client secret is a deployment input and must be supplied through a
secure deployment mechanism; it must not be committed or placed in the UI
bundle. The API still performs authorization after token validation. Group
claims are mapped to ADOP roles, and workspace membership is checked again for
each request.

### AWS storage responsibilities

| Data | AWS location | Rule |
|---|---|---|
| Contract and policy proposals | DynamoDB | Immutable proposal versions; approval advances the current pointer |
| Effective configuration | DynamoDB snapshot | A run resolves once and records a snapshot ID/hash |
| Connector metadata | DynamoDB | Store type, endpoint metadata, scope, status, and secret reference only |
| Passwords, tokens, keys | Secrets Manager | Write-only from the browser; decrypt only for an authorized test/runtime role |
| Encryption keys | KMS | Use customer-managed keys where the environment requires independent key policy and rotation control |
| Connector network path | VPC, Glue Connection, or private test Lambda | No public database exposure for production connectors |
| Audit | DynamoDB plus CloudTrail | Record actor, workspace, action, result, and affected version |

The browser must never read a secret value. A connector test returns only a
health state, duration, provider, and redacted error class. A successful test
does not grant a workload access; a separate connector binding and workload
authorization check is still required.

AWS draft connector tests are disabled because accepting caller-supplied host
and port values would let a user turn the control-plane Lambda into a network
probe. Save the connector first; the persisted record contains only the
scope, provider, and secret reference, and the health check resolves endpoint
metadata from the authorized secret.

The CloudFormation Lambda role reads only Secrets Manager names under
`adop/<environment>/*`. Use `adop/dev/*` for AWS Dev, `adop/staging/*` for
staging, and `adop/prod/*` for production. A connector may still store a full
secret ARN, but the ARN must resolve inside the deployed environment prefix.

## 3. Local-to-AWS parity

The following behavior must be identical in both modes:

1. organization/domain/project scope parsing;
2. role-to-feature permissions;
3. project visibility and soft isolation;
4. contract schema and inheritance validation;
5. approval rules and stale-version checks;
6. CLI authorization versus UI/API authorization;
7. connector status semantics (`Not tested`, `Healthy`, `Auth failed`,
   `Network failed`, and `Driver unavailable`);
8. audit event shape.

The CLI connector commands use the same contract:

```bash
adop login --user hcherian@example.com --workspace project/orders
adop connector list
adop connector test --name rds_connector_e2e
```

They print connector metadata and redacted health only. They never print the
Secrets Manager value. In AWS mode, the CLI must run with an identity that has
the appropriate scoped read/test permission and IAM permission to resolve the
secret through the approved connector path.

The following behavior is intentionally adapter-specific:

1. local JSON versus DynamoDB persistence;
2. local test identity versus OIDC/Cognito claims;
3. environment-variable connector references versus Secrets Manager;
4. local API process versus API Gateway/Lambda;
5. local connector network versus VPC/Glue/private connectivity.

## 4. Deployment readiness boundary

The current template is a foundation, not a claim that every production
control is complete. Before calling an AWS environment production-ready,
verify all of the following in that environment:

- OIDC redirect/logout URLs and issuer/audience validation;
- least-privilege Lambda, test, and workload IAM roles;
- Secrets Manager resource policies and KMS key policy;
- Lambda/VPC connectivity for private connector tests;
- WAF, TLS, security headers, and CloudFront access logging;
- DynamoDB PITR, backup/restore test, and deletion protection policy;
- CloudTrail, API logs, connector-test logs, alarms, and retention;
- explicit organization/domain/project membership fixtures;
- real CLI/UI parity tests against the same identity claims;
- run-bootstrap wiring that selects the file snapshot provider in Local mode
  and the DynamoDB snapshot provider in AWS mode, followed by a snapshot-hash
  assertion in the workload run context;
- a tested teardown path for temporary connector resources.

The UI/API persistence path is not itself a runtime promotion mechanism.
Approved AWS proposals must be promoted to an immutable `CURRENT` snapshot and
the ADOP run bootstrap must consume that snapshot before the AWS deployment is
end-to-end complete. This boundary is intentional so a browser edit cannot
change an already-running workload or silently bypass repository review.

The temporary RDS test described in the E2E plan must not be added as an
always-on resource to the console stack. It belongs in a separate test stack
or an explicitly approved test run with a hard cleanup step.

## 5. Lessons applied from the MCP gateway registry

The ADOP design follows the useful deployment patterns demonstrated by the MCP
gateway registry:

- keep identity providers pluggable instead of hard-coding one IdP;
- make local Docker/development and cloud deployment paths explicit;
- use authorization-code/OIDC flows for browser users and token-based
  authorization for service calls;
- map directory groups/scopes to application roles;
- keep provider-specific configuration in environment or deployment values;
- offer more than one infrastructure target while keeping the application
  contract stable.

ADOP differs in one important way: its organization/domain/project contract
hierarchy and run snapshot are domain-specific, so policy and contract
resolution remains a shared ADOP library used by both the UI API and CLI.

