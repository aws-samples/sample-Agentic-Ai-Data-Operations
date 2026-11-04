# ADOP control-plane and connector E2E plan

This is the execution plan for validating the local and AWS control plane with
Chromium/Playwright, API tests, CLI checks, and an ephemeral RDS connector.
The plan is intentionally staged: local tests are safe to run now; AWS/RDS
tests require an explicit environment and cost boundary.

## 1. Test identities and scopes

Use separate identities, not one account with a role toggle:

| Identity | Expected access |
|---|---|
| `org-admin` | Organization, domain, project, users, policies, contracts, connectors, approvals, and audit |
| `domain-owner` | Assigned domain and eligible projects; may propose project changes; organization/domain contract changes are review-only |
| `project-user` | Assigned project workloads and project contracts/policies; cannot see another project |
| `security-admin` | Cedar policy validation, approval, and audit surfaces |
| `connector-admin` | Connector registration, health checks, and connector approvals |
| `auditor` | Read-only governance and audit views |

The fixtures must include at least:

```text
organization/default
├── domain/sales
│   ├── project/customer-orders
│   └── project/claims
└── domain/finance
    └── project/ledger
```

The negative cases are as important as the positive cases:

- a claims user cannot list or read customer-orders;
- a domain owner cannot propose an organization or domain contract change;
- a project user cannot approve their own proposal;
- a user cannot use a workspace selector to gain membership;
- an approved change in sales cannot alter finance state;
- CLI and UI return the same allow/deny result for the same identity, scope,
  resource, and action.

## 2. Local Chromium/Playwright pass

Run the local server:

```bash
python3 -m api.local_server
```

Then run the browser suite:

```bash
npx playwright test ui/chromium.smoke.spec.js
```

The local suite must cover:

1. login and logout;
2. organization/domain/project workspace switching;
3. dashboard, workloads, and runs;
4. connector list, new connector modal, validation, test, and test-all;
5. contract inheritance and effective hash;
6. organization/domain/project edit visibility;
7. policy view, proposal, Cedar validation, and approval;
8. approval queue and second-approver behavior;
9. audit log and access page;
10. empty, unauthorized, malformed, stale-version, and backend-error states.

The local suite proves UI behavior and API authorization. It does not prove
AWS IAM, Secrets Manager, VPC routing, or a real external provider.

## 3. Ephemeral AWS/RDS connector pass

This test is billable and must be run only in an approved sandbox account.
Before creation, record:

- AWS account and region;
- VPC and private subnet IDs;
- security group IDs and allowed test source;
- database engine/version and instance class;
- maximum test duration and budget owner;
- Secrets Manager secret name prefix;
- teardown owner and deadline.

For this local-runner experiment, use the separate
[`rds-connector-test.yaml`](../infra/cloudformation/rds-connector-test.yaml)
stack in the default VPC. It uses encrypted storage and a temporary dedicated
security group restricted to the test runner's `/32`; it is publicly
reachable only because the local browser/API process is outside the VPC.
Production connectors must use private subnets and a private Lambda, Glue
Connection, or workload path instead.

Credentials must be generated into Secrets Manager. Do not put the password in
CloudFormation parameters, browser storage, DynamoDB, logs, or a command
history. The connector metadata should contain only a secret ARN/reference and
non-sensitive endpoint metadata.

Test sequence:

1. create the temporary RDS test stack;
2. wait for the instance to become available;
3. verify the test Lambda/worker can reach the private endpoint;
4. open the UI as `connector-admin` or `org-admin`;
5. use `+ New connector` and register the JDBC profile;
6. run `Test connection` and require `Healthy`;
7. run `Test all` and confirm the same result appears in the list;
8. open the connector metadata and confirm no credential value is returned;
9. log in through the CLI with the same user/workspace;
10. run `adop connector list` and `adop connector test --name <name>` and verify
    the CLI receives the same authorization
    decision and secret reference behavior;
11. test bad credentials, wrong port, wrong project membership, and missing
    driver/network paths;
12. verify redacted errors and audit records;
13. remove the connector binding and temporary secret;
14. delete the RDS test stack;
15. confirm the instance, security group, secret, logs, and test artifacts are
    gone or retained only according to the approved retention policy.

The test passes only if the resource is reachable, the credentials are
retrieved by the authorized backend path, the UI reports the real health
result, the CLI and UI agree on access, and teardown succeeds.

## 4. UI/API/CLI parity matrix

For every row, run the action in the UI and the equivalent CLI/API operation.

| Operation | Org admin | Domain owner | Project user | Expected parity |
|---|---:|---:|---:|---|
| Read organization contract | allow | read | read | same effective hash |
| Propose organization contract | allow | deny | deny | same denial code |
| Propose domain contract | allow | deny | deny | same denial code |
| Propose project contract | allow | allow when eligible | allow when eligible | schema validated first |
| Approve own proposal | deny | deny | deny | two-person approval |
| Read assigned connector | allow | allow in domain | allow in project | same scope filter |
| Test connector | allow | allow if feature granted | allow if feature granted | health result is redacted |
| Read another project | allow when admin policy permits | deny | deny | no selector bypass |
| Read audit | allow | assigned scope | assigned scope/read-only | same filtered events |

If a UI/API result differs from the CLI result, stop the release. The shared
authorization adapter, identity normalization, or workspace context is out of
sync.

## 5. Required evidence

Store test evidence outside generated workload artifacts:

- Playwright report and screenshots for each role;
- API test output and response codes;
- CLI transcript with secrets removed;
- connector health results and redacted failure cases;
- DynamoDB proposal/approval/audit records;
- CloudTrail event IDs for secret access and infrastructure changes;
- RDS stack outputs and teardown confirmation;
- local-versus-AWS parity summary.

Do not mark the AWS connector feature production-ready until all evidence is
present and the teardown check passes.

## 6. Current boundary

The existing local Chromium suite and control-plane unit suite cover the
repository-backed UI/API behavior. The real RDS portion is not yet executed
because creating an RDS instance requires an AWS account, network placement,
and a cost-approved teardown boundary. Once those are supplied, add a
separate temporary test template and run this plan; do not alter the default
console CloudFormation stack to create RDS automatically.

