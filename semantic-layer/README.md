# Semantic Layer

OWL ontology + R2RML virtualization over the Bronze→Silver→Gold workloads
in this repo. Question-in-natural-language → SPARQL → SQL → Iceberg, with
deterministic ontology validation between question and execution.

---

## What this gives you

- **Cross-workload joins** without writing SQL. Once two workloads are
  onboarded, the agent can answer questions that traverse them
  (`Apple's 2024 free cash flow joined to its sector classification`)
  by following the ontology.
- **Schema as source of truth**. The OWL ontology + R2RML mappings are
  the only place class names, properties, and join keys are declared.
  The agent learns the schema at query time from the ontology slices it
  retrieves — no hardcoded names anywhere in the agent prompt or
  indexer.
- **Deterministic query validation**. Every generated SPARQL passes
  through OBQC against the OWL T-Box in Neptune before it touches Athena.
  Hallucinated predicates fail fast with a structured error the agent
  uses to repair the query.

---

## Architecture

```
                       natural-language question
                                  │
                                  ▼
                        ┌─────────────────────┐
                        │  Bedrock AgentCore  │
                        │  adop_sparql_agent  │
                        │  (5 tools, repair   │
                        │   loops to validate)│
                        └──┬───┬───────┬───┬──┘
                           │   │       │   │
       ┌───────────────────┘   │       │   └─────────────────────┐
       │                       │       │   ▲ (repair_sparql      │
       │                       │       │    │  loops back here   │
       │                       │       │    │  on validation     │
       │                       │       │    │  failure, ≤ 3 tries)│
       ▼                       ▼       ▼    │                    ▼
  ┌─────────┐         ┌──────────────┐ ┌────┴─────────┐    ┌─────────────┐
  │ extract │         │ get_ontology │ │   validate   │    │   execute   │
  │  terms  │         │    _slice    │ │    _sparql   │    │   _sparql   │
  └─────────┘         └──────┬───────┘ └──────┬───────┘    └──────┬──────┘
                             │                │                   │
                             ▼                ▼                   │
                  ┌──────────────────┐ ┌──────────────────┐       │
                  │   OpenSearch     │ │   OBQC Lambda    │       │
                  │   Serverless     │ │  (queries Neptune│       │
                  │  ontology slices │ │   T-Box at       │       │
                  │  (Titan v2 1024d)│ │   request time)  │       │
                  └──────────────────┘ └────────┬─────────┘       │
                                                │                 │
                                                ▼                 │
                                    ┌──────────────────────┐      │
                                    │   Neptune cluster    │      │
                                    │   OWL ontology       │      │
                                    │   (T-Box only,       │      │
                                    │   in memory)         │      │
                                    └──────────────────────┘      │
                                                                  │
                                       (in-VPC Lambda proxy → ALB)│
                                                                  ▼
                                                    ┌──────────────────────┐
                                                    │   Ontop ECS Fargate  │   <─ R2RML mappings
                                                    │   (VKG: SPARQL→SQL)  │      pulled from S3
                                                    └──────────┬───────────┘      at startup
                                                               │ JDBC
                                                               ▼
                                                    ┌──────────────────────┐
                                                    │   Amazon Athena      │
                                                    │   (per-workload      │
                                                    │    Glue databases)   │
                                                    └──────────┬───────────┘
                                                               │
                                                               ▼
                                                    ┌──────────────────────┐
                                                    │   S3 Iceberg tables  │
                                                    │   {workload}_db      │
                                                    │   .silver_*          │
                                                    │   .gold_* (when      │
                                                    │            built)    │
                                                    └──────────────────────┘
```

**Key choices** ([details](../prompts/data-onboarding-agent/07-deploy-semantic-layer.md#architectural-choices-to-call-out)):

- Neptune holds the **OWL T-Box only** (~hundreds of triples) for OBQC
  validation. No instance data — that lives in Iceberg.
- Ontop translates SPARQL → SQL via R2RML; instance data is virtual
  (queries materialize on demand).
- OpenSearch Serverless holds **vector embeddings of ontology slices**
  (one per OWL class, includes the navigation graph: outgoing + incoming
  object relationships). The agent retrieves slices by similarity to
  the user's question, then walks the navigation graph by calling
  `get_ontology_slice` again on linked class names.
- The agent runs in **AgentCore PUBLIC network mode** (outside the VPC).
  It reaches Ontop through an in-VPC Lambda proxy (`adop-semantic-smoke`).
  OpenSearch + OBQC + Neptune Loader are called directly via signed
  AWS API calls.

---

## Repo layout

```
semantic-layer/
├── ontology.ttl                  # consolidated OWL VKG (T-Box)
├── r2rml-mappings.ttl            # consolidated R2RML mappings
├── manifest.json                 # workloads onboarded + relationship evidence
├── deployment_manifest.json      # live AWS endpoints (account redacted)
├── PHASE7_DEPLOY_NOTES.md        # session journal of decisions + bugs fixed
│
├── infra/                        # CDK app — 3 stacks
│   ├── bin/app.ts
│   └── lib/
│       ├── storage-stack.ts            # S3 config bucket + KMS + ECR + CodeBuild
│       ├── opensearch-stack.ts         # AOSS collection + policies
│       └── sparql-virtualization-stack.ts  # VPC + Neptune + Ontop ECS + Lambdas
│
├── agent/adop_sparql_agent/      # Bedrock AgentCore SPARQL agent
│   ├── sparql_agent.py
│   └── requirements.txt
│
├── lambdas/
│   ├── obqc/                     # SPARQL validation against OWL T-Box
│   └── neptune_loader/           # ontology load + SPARQL proxy (in-VPC)
│
├── ontop_config/                 # Ontop container (Dockerfile, start.sh)
│
├── scripts/
│   ├── deploy_semantic_layer.py        # full Phase 7 deploy via CodeBuild
│   ├── load_ontology_neptune.py        # reload Neptune (DELETE+INSERT)
│   ├── index_ontology_slices.py        # rebuild OpenSearch slice index
│   ├── ask_agent.py                    # interactive query helper (Python)
│   ├── ask-agent.ps1                   # thin PowerShell wrapper
│   └── ask-agent.sh                    # thin bash wrapper
│
└── tests/                        # generic tests; run after every onboarding
    ├── test_consolidated_turtle.py
    ├── test_ontology_referential_integrity.py
    ├── test_r2rml_table_existence.py
    └── test_relationship_evidence.py
```

---

## Onboarding workflow

The semantic layer is built **incrementally, one workload at a time**.
Two skills cover it end to end — both are workload-agnostic and live in
`prompts/data-onboarding-agent/`.

### Phase 6 — onboard a workload to the ontology

[`06-onboard-semantic-layer.md`](../prompts/data-onboarding-agent/06-onboard-semantic-layer.md)

For a workload whose Silver (and/or Gold) tables already exist in Glue:

1. Detect zones (Silver/Gold/both) deployed for the workload
2. Detect multi-table workloads (e.g. `fundamentals` → 4 sub-tables) and
   ask whether to model as one class or per-table record classes
3. Profile the chosen zone(s) via Athena, propose column descriptions,
   write back to `workloads/{name}/config/semantic.yaml`
4. Read pre-declared `relationship:` blocks from `semantic.yaml` (high-
   confidence FK candidates)
5. For columns without pre-declared relationships, run embedding-based
   discovery against the existing ontology corpus
6. Verify every candidate (pre-declared + embedded) via Athena join
   sample (≥5% match rate)
7. Confirm relationships with the user
8. Append new classes/properties/relationships to
   `semantic-layer/ontology.ttl` + `semantic-layer/r2rml-mappings.ttl`
9. Run `pytest semantic-layer/tests/` — all 4 must pass before continuing

This skill produces **artifacts only** — no AWS deployment.

### Phase 7 — deploy / refresh the serving stack

[`07-deploy-semantic-layer.md`](../prompts/data-onboarding-agent/07-deploy-semantic-layer.md)

Detects whether the stack already exists in the target account:

- **First-time deploy** (~30–45 min, ~$590/mo running cost in dev):
  CDK provisions VPC + Neptune + Ontop ECS + OpenSearch + Lambdas;
  CodeBuild builds Ontop image; agent code is built and registered
  with AgentCore.
- **Subsequent deploys** (~5–10 min, no new spend): upload TTLs to S3,
  reload Neptune, force Ontop rolling restart, rebuild OpenSearch
  index, run smoke tests.

The skill enforces preflight checks (data-lake KMS access, Phase 6
artifacts present, Glue tables exist) and ends with end-to-end smoke
tests against the deployed agent.

---

## Test commands

### Static tests (run after every Phase 6 onboarding)

From the repo root:

```bash
# Set AWS credentials first (the table-existence test makes a live Glue call)
export AWS_REGION=us-west-2

pytest semantic-layer/tests/ -v
```

What each test covers:

| Test | What it checks |
|---|---|
| `test_consolidated_turtle.py` | `ontology.ttl` and `r2rml-mappings.ttl` parse cleanly with rdflib |
| `test_ontology_referential_integrity.py` | every `rdfs:domain` / `rdfs:range` references a class declared in the ontology |
| `test_r2rml_table_existence.py` | every `rr:tableName` resolves to a real Glue table (skipped without AWS creds) |
| `test_relationship_evidence.py` | every cross-workload relationship in `manifest.json` has `match_rate ≥ 0.05` |

### Live agent query (after Phase 7 deploy)

The interactive helper streams each step (extract_terms → ontology_slice
→ generate_sparql → validate_sparql → execute_sparql) as the agent
emits it.

**macOS / Linux:**

```bash
./semantic-layer/scripts/ask-agent.sh
# or pass the question directly
./semantic-layer/scripts/ask-agent.sh "What was Apple's free cash flow in 2024?"
```

**Windows PowerShell:**

```powershell
.\semantic-layer\scripts\ask-agent.ps1
```

**Anywhere with Python:**

```bash
python semantic-layer/scripts/ask_agent.py "Top 5 Technology entities by 2024 total assets in USD?"
```

### Agent ARN resolution

The helper finds the deployed agent in this order:

1. `--agent-arn` / `-a` CLI flag
2. `ADOP_AGENT_ARN` environment variable
3. `semantic-layer/deployment_manifest.json` →
   `endpoints.agent_runtime_arn` (rejected if it still contains the
   `<ACCOUNT_ID>` placeholder — set the env var, or run a fresh deploy
   so the manifest gets your account)

```bash
export ADOP_AGENT_ARN="arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/adop_sparql_agent-XXXXXXX"
python semantic-layer/scripts/ask_agent.py "..."
```

### Direct SPARQL (bypasses the agent)

For validating Ontop without going through the agent's NL→SPARQL step:

```bash
aws lambda invoke --function-name adop-semantic-smoke \
  --cli-binary-format raw-in-base64-out \
  --payload '{"sparql":"PREFIX adop: <http://adop.example.org/ontology#> SELECT (COUNT(*) AS ?n) WHERE { ?s a adop:Entity }"}' \
  /tmp/r.json && cat /tmp/r.json | python -m json.tool
```

---

## Sample questions that span both currently-onboarded workloads

`entity_resolved` (Entity / Sector / Industry / Exchange / Country) plus
`fundamentals` (BalanceSheetRecord / CashFlowRecord / RatioRecord /
SalesRecord / FiscalPeriod). Run any of these via `ask_agent.py`:

```
What were Apple's total assets in fiscal year 2024 in USD?
List 5 entities listed on NASDAQ with their tickers.
Which Technology sector entities had ROE above 30 percent in 2024?
What was Microsoft's revenue in fiscal year 2023 in USD?
Top 5 Technology entities by 2024 total assets in USD.
What was Q3 2023 sales for Apple in USD?
Free cash flow in 2024 for entities in the Software industry, sorted high to low.
For Apple in fiscal year 2024, show total assets, free cash flow, and full-year revenue, all in USD.
```

These exercise different relationship patterns — sector filters, exchange
joins, quarterly vs annual grain, multi-record-class joins on the same
entity+period, and ratio aggregates.

---

## Cost note

A semantic-layer stack in `dev` runs ~$590/month — Neptune `db.r6g.large`
is the dominant line item (~$315), then OpenSearch Serverless 2-OCU
minimum (~$175), NAT (~$33), ALB (~$22), Ontop ECS Fargate (~$36),
plus per-invocation AgentCore. Tear down with:

```bash
cd semantic-layer/infra
cdk destroy AdopSemanticLayerSparql AdopSemanticLayerOpenSearch AdopSemanticLayerStorage
```

---

## Related docs

- **[Skill 06](../prompts/data-onboarding-agent/06-onboard-semantic-layer.md)**
  — onboard a workload to the consolidated ontology
- **[Skill 07](../prompts/data-onboarding-agent/07-deploy-semantic-layer.md)**
  — deploy/refresh the AWS serving stack + agent
- **[PHASE7_DEPLOY_NOTES.md](PHASE7_DEPLOY_NOTES.md)** — session journal
  of decisions made + bugs fixed during the initial deployment (load-
  bearing for understanding the current state, not a runbook)
