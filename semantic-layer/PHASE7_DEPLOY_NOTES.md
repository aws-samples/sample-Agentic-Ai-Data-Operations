# Phase 7 Deploy — Session Notes

> **Status: DEPLOYED + VERIFIED end-to-end.** Stack is live in us-west-2 (account redacted). entity_resolved + fundamentals (4 sub-workloads) onboarded and queryable through the deployed AgentCore agent. See `deployment_manifest.json` for endpoints + smoke test results.
>
> This file documents the full session — open decisions made, lessons learned, and bug fixes applied. Useful as a record of *how the stack got built*, not as a runbook (skills 06 + 07 are the runbooks).

## What's verified working

- `semantic-layer/ontology.ttl` (parses, ref-integrity OK)
- `semantic-layer/r2rml-mappings.ttl` (parses, all referenced Glue tables exist in `us-west-2`)
- `semantic-layer/manifest.json`
- `semantic-layer/tests/` (5/5 passing including live AWS check)
- 6 workloads deployed in AWS account `<ACCOUNT_ID>` region `us-west-2`:
  - `entity_resolved_db.silver_entity_resolved` (55 rows)
  - `estimates_db.silver_{estimates_eps,estimates_ratings,estimates_sales_ntm}`
  - `fundamentals_db.silver_{balance_sheet,cash_flow,ratios,sales}`
  - `pricing_db.silver_pricing`
  - `reference_db.silver_reference`
  - `supplier_chain_data_db.silver_supplier_chain_data`
- **Silver-only across all workloads — no Gold tables exist yet**

## What's staged on disk (NOT verified, NOT committed)

Files are present in the repo with `adop:` namespace and `/adop-semantic/` SSM prefix conventions, but unverified — no CDK yet to wire them, no infra to point at.

| Path | Lines | Role |
|---|---:|---|
| `semantic-layer/lambdas/obqc/handler.py` | 548 | OBQC: deterministic SPARQL validation against OWL T-Box in Neptune |
| `semantic-layer/lambdas/neptune_loader/handler.py` | 88 | Loads ontology TTL into Neptune via the bulk loader endpoint |
| `semantic-layer/lambdas/ontop_proxy/handler.py` | 61 | SPARQL forwarder for clients outside the VPC |
| `semantic-layer/ontop_config/Dockerfile` | — | Ontop image base + Simba Athena JDBC driver |
| `semantic-layer/ontop_config/start.sh` | — | Startup: pulls TTL files from S3, launches Ontop |
| `semantic-layer/ontop_config/ontop.properties` | — | Ontop runtime config |
| `semantic-layer/ontop_config/db-metadata.json` | — | Database metadata for Athena JDBC |
| `semantic-layer/agent/sparql_agent/sparql_agent.py` | 802 | 5-tool SPARQL/NL agent (extract_terms, get_ontology_slice, validate_sparql, execute_sparql, repair_sparql) |
| `semantic-layer/agent/sparql_agent/tools/ontology_slice.py` | 237 | Slice retrieval (currently SPARQL-based, will be rewritten for OpenSearch) |

**OPEN DECISIONS BEFORE NEXT SESSION:**
- Decide whether to keep `lambdas/ontop_proxy/` — only needed if anything outside the VPC issues SPARQL directly. If the AgentCore agent runs inside the VPC, proxy is dead code; remove.
- Decide whether OBQC fetches ontology at request time (Neptune query, ontology updates immediately) or at startup (Lambda zip rebuild on each ontology update).

## Architectural decisions made

### 1. OpenSearch Serverless for ontology slices

`tools/ontology_slice.py` currently retrieves slices via Neptune SPARQL — needs rewrite to query OpenSearch Serverless instead. OpenSearch gives more accurate NL→class matching via Titan v2 embeddings vs SPARQL text match, at ~$175/mo extra cost (2 OCU minimum).

Implications:
- New `semantic-layer/scripts/index-ontology-slices.py` — chunks ontology by class, embeds, bulk-indexes with alias swap
- CDK additions: `aws-opensearchserverless` collection + encryption policy + network policy + data-access policy

### 2. Per-workload Glue databases

Codebase layout: `entity_resolved_db`, `estimates_db`, `fundamentals_db`, `pricing_db`, `reference_db`, `supplier_chain_data_db`. Semantic-layer R2RML targets `silver_*` tables (and `gold_*` once Gold is built); the semantic layer never queries Bronze.

**Ontop task IAM scope**: wildcard on `arn:aws:glue:us-west-2:ACCOUNT:database/*_db` and `arn:aws:glue:us-west-2:ACCOUNT:table/*_db/*`.

R2RML logical tables target Silver (e.g. `entity_resolved_db.silver_entity_resolved`) — not Gold (no Gold tables exist).

### 3. Ontop image — TTL files pulled from S3 at startup

`start.sh` should pull `ontology.ttl` + `r2rml-mappings.ttl` from the S3 config bucket on container start. This way artifact updates → ECS rolling restart, not full image rebuild.

Build via CodeBuild (no local Docker): zip repo → S3 → CodeBuild project builds image and pushes to ECR.

### 4. OBQC ontology source

Reference pattern queries Neptune at request time (`SELECT ?p ?dom ?rng WHERE { ?p rdfs:domain ?dom ; rdfs:range ?rng }`). Better than bundling ontology in Lambda zip — ontology updates take effect immediately.

## What still needs to be written

1. **`semantic-layer/infra/`** — fresh CDK TypeScript project
   - `package.json`, `tsconfig.json`, `cdk.json`
   - `bin/app.ts` — entry point
   - `lib/storage-stack.ts` — S3 config bucket, KMS key
   - `lib/sparql-virtualization-stack.ts` — VPC, Neptune, Ontop ECS, ALB, OBQC Lambda, Neptune Loader Lambda, Athena workgroup, security groups, SSM params
   - `lib/opensearch-stack.ts` — Serverless collection + policies + IAM
   - `lib/agent-stack.ts` — Bedrock AgentCore runtime + ECR repo + IAM (or skip; deploy agent via CLI later)

   Estimated ~700-900 lines TS.

2. **`semantic-layer/scripts/deploy-semantic-layer.py`** — CodeBuild orchestration (no local Docker)
3. **`semantic-layer/scripts/index-ontology-slices.py`** — OpenSearch indexer
4. **`semantic-layer/scripts/load-ontology-neptune.py`** — invoke Neptune Loader Lambda
5. **`semantic-layer/scripts/deploy-sparql-agent.py`** — AgentCore runtime provisioning
6. **`semantic-layer/agent/sparql_agent/tools/get_ontology_slice.py`** — REWRITE for OpenSearch (replaces current SPARQL-based version)

## Cost estimate (us-west-2 dev)

| Resource | $/month |
|---|---|
| Neptune `db.r6g.large` × 1 | ~$315 |
| Ontop ECS Fargate (1 vCPU, 2 GiB, always-on) | ~$36 |
| ALB | ~$22 |
| NAT Gateway | ~$33 |
| OpenSearch Serverless 2 OCU minimum (1 indexing + 1 search) | ~$175 |
| Lambda + CloudWatch + S3 + KMS | ~$5-10 |
| Bedrock AgentCore runtime (when running) | per-invocation |
| **Total baseline** | **~$590/mo** |

## Resume checklist for next session

1. Confirm budget commitment (~$590/mo until torn down)
2. Decide: AgentCore runtime in stack or via separate CLI deploy?
3. Decide: keep OpenSearch slice retrieval (~$175/mo extra, more accurate NL→class) or fall back to Neptune-SPARQL slices (cheaper, simpler)?
4. Begin with `semantic-layer/infra/` scaffold
5. `cdk bootstrap` against `us-west-2` if not done
6. `cdk synth` validation before any `cdk deploy`
7. After `cdk deploy`: load ontology, push R2RML, index slices, deploy agent, smoke-test

## Lessons learned (already patched into skill 07)

- **First-workload onboarding is multi-session.** Skill 07 now flags this explicitly at the top.
- **Subsequent workloads** are a much lighter artifact-push (skill 07 documents the difference).
- **`aws-cli` >= 2.20** required for `bedrock-agentcore-control` subcommands.
- **CodeBuild is required** for Docker builds (no local Docker assumed).
- **Silver-only across all 6 onboarded workloads** today; semantic layer maps Silver. Once Gold is built for any workload, Phase 6 will offer Gold as an additional zone option.
- **Repo self-containment**: do not reference external paths in checked-in skill specs.
