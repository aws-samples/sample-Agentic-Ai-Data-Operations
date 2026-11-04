# ADOP Console CloudFormation deployment

The console is designed to move between environments without changing UI code:

```
browser → CloudFront → private S3 UI
                   └→ API Gateway HTTP API → Lambda → DynamoDB
                                      └→ Cognito/OIDC claims
```

`template.yaml` creates the S3 bucket, CloudFront distribution, API Gateway
HTTP API, Lambda wiring, DynamoDB control-plane table, and Cognito user pool.
The same stack is usable for `dev`, `test`, `staging`, and `prod`; only stack
parameters and AWS credentials change.

## Deploy

Prerequisites: AWS CLI, AWS SAM CLI, and an AWS identity allowed to create the
listed resources. `requirements.txt` at the repository root is used by SAM to
bundle the Lambda's Python dependencies.

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

The script deploys infrastructure first, then uploads the static `ui/` assets
to the private bucket. It does not create local passwords or place secrets in
the browser. Add users to Cognito and map them to `adop-org-admins`,
`adop-domain-owners`, or `adop-project-users`.

The browser flow is generic OIDC: Okta, Entra ID, Keycloak, and other OIDC
providers use the same authorization-code + PKCE path. Cognito can broker that
provider by setting `ExternalOidcProviderName`, `ExternalOidcIssuer`,
`ExternalOidcClientId`, and `ExternalOidcClientSecret` during deployment. The
client secret is a deployment parameter only; it is not exposed to the UI.
Direct OIDC deployments can instead provide `ADOP_OIDC_*` environment values to
the API.

The Lambda package must include the repository modules under `api/`, `shared/`,
and the contract files that the repository projection reads. For a production
pipeline, run `sam build` in CI and deploy the generated artifact from the
versioned build. The current local server remains the fastest development path.

Terraform can later consume the same inputs and outputs (`EnvironmentName`,
`CallbackUrl`, `LogoutUrl`, `HostedUiDomainPrefix`, `AllowedOrigin`) without
changing the API contract or UI.
