# ADOP UI/UX and Multi-Tenant QA Report

Date: 2026-11-04  
Mode tested: Local control plane on `127.0.0.1:4173`  
AWS surface smoke-tested: `https://drt09ono76e8y.cloudfront.net`  
Browser: Playwright 1.64.1, Chromium, headless  

## Executive result

The local UI passes the baseline and adversarial Chromium suites:

```text
Baseline smoke:      6 passed
Adversarial suite:   7 passed
```

The shared CLI workspace context also enforces project isolation for the seeded
users. The CloudFront deployment serves the UI and Cognito auth configuration
successfully, but a full AWS login was not executed because no AWS test-user
password was supplied to the test environment.

The QA pass found one real UI defect: feature-gated administration buttons had
the `hidden` attribute but remained visible because the navigation CSS declared
`display: flex` without an explicit `[hidden]` override. This was fixed in
`ui/styles.css` and verified by the passing adversarial suite.

## Severity-ranked anomalies

### P0 — none

No data exposure, authentication bypass, cross-project read, or browser-blocking
failure was found in the tested local flows.

### P1 — production workflow gaps

1. **Invite user is not implemented in the console.** The Access page's
   `Invite user` action only displays a message that provisioning belongs to
   Cognito/Okta/Entra. This is correct for directory ownership, but the UI does
   not yet provide a directory deep link, invitation hand-off, or membership
   mapping workflow. Admins can view access but cannot complete onboarding from
   this console.

2. **Real AWS authentication was not end-to-end tested.** CloudFront and the
   Cognito configuration respond correctly, and the local suite verifies an
   Okta-style OIDC authorization request, but a real Cognito user/password was
   not available for this run. Run the opt-in AWS test after supplying a
   temporary test identity.

3. **Real provider connector health was not verified against Snowflake or RDS.**
   The local suite verified that a Snowflake connector can be submitted with
   only a Secrets Manager ARN and blank endpoint fields. It did not call a real
   provider because no test secret/database credentials were supplied. The
   backend correctly reports an untested connector instead of claiming health.

### P2 — expected prototype limitations or baseline issues

1. `New workload` intentionally stops at the human discovery gate and does not
   create a workload. This is consistent with the repository's human-in-the-
   loop policy, but it is not a complete onboarding transaction in the UI.

2. The complete repository unit suite is not green because the existing
   QuickSight tests require the missing
   `workloads/customer_master/config/analytics.yaml` fixture:

   ```text
   389 passed, 31 failed, 15 errors, 1 skipped
   ```

   This failure is outside the ADOP Console changes. No workload configuration
   was invented to make those tests pass.

3. Local seeded identities are test identities, not a replacement for an
   enterprise directory. Production identity and membership remain owned by
   Cognito, Okta, Entra, or IAM Identity Center claims.

### P3 — minor UX observations

1. Denied out-of-scope API requests can return either `403` or a scope-safe
   `404` depending on whether the request fails authorization before contract
   resolution. Both prevent disclosure, but the API error contract could be
   standardized for easier client diagnostics.

2. The current responsive check validates overflow and clickable controls. It
   does not yet compare screenshot snapshots across browsers or against a
   visual baseline.

## Automated scenarios

The complete executable Playwright script is:

- [`ui/chromium.adversarial.spec.js`](ui/chromium.adversarial.spec.js)

Run it with:

```bash
cd ui
npx playwright test chromium.adversarial.spec.js --workers=1
```

The script covers:

| Scenario | Assertion |
|---|---|
| Mobile, tablet, desktop | No horizontal overflow; controls have usable bounds |
| Invalid workspace input | Script/unsafe names are rejected; double submit does not create a valid workspace |
| Malformed contract JSON | Validation error is shown and editor content remains intact |
| Policy editor injection text | Adversarial HTML remains inert in the textarea; Cedar validation still runs |
| Secret-only Snowflake connector | ARN is accepted with host, port, and database blank; secret text is not rendered |
| Oliver project user | Orders workload/project visible; claims access denied |
| Lina project user | Claims workspace visible; orders workload hidden and cross-project access denied |
| Sara domain owner | Organization-only Access and Workspaces navigation is hidden; domain contract is review-only |

The existing baseline suite remains at:

- [`ui/chromium.smoke.spec.js`](ui/chromium.smoke.spec.js)

```bash
cd ui
npm run test:chromium:local
```

## CLI isolation scenarios

The CLI checks used the same seeded identities and the same workspace model as
the UI:

```bash
ADOP_WORKSPACE_SESSION=/tmp/adop-cli-qa-session.json \
python3 -m shared.control_plane.workspace_context login \
  --user oliver.orders@example.com --workspace project/orders

ADOP_WORKSPACE_SESSION=/tmp/adop-cli-qa-session.json \
python3 -m shared.control_plane.workspace_context check \
  --workload customer_orders --json
# allowed: true

ADOP_WORKSPACE_SESSION=/tmp/adop-cli-qa-session.json \
python3 -m shared.control_plane.workspace_context check \
  --workload claims --json
# allowed: false
```

Additional checks passed for:

- `lina.claims@example.com`: denied `customer_orders` from `project/claims`
- `sara.sales@example.com`: allowed `customer_orders` from `domain/sales`
- `hcherian@example.com`: created a domain and project workspace through the CLI
- Created CLI workspaces appeared in the same local registry model used by the UI
- The live local store contained no disposable connector record or secret value

## Workflow log

| Workflow | Result | Evidence |
|---|---|---|
| Discover framework | Pass | Static HTML/CSS/vanilla JS UI, Python API |
| Discover test tooling | Pass | Playwright 1.64.1; no Cypress/Vitest required |
| Start local application | Pass | `python3 -m api.local_server --host 127.0.0.1 --port 4173` |
| Local login | Pass | Maya, H Cherian, Sara, Oliver, and Lina seeded identities |
| Navigation | Pass | Home, Workloads, Runs, Contracts, Policies, Connectors, Approvals, Audit, Access, Workspaces |
| Workspace selection | Pass | Organization/domain/project scopes are reflected in API requests |
| Organization/domain/project isolation | Pass | UI filtering and API denial verified |
| Contract proposal validation | Pass | Invalid JSON rejected; project proposal path validates |
| Policy view and Cedar validation | Pass | Editor opens and validation toast appears |
| Connector submission | Pass | Secret ARN-only Snowflake draft saved as not tested |
| Connector real health | Not run | No provider credentials or RDS test resource supplied |
| Responsive layout | Pass | 390x844, 768x1024, and 1440x900 |
| SSO provider behavior | Pass | Mock Okta-style PKCE authorization request |
| AWS static deployment | Pass | CloudFront returned HTTP 200 |
| AWS auth configuration | Pass | CloudFront API returned Cognito/OIDC configuration |
| AWS full login | Not run | Temporary Cognito test password not supplied |
| Full repository unit tests | Partial | ADOP/control-plane tests pass; unrelated QuickSight fixture fails |

## Security observations

- No secret value was entered into the connector form or persisted in the local
  control-plane store.
- Policy and contract edits remain proposal/approval flows; the UI does not
  directly overwrite repository policy files.
- Project users cannot see another project in the workspace picker or workload
  list.
- API requests repeat scope checks; UI filtering is not the only control.
- The policy textarea safely treats injected HTML as text.
- This QA pass did not attempt destructive AWS actions, real credential
  harvesting, or prompt execution against production systems.

## Recommended next tests

1. Create a temporary Cognito user and run `ui/chromium.aws.spec.js`.
2. Provision an ephemeral PostgreSQL RDS instance and run
   `ui/chromium.rds.connector.spec.js`.
3. Add an SSO directory hand-off/membership mapping flow to the Access page.
4. Add screenshot baselines for Chromium, Firefox, and WebKit.
5. Restore or add the missing QuickSight analytics fixture so the full
   repository suite can run cleanly.
