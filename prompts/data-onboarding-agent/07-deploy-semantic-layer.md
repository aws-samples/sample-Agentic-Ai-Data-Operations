# 07 — DEPLOY: Semantic Layer Infrastructure + NL Query Agent

> Phase 7 (optional). Deploy the consolidated VKG ontology, R2RML mappings, and ontology-slice retrieval index to AWS, then provision a SPARQL/NL-query agent on Bedrock AgentCore.
>
> ⚠️ **First-workload onboarding is a multi-session effort, not a single autopilot pass.** When this is the **first** workload being onboarded (semantic-layer infrastructure does not yet exist in the account), expect 4–6 focused turns of porting work before `cdk deploy` even begins, plus 25–40 min deploy time, plus 2–3 debug rounds. Estimated ~$590/month running cost in `us-west-2 dev`. **Always confirm the budget commitment with the user before any `cdk deploy`** — not just before `cdk synth`. Surface the cost early and explicitly.
>
> For **subsequent workloads** (infra already exists, detected via `core` MCP / CloudFormation describe), Phase 7 is a much lighter artifact-push: ontology TTL → Neptune Loader, R2RML TTL → Ontop S3 + ECS rolling restart, ontology-slice re-index in OpenSearch (atomic alias swap), agent container rebuild + AgentCore runtime update. No new infra, no new monthly spend, ~5–10 min wall time.

## Purpose

Take the consolidated artifacts produced by Phase 6 (`semantic-layer/ontology.ttl`, `semantic-layer/r2rml-mappings.ttl`) and deploy them to a runnable serving stack:

1. **Detect-and-branch**: check whether the semantic-layer infrastructure is already provisioned. If absent, provision it via CDK. If present, push artifact updates only.
2. **Neptune** — load the OWL ontology (SPARQL endpoint for ontology context retrieval).
3. **Ontop ECS Fargate** — host the Virtual Knowledge Graph server with R2RML mappings → SPARQL-to-SQL translation against Athena.
4. **OpenSearch Serverless** — vector index of ontology-slice embeddings (for the SPARQL agent's `get_ontology_slice` tool).
5. **OBQC Lambda** — deterministic SPARQL validation against OWL domain/range constraints.
6. **Bedrock AgentCore** — provision a 5-tool SPARQL/NL agent (`semantic-layer/agent/sparql_agent/`). Detect existing agent by name; create if missing.

## Hard Scope Boundary

### You DO

1. Detect existing semantic-layer infra by querying for the CDK stack name `AdopSemanticLayer{environment}`.
2. If absent: emit + apply a CDK stack (TypeScript) at `semantic-layer/infra/`. Stack provisions VPC, Neptune cluster, Ontop ECS Fargate service, OpenSearch Serverless collection, OBQC Lambda, Athena workgroup, IAM roles, and Bedrock AgentCore runtime.
3. If present: skip provisioning. Push artifact updates only.
4. Load `semantic-layer/ontology.ttl` into Neptune via the Neptune Loader Lambda (replace mode — full ontology re-load, since it's a small in-memory T-Box).
5. Push `semantic-layer/r2rml-mappings.ttl` to the Ontop ECS service's S3 config bucket and trigger an ECS service redeploy (rolling, with health-check gate).
6. Build ontology-slice embeddings: chunk the ontology into per-class slices (class + properties + neighbors), embed each via Bedrock Titan v2, index in OpenSearch Serverless under collection `adop-semantic-slices`.
7. Build/refresh the OBQC Lambda code from `semantic-layer/ontology.ttl` (Lambda at `semantic-layer/lambdas/obqc/` validates SPARQL against OWL domain/range queried from Neptune at request time).
8. Provision the SPARQL/NL agent on Bedrock AgentCore — the 5-tool agent at `semantic-layer/agent/sparql_agent/`:
   - `extract_terms` — parse NL question → entity/metric/temporal terms
   - `get_ontology_slice` — query OpenSearch for relevant ontology context
   - `validate_sparql` — call OBQC Lambda
   - `execute_sparql` — call Ontop service
   - `repair_sparql` — fix invalid SPARQL (≤ 3 attempts)
   - System prompt + tool specs live at `agent/sparql_agent/`. Deployed as a Bedrock AgentCore runtime with name `adop-semantic-agent-{environment}`.
9. Run end-to-end smoke tests: 3 canned NL questions against deployed agent → assert SPARQL generated, validated, executed, returned non-empty result.
10. Emit `semantic-layer/deployment_manifest.json` with: stack name, Neptune endpoint, Ontop endpoint, OpenSearch endpoint, agent ARN, OBQC Lambda ARN, deployment timestamp, ontology version deployed.

### You DO NOT

- ❌ Deploy without the Phase 6 artifacts present and passing tests. If `semantic-layer/ontology.ttl` is missing or invalid, refuse and direct user to Phase 6.
- ❌ Hardcode account IDs, VPC IDs, or bucket names — derive from `CDK_DEFAULT_ACCOUNT` and stack outputs.
- ❌ Drop and recreate Neptune on artifact updates — the cluster is expensive to provision and the ontology fits in memory; always push via the loader, never replace the cluster.
- ❌ Modify Phase 6 artifacts. If the agent finds the artifacts inconsistent, halt and ask the user to re-run Phase 6.
- ❌ Skip the smoke tests. A "successful deploy" with zero query verification is a failure, not a success.

## When You Run

Invoked manually after Phase 6 produces (or refreshes) `semantic-layer/ontology.ttl` + `semantic-layer/r2rml-mappings.ttl`. Typical trigger:
> "Deploy the semantic layer."

Preconditions:
- `semantic-layer/ontology.ttl` and `semantic-layer/r2rml-mappings.ttl` exist and pass `pytest semantic-layer/tests/`.
- All workloads referenced in `manifest.json` have deployed Gold tables (verified via `glue-athena` MCP `get_table`).

## Inputs

| Input | Source | Required |
|---|---|---|
| `environment` | user (`dev`/`staging`/`prod`) | Yes (default `dev`) |
| `aws_account_id` | `CDK_DEFAULT_ACCOUNT` | Yes (auto-derived) |
| `aws_region` | `CDK_DEFAULT_REGION` | Yes (auto-derived) |
| `agent_name` | derived: `adop-semantic-agent-{environment}` | No |
| `stack_name` | derived: `AdopSemanticLayer{environment}` | No |
| `bedrock_model_id` | for SPARQL agent | No (default `anthropic.claude-sonnet-4-6-v1:0`) |

## Workflow

### Step 1 — Preflight

- Check Phase 6 artifacts exist + pass tests.
- Run `glue-athena` MCP `get_table` for every `rr:tableName` in `r2rml-mappings.ttl` — every table must exist or deployment halts.
- Check IAM caller identity (must have CDK deploy permissions; verify via `iam` MCP `get_role` + policy check).
- **Look up the data lake bucket's KMS key.** If the data lake bucket (where Athena writes results) uses a customer-managed KMS key (different from the semantic-layer key the CDK creates), the Ontop task role MUST have `kms:Decrypt`, `kms:Encrypt`, `kms:GenerateDataKey`, `kms:DescribeKey` on that key. Check via `aws s3api get-bucket-encryption` and add a `PolicyStatement` to the Ontop task role in CDK with the right key ARN. Hardcoding the key ID in CDK is acceptable for `dev`; for `prod`, look it up at synth time via a CDK custom resource or pass via stack input.
- Check `bedrock-agentcore-starter-toolkit` is installed: `pip show bedrock-agentcore-starter-toolkit` should return version. If absent, run `pip install bedrock-agentcore-starter-toolkit`.

### Step 2 — Detect existing infra

- Use the `core` MCP (CloudFormation) to describe stack `AdopSemanticLayer{environment}`.
- If `StackStatus` is `CREATE_COMPLETE` / `UPDATE_COMPLETE`, jump to Step 4 (artifact-only update).
- If stack does not exist, proceed to Step 3.
- If stack is in a failed state, halt and ask the user to clean up before redeploy.

### Step 3 — Provision infrastructure (first run only)

If the CDK directory `semantic-layer/infra/` does not exist in this repo, scaffold it. The scaffold lives at `semantic-layer/infra/lib/sparql-virtualization-stack.ts` and provisions:

| Resource | Purpose | Config |
|---|---|---|
| VPC | Network isolation | 2 AZ, 2 public + 2 private subnets, NAT gateway |
| Neptune cluster | OWL ontology storage + SPARQL 1.1 endpoint | `db.r5.large` × 1 (dev) / × 2 (prod). IAM auth on. |
| Neptune Loader Lambda | Bulk-load TTL into Neptune | Python 3.12, 1024 MB |
| Ontop ECS Fargate service | VKG SPARQL → SQL via R2RML | 1 task, 1 vCPU / 4 GiB. ALB front. Reads R2RML from S3 config bucket. |
| ECR repository | Ontop container image | `adop-ontop-{environment}` |
| OpenSearch Serverless collection | Ontology-slice embeddings | `adop-semantic-slices` (vector search type) |
| OBQC Lambda | SPARQL validation against OWL | Python 3.12, 1024 MB. Uses `rdflib` + ontology bundled in. |
| Athena workgroup | SPARQL execution path | `adop-semantic-{environment}` |
| Bedrock AgentCore runtime | NL → SPARQL agent | Container-based runtime, Streamable HTTP transport |
| S3 config bucket | Stores R2RML, ontology TTL, agent code | `adop-semantic-{accountId}-{environment}` |
| KMS key | Encryption at rest for Neptune, S3, OpenSearch | Rotation enabled |

Build steps:
1. `cdk bootstrap` if not already bootstrapped.
2. `cdk deploy AdopSemanticLayer{environment} --require-approval never`.
3. Build Ontop container image via CodeBuild from `semantic-layer/ontop_config/` (Docker not required locally — repo-zip → S3 → CodeBuild pattern).
4. Wait for stack `CREATE_COMPLETE`. Capture stack outputs (Neptune endpoint, Ontop ALB, OpenSearch endpoint, etc.).

This is a 15–25 minute step. Report progress to the user.

### Step 4 — Push artifacts

> ⚠️ **TTL upload ordering matters.** Ontop ECS pulls TTL files from S3 at container startup. If you `cdk deploy` before uploading the TTLs, the first 3 ECS tasks fail with "404 ontology/ontology.ttl does not exist" before stabilizing. Two safe orderings: (a) upload TTLs **before** `cdk deploy` so the bucket already has them when the container starts, or (b) make `start.sh` retry the S3 fetch with backoff. Pick (a) for simplicity.

#### 4a. Neptune ontology load

- Upload `semantic-layer/ontology.ttl` to S3 config bucket → `ontology/ontology.ttl`.
- Invoke Neptune Loader Lambda. For ontologies under ~10K triples, the loader can do a `DELETE WHERE { ?s ?p ?o }` followed by `INSERT DATA { <nt-serialized triples> }` in a single SPARQL UPDATE. For larger ontologies, switch to the Neptune Bulk Loader (`s3://` source).
- Run a smoke SPARQL query: `SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }` and `SELECT ?c WHERE { ?c a owl:Class }` — expect the triple count and class count from the local ontology to match.

#### 4b. Ontop R2RML refresh

- Upload `semantic-layer/r2rml-mappings.ttl` to S3 config bucket → `ontology/r2rml-mappings.ttl` (must match the path the container's `start.sh` fetches from).
- Trigger ECS service rolling update (`force_new_deployment`). Health check on the Ontop SPARQL endpoint must pass before old tasks are stopped.
- Run a smoke SPARQL query through the Ontop endpoint via an in-VPC Lambda: `ASK { ?s ?p ?o }` (boolean true) followed by a query that exercises one full R2RML triplesMap end-to-end (R2RML → Athena → Iceberg). Compare the returned count against the underlying Athena row count for the table.

#### 4c. OpenSearch ontology-slice index

- Chunk `semantic-layer/ontology.ttl` into per-class slices generically (no domain knowledge baked in). Each slice MUST contain:
  - Class IRI + label + `rdfs:comment`
  - All datatype properties where the class is `rdfs:domain` (with property name + range datatype + `rdfs:comment`)
  - **Outgoing object relationships** — every object property where the class is `rdfs:domain`, with the target class label
  - **Incoming object relationships** — every object property where the class is `rdfs:range`, with the source class label
  - A trailing hint line telling the reader they can call `get_ontology_slice` again on any linked class name to retrieve its properties

  This navigation graph is **load-bearing** — without incoming/outgoing relationships in the slice, the agent cannot traverse from one class to another and will hallucinate predicates. Walk the graph generically with rdflib (`rdfs:domain`, `rdfs:range`, `owl:Class`, `owl:DatatypeProperty`, `owl:ObjectProperty`) — never hardcode class names or domain-specific terms.

- Embed each slice via Bedrock Titan v2 (1024-dim, normalized).
- Bulk-index into OpenSearch Serverless collection `adop-semantic-slices` with fields: `iri`, `label`, `text`, `embedding`. Index name `ontology-slices` with `index.knn: true`, knn_vector field, faiss/cosinesimil method.
- **AOSS has eventual consistency.** After delete + recreate of the index, wait 30–60 seconds before the first query — `_count` may briefly return 0 even when documents are indexed. Build a retry into the indexer.
- Use `requests-aws4auth` (or boto3 session-aware signers) to sign requests. Manual `botocore.auth.SigV4Auth + urllib.request` is brittle for AOSS data-plane calls.

#### 4d. OBQC Lambda refresh

- The OBQC Lambda queries Neptune at request time for `rdfs:domain` / `rdfs:range`, so **no rebuild is needed when only the ontology changes** — Neptune reload (4a) is sufficient. Skip rebuilding OBQC unless the OBQC code itself changed.
- After a Neptune reload, run an OBQC verification checklist (canonical test inputs that should always pass / always fail):
  - **Valid SPARQL using only declared predicates** → `pass: true, errors: []`
  - **SPARQL with an undeclared `adop:nonExistentProperty`** → `pass: false, rule: property_existence`
  - **SPARQL using predicate-object lists** (`subject pred1 obj1 ; pred2 obj2 ; pred3 obj3 .`) — verify the parser captures all triples after `;` continuations, not just the first
  - **SPARQL with `COUNT(?var)` aggregate** — verify `?var` is NOT flagged as an `iri_output` violation just because it appears inside an aggregate
  - **SPARQL using a polymorphic predicate** (one with multiple `rdfs:domain` declarations, e.g. `forEntity` on multiple record classes) — verify OBQC treats the domains as UNION (any domain matches), not intersection (all domains must match). Bug pattern: returning only the first domain from `_query_domain` causes false-positive type conflicts.
  - **SPARQL using a polymorphic-domain predicate alongside `?x a SomeClass`** — verify no false-positive `type_conflict` because `_build_type_bindings` treats union-domain constraints as ANY-of, not ALL-of.

  These five canonical tests catch the regressions we've actually hit. Add them to `semantic-layer/tests/test_obqc_canonical.py`.

### Step 5 — Provision / refresh the SPARQL agent

**Tooling:** `bedrock-agentcore-starter-toolkit` (provides the `agentcore` CLI, install via `pip install bedrock-agentcore-starter-toolkit`) handles container build + AgentCore runtime creation. Use boto3 `bedrock-agentcore-control` for runtime updates (env vars, image tag) — older `aws-cli` versions (≤ 2.15) lack `bedrock-agentcore-control` subcommands; boto3 has it regardless.

If the Bedrock AgentCore runtime `adop-semantic-agent-{environment}` does not exist:

1. Scaffold `semantic-layer/agent/sparql_agent/`:
   - `sparql_agent.py` — entry point using `bedrock_agentcore.runtime.BedrockAgentCoreApp`. Implements an iterative tool-calling loop via Bedrock Converse (see "Agent SPARQL generation pattern" below).
   - `requirements.txt` — `bedrock-agentcore`, `boto3`, `requests`, `requests-aws4auth`.
   - Dockerfile is auto-generated by `agentcore configure`.

2. Run `agentcore configure -e sparql_agent.py -n adop_sparql_agent -r {region} -p HTTP -dt container -rf requirements.txt -ni` to generate the Dockerfile and `.bedrock_agentcore.yaml`. **On Windows, set `PYTHONIOENCODING=utf-8 PYTHONUTF8=1`** — the toolkit's Rich console output uses Unicode characters that crash on cp1252.

3. Run `agentcore launch --auto-update-on-conflict`. This: zips source → S3 → triggers CodeBuild project `bedrock-agentcore-{name}-builder` → builds container → pushes to ECR → calls `bedrock-agentcore-control.create_agent_runtime`. Auto-creates IAM execution role + CodeBuild role.

4. **Inject runtime env vars** via `bedrock-agentcore-control.update_agent_runtime` after the initial launch (the toolkit doesn't support env vars on `agentcore configure`):
   - `OPENSEARCH_ENDPOINT` — from OpenSearch stack output
   - `OBQC_FUNCTION_NAME` — Lambda function name for OBQC
   - `EXEC_SPARQL_FUNCTION_NAME` — name of the in-VPC Lambda that proxies SPARQL to Ontop ALB (the Ontop ALB is internal-only; AgentCore runs in PUBLIC network mode so it cannot reach the ALB directly).
   - `LLM_MODEL` — e.g. `us.anthropic.claude-sonnet-4-5-20250929-v1:0`

5. **Grant the agent execution role** via inline IAM policy: `lambda:InvokeFunction` on OBQC + Ontop-proxy Lambdas, `bedrock:InvokeModel*` for embedding + LLM, `aoss:APIAccessAll` on the OpenSearch collection ARN, `ssm:GetParameter*` for `/adop-semantic/*`. The role is named `AmazonBedrockAgentCoreSDKRuntime-{region}-{hash}` (auto-created by the toolkit).

6. **Add the agent role to the OpenSearch data-access policy.** AOSS policies require principal patterns to use the **STS assumed-role** ARN format, not the plain IAM role ARN. The agent runtime's signing principal at request time is `arn:aws:sts::ACCOUNT:assumed-role/AmazonBedrockAgentCoreSDKRuntime-{region}-{hash}/BedrockAgentCore-*` — include this `assumed-role/.../*` pattern in the `Principal` array of the data-access policy. Plain IAM-role ARN alone does NOT match.

7. Capture `agent_arn` for the manifest.

If it exists: run `agentcore launch --auto-update-on-conflict` again — the toolkit detects the existing runtime, rebuilds the image, and updates it. AgentCore runtime versions are immutable; updating bumps the version number. Existing sessions continue on the old version until they expire.

#### Agent SPARQL generation pattern

The agent must use an **iterative slice-tool loop** in `generate_sparql`, not a single LLM call. Linear pipelines fail when the question requires traversing multiple linked classes (e.g. "Apple total assets in 2024" needs Entity → BalanceSheetRecord → FiscalPeriod). Implementation:

- The agent calls `bedrock-runtime.converse` with a tool spec for `get_ontology_slice`.
- System prompt is **fully generic** — describes the workflow (call slice tool to retrieve classes, navigate the graph, write SPARQL using only verbatim IRIs from slices) but does NOT name any classes, predicates, or entity-id formats. The model learns the schema from the slices it retrieves, not from the prompt.
- The model can call `get_ontology_slice` up to 4 times per question. First call: user's question. Follow-up calls: specific class names from the navigation graph the model just saw.
- When the model stops calling tools, the assistant message is the SPARQL response. Apply a robust strip step: extract the SPARQL block (prefer fenced code blocks, fall back to keyword-anchored extraction at start-of-line for `PREFIX`/`BASE`/`SELECT`/`ASK`/`CONSTRUCT`/`DESCRIBE`), and **auto-inject the namespace `PREFIX` declaration if missing** (the model often omits it).

#### Other pitfalls to handle in the agent

- **Reverse predicates with no R2RML** return empty. Either declare them in R2RML or remove from ontology — see Phase 6 spec.
- **Polymorphic predicates** (multiple `rdfs:domain` values) require OBQC's `_query_all_domains` + union-aware type-conflict logic. Without this, OBQC false-positives on every record-class query.
- **AgentCore env-var update doesn't take effect on cached sessions.** Old container instances keep running with the old env. To force a fresh container with new env, pass a fresh long session ID (≥ 33 chars) on the next `agentcore invoke`.

### Step 6 — End-to-end smoke tests

Run 3 canned NL questions through the deployed agent (the questions live in `semantic-layer/tests/smoke_questions.yaml`). For each:

1. Send NL question to AgentCore runtime via SSE stream.
2. Verify the agent: extracted terms, fetched ontology slice, generated SPARQL, validated SPARQL via OBQC, executed against Ontop, returned non-empty result.
3. Assert end-to-end latency ≤ 30s.

If any smoke test fails, do not mark deployment complete. Report failure with the failing tool's output and ask the user how to proceed (rollback / debug / accept).

### Step 7 — Emit deployment manifest

Write `semantic-layer/deployment_manifest.json`:

```json
{
  "stack_name": "AdopSemanticLayerDev",
  "environment": "dev",
  "deployed_at": "2026-05-24T12:00:00Z",
  "ontology_version": "v3",
  "endpoints": {
    "neptune": "...",
    "ontop": "...",
    "opensearch": "...",
    "obqc_lambda_arn": "...",
    "agent_arn": "..."
  },
  "smoke_tests": [
    { "question": "...", "passed": true, "latency_ms": 12500 }
  ]
}
```

Commit the manifest to the repo (it is a deployment record, not a secret).

## Outputs

| File / Resource | Action |
|---|---|
| `infra/semantic-layer/` (CDK) | Created on first run, reused thereafter |
| `agent/sparql_agent/` | Created on first run, reused thereafter |
| `semantic-layer/deployment_manifest.json` | Created or replaced |
| AWS stack `AdopSemanticLayer{environment}` | Created or updated |
| Neptune ontology graph | Replaced with new TTL |
| Ontop service | New R2RML pushed + rolling restart |
| OpenSearch index `adop-semantic-slices` | Re-indexed atomically |
| Bedrock AgentCore runtime | Created or updated |

## Tests Required

- `semantic-layer/tests/smoke_questions.yaml` — 3+ canned NL questions with expected SPARQL term/result fingerprints.
- `semantic-layer/tests/test_deployment_smoke.py` — runs the smoke set, asserts non-empty results.
- `semantic-layer/tests/test_obqc_validates_examples.py` — asserts OBQC accepts known-good and rejects known-bad SPARQL.
- `semantic-layer/tests/test_ontology_slice_retrieval.py` — asserts OpenSearch returns the expected class for canonical NL queries.

## Subsequent-workload deploy (artifact-only path)

When the stack already exists (detected in Step 2), the deploy is much shorter and CHEAP — no new infra:

1. Upload new `ontology.ttl` + `r2rml-mappings.ttl` to S3 config bucket (`adop-semantic-{accountId}-{region}/ontology/`).
2. Reload Neptune: full DELETE+INSERT for ontologies under ~10K triples (idempotent, ~5s). For larger ontologies use the bulk loader.
3. Trigger Ontop ECS rolling restart (`force_new_deployment`) — container picks up new R2RML on startup.
4. Re-run the OpenSearch indexer. Delete-and-recreate index, wait for AOSS consistency, bulk-index.
5. **Skip OBQC redeploy** — it queries Neptune at request time, no rebuild needed.
6. Run the OBQC canonical test checklist (Step 4d) to verify regressions weren't introduced by ontology changes.
7. **Skip AgentCore redeploy** unless the agent code itself changed. New ontology classes are picked up automatically via the slice retrieval path.
8. Run smoke tests (Step 6) against the deployed agent to verify end-to-end.
9. Update `deployment_manifest.json` with new ontology version + verified-questions list.

Total wall time: ~5–10 minutes. No incremental monthly spend.

## NEVER Do

- ❌ Deploy without Phase 6 artifacts in place and tests passing.
- ❌ Hardcode account IDs / VPC IDs / bucket names. Use stack outputs.
- ❌ Drop Neptune to update the ontology — push via the loader.
- ❌ Skip smoke tests because deployment "looked successful." A green CloudFormation stack is not the same as a working agent.
- ❌ Auto-rollback on smoke-test failure. Halt, report, ask the user.
- ❌ Provision in `prod` environment without explicit user confirmation including the cost impact (Neptune cluster is the largest line item).
- ❌ Deploy a new ontology with `owl:ObjectProperty` declarations that have no corresponding R2RML triplesMap producing them. Add a deploy-time validator that walks the ontology and checks every object property is materialized somewhere in the R2RML. If a predicate is declared-but-not-mapped, queries traversing it return empty — silent failure.
- ❌ Embed domain knowledge into agent prompts or the slice indexer. Both must be fully generic (walk the rdflib graph, name no specific classes/predicates/entity-id formats). The schema IS the source of truth — the agent learns it at query time from the slices.

## Architecture

End-to-end pattern: **OWL ontology in Neptune** (T-Box for OBQC validation) + **R2RML mappings driving Ontop** (VKG that translates SPARQL → SQL against Athena) + **OpenSearch Serverless** (vector index of ontology slices for NL→class retrieval) + **OBQC Lambda** (deterministic SPARQL validation against OWL domain/range) + **Bedrock AgentCore runtime** hosting a 5-tool SPARQL/NL agent (extract_terms, get_ontology_slice, validate_sparql, execute_sparql, repair_sparql).

The deploy artifacts in this repo (`semantic-layer/lambdas/`, `semantic-layer/agent/sparql_agent/`, `semantic-layer/ontop_config/`, `semantic-layer/infra/`) are the canonical implementation — modify them in place rather than maintaining external references.

**Repo layout for ported semantic-layer artifacts**: keep everything under `semantic-layer/` — do NOT scatter into top-level `lambdas/`, `agent/`, `config/`. The Phase 7 directory tree is:

```
semantic-layer/
├── ontology.ttl                       # Phase 6 output
├── r2rml-mappings.ttl                 # Phase 6 output
├── manifest.json                      # Phase 6 output
├── deployment_manifest.json           # Phase 7 output (post-deploy)
├── lambdas/
│   ├── obqc/                          # SPARQL OWL-validation Lambda
│   ├── neptune_loader/                # ontology load + SPARQL proxy
│   └── ontop_proxy/                   # SPARQL forwarder for outside-VPC clients
├── ontop_config/                      # Dockerfile + start.sh + ontop.properties
├── agent/sparql_agent/                # 5-tool agent (extract_terms, get_ontology_slice, ...)
├── infra/                             # CDK app for the semantic layer (separate from any other infra)
│   ├── bin/app.ts
│   └── lib/
│       ├── storage-stack.ts
│       ├── opensearch-stack.ts
│       ├── sparql-virtualization-stack.ts
│       └── agent-stack.ts
├── tests/                             # parse + ref-integrity + table-existence + smoke
├── scripts/                           # index-ontology-slices.py, deploy helpers
└── PHASE7_DEPLOY_NOTES.md             # session-progress notes if multi-session
```

This keeps semantic-layer concerns isolated from workload ETL code and prevents confusion with any non-semantic-layer Lambda or agent code that may live in the repo.

### Architectural choices to call out

These choices are deliberate and may differ from common Ontop tutorials or earlier prototypes — call them out when explaining the deploy:

| Aspect | Reference | This skill |
|---|---|---|
| Ontology slice retrieval | Neptune SPARQL direct | OpenSearch Serverless + Titan v2 embeddings (more accurate NL→class matching, costs ~$175/mo more) |
| Glue database layout | Single `fip_gold` | Per-workload `*_db` databases (`entity_resolved_db`, `estimates_db`, ...). Ontop IAM uses wildcard on `*_db` pattern. |
| Region | `us-east-1` | `us-west-2` (configurable; whatever account already has data) |
| Namespace | `fip:` (`http://fip.example.org/`) | `adop:` (`http://adop.example.org/`) |
| SSM parameter prefix | `/fip-poc/` | `/adop-semantic/` |
| Ontology + R2RML in Ontop image | Baked at build time | Pulled from S3 at startup (so artifact updates → service restart, not image rebuild) |
| Zone targeted by R2RML | Gold | Silver (most workloads have no Gold; Phase 6 picks per workload) |
| Repo layout | Spread across `lambdas/`, `agent/`, `config/`, `infra/` | Everything consolidated under `semantic-layer/` |

### Build workflow (proven approach)

For the first workload onboarding (when nothing exists in the target account), follow this order — it minimizes wasted code and surfaces issues early:

1. **Verify Phase 6 artifacts** (`semantic-layer/ontology.ttl`, `semantic-layer/r2rml-mappings.ttl`, `manifest.json`) exist and pass `pytest semantic-layer/tests/`.
2. **Detect existing infra** via `core` MCP / CloudFormation describe of stack `AdopSemanticLayer{environment}`. If present, jump to Step 7 (artifact-only update). If absent, continue.
3. **Confirm budget commitment** with the user (~$590/mo dev) BEFORE writing any CDK code.
4. **Write `semantic-layer/agent/sparql_agent/tools/get_ontology_slice.py`** for OpenSearch retrieval (this skill's design — see Forks table below).
5. **Write `semantic-layer/scripts/index-ontology-slices.py`** — chunks the ontology by class, embeds via Titan v2, bulk-indexes with atomic alias swap.
6. **Scaffold `semantic-layer/infra/`** as a CDK TypeScript project. Split into multiple stacks for parallel deploy: `StorageStack` (S3+KMS), `OpenSearchStack` (collection + policies), `SparqlVirtualizationStack` (VPC + Neptune + Ontop + Lambdas), `AgentStack` (AgentCore runtime). The first three can deploy in parallel; AgentStack depends on them.
7. **`cdk synth` + show user** the full template before any `cdk deploy`. Validate cost-impacting choices (instance class, NAT gateway, OCU minimums).
8. **Deploy in dependency order**, capture stack outputs.
9. **Push artifacts** (ontology → Neptune Loader, R2RML → Ontop S3 + ECS rolling restart, slices → OpenSearch alias swap) only after stacks are `CREATE_COMPLETE`.
10. **Smoke-test before declaring success.** Three canned NL questions, end-to-end. Stop and report on any failure.

### Pitfalls and version requirements

- **`aws-cli` >= 2.20** for `bedrock-agentcore-control` subcommands. Older CLIs (e.g. 2.15) silently lack the command and the error is misleading.
- **CodeBuild for Docker builds.** No local Docker required (and `docker` is often not installed in the user's shell). Reference's `scripts/deploy-sparql-stack.py` shows the zip → S3 → CodeBuild pattern.
- **Neptune deletion protection is OFF by default in CDK.** Skill 07 keeps it off for `dev` (so teardown works). For `prod`, flip on.
- **OpenSearch Serverless OCU minimums are non-trivial.** 2 OCUs minimum (1 indexing + 1 search) at ~$87.60/OCU/month = ~$175/month. Cannot be scaled below 2.
- **Silver-only deployments are common.** When Gold has not been built for a workload, R2RML targets Silver. The semantic layer queries Silver and/or Gold — never Bronze (Bronze is raw immutable source data, outside the queryable surface).
- **Multi-session work is normal for the first workload.** Don't pretend it can be one-shot. Use a `PHASE7_DEPLOY_NOTES.md` file to track progress across sessions and avoid committing half-baked code.

## Cost Note

A semantic-layer stack in `dev` runs ~$400–600/month (Neptune `db.r5.large` is the dominant cost). Surface this to the user before first provisioning. For development, recommend the pattern of running locally where possible and only provisioning the full stack for integration tests / demos.
