# Prompt Architecture: How the Data Onboarding Prompts Work

> For technical audiences. Explains prompt naming, hierarchy, decision logic, and how prompts map to the multi-agent system.

---

## Prompt Taxonomy

Each prompt is named with a **phase prefix** that indicates when it runs in the onboarding lifecycle:

| Prompt ID | Phase | Name | Purpose |
|-----------|-------|------|---------|
| `ROUTE` | Pre-flight | **Route: Check Existing Source** | Prevent duplicate onboarding |
| `GENERATE` | Pre-flight | **Generate: Create Synthetic Data** | Produce test/demo fixtures |
| `ONBOARD` | Core | **Onboard: Build Data Pipeline** | Master orchestrator (Bronze -> Silver -> Gold) |
| `ENRICH` | Post-build | **Enrich: Link Datasets via FK** | Add relationships + join semantics |
| `CONSUME` | Post-build | **Consume: Create Dashboard** | QuickSight visualization on Gold |
| `GOVERN` | Post-build | **Govern: Trace Data Lineage** | Compliance docs, impact analysis |
| `prompts/regulation/` | Optional | **Regulation-Specific Controls** | GDPR, CCPA, HIPAA, SOX, PCI DSS — loaded only when regulation selected during discovery (referenced from SKILLS.md section 6a) |

---

## Prompt Hierarchy (Parent-Child Graph)

```
                           ┌──────────────────────────┐
                           │     USER REQUEST          │
                           │  "I have data to onboard" │
                           └────────────┬─────────────┘
                                        │
                                        ▼
                    ┌───────────────────────────────────────┐
                    │  ROUTE: Check Existing Source          │
                    │  ─────────────────────────────         │
                    │  Agent: Router (inline)                │
                    │  Action: Search workloads/ folder      │
                    │  Decision: found / not found / partial │
                    └───────────────┬───────────────────────┘
                                    │
               ┌────────────────────┼──────────────────────┐
               │                    │                      │
               ▼                    ▼                      ▼
        ┌──────────┐     ┌──────────────────┐    ┌──────────────────┐
        │  FOUND   │     │  NOT FOUND       │    │  PARTIAL         │
        │          │     │                  │    │                  │
        │ Use or   │     │  Need real data? │    │ Complete missing │
        │ modify   │     │                  │    │ zones            │
        │ existing │     └───────┬──────────┘    └──────────────────┘
        └──────────┘             │
                        ┌────────┴────────┐
                        │                 │
                        ▼                 ▼
              ┌──────────────┐   ┌──────────────────────────────────────┐
              │  GENERATE    │   │  ONBOARD: Build Data Pipeline        │
              │  ──────────  │   │  ────────────────────────────         │
              │  (optional)  │   │  Agent: Data Onboarding (orchestrator)│
              │  Create      │   │                                       │
              │  synthetic   │   │  THIS IS THE MASTER PROMPT            │
              │  test data   │   │  Spawns 4 sub-agent prompts:          │
              │              │   │                                       │
              │  Output:     │   │  ┌─────────────────────────────────┐ │
              │  CSV files   │   │  │ Phase 1: Discovery (inline)     │ │
              │  in shared/  │   │  │  Questions → semantic.yaml      │ │
              │  fixtures/   │   │  ├─────────────────────────────────┤ │
              └──────┬───────┘   │  │ Phase 2: Dedup (inline)         │ │
                     │           │  │  Check for duplicate sources    │ │
                     │           │  ├─────────────────────────────────┤ │
                     └──────────>│  │ Phase 3: Profile (sub-agent)    │ │
                                 │  │  Glue Crawler + Athena          │ │
                    ┌───────────>│  ├─────────────────────────────────┤ │
                    │            │  │ Phase 4: Build (4 sub-agents)   │ │
                    │            │  │                                  │ │
                    │            │  │  ┌──────────────────────────┐   │ │
                    │            │  │  │ SUB-PROMPT: Metadata      │   │ │
                    │            │  │  │ Agent: Metadata Agent     │   │ │
                    │            │  │  │ Output: semantic.yaml,    │   │ │
                    │            │  │  │   source.yaml, catalog    │   │ │
                    │            │  │  │ Test gate: unit+integ     │   │ │
                    │            │  │  └──────────┬───────────────┘   │ │
                    │            │  │             │ PASS              │ │
                    │            │  │             ▼                    │ │
                    │            │  │  ┌──────────────────────────┐   │ │
                    │            │  │  │ SUB-PROMPT: Transform     │   │ │
                    │            │  │  │ Agent: Transformation     │   │ │
                    │            │  │  │ Output: bronze_to_silver, │   │ │
                    │            │  │  │   silver_to_gold scripts  │   │ │
                    │            │  │  │ Test gate: unit+integ     │   │ │
                    │            │  │  └──────────┬───────────────┘   │ │
                    │            │  │             │ PASS              │ │
                    │            │  │             ▼                    │ │
                    │            │  │  ┌──────────────────────────┐   │ │
                    │            │  │  │ SUB-PROMPT: Quality       │   │ │
                    │            │  │  │ Agent: Quality Agent      │   │ │
                    │            │  │  │ Output: quality_rules,    │   │ │
                    │            │  │  │   check scripts           │   │ │
                    │            │  │  │ Test gate: unit+integ     │   │ │
                    │            │  │  └──────────┬───────────────┘   │ │
                    │            │  │             │ PASS              │ │
                    │            │  │             ▼                    │ │
                    │            │  │  ┌──────────────────────────┐   │ │
                    │            │  │  │ SUB-PROMPT: DAG           │   │ │
                    │            │  │  │ Agent: Orchestration DAG  │   │ │
                    │            │  │  │ Output: Airflow DAG,      │   │ │
                    │            │  │  │   schedule config         │   │ │
                    │            │  │  │ Test gate: unit+integ     │   │ │
                    │            │  │  └──────────┬───────────────┘   │ │
                    │            │  │             │ PASS              │ │
                    │            │  ├─────────────────────────────────┤ │
                    │            │  │ Phase 5: Human Review            │ │
                    │            │  │  Present all artifacts + tests  │ │
                    │            │  │  Human approves → deploy        │ │
                    │            │  └─────────────────────────────────┘ │
                    │            └───────────────┬───────────────────────┘
                    │                            │
                    │                            │ Workload created
                    │                            ▼
                    │     ┌───────────────────────────────────────────────────┐
                    │     │              POST-BUILD PROMPTS                    │
                    │     │         (run after ONBOARD completes)              │
                    │     │                                                    │
                    │     │  ┌──────────────────┐  ┌───────────────────────┐  │
                    │     │  │ ENRICH           │  │ CONSUME               │  │
                    │     │  │ ────────         │  │ ───────               │  │
                    │     │  │ Link datasets    │  │ QuickSight dashboard  │  │
                    │     │  │ via FK           │  │ on Gold zone data     │  │
                    │     │  │                  │  │                       │  │
                    │     │  │ Updates:         │  │ Creates:              │  │
                    │     │  │ - semantic.yaml  │  │ - analytics.yaml      │  │
                    │     │  │ - transform      │  │ - Data source         │  │
                    │     │  │   scripts        │  │ - Datasets            │  │
                    │     │  │ - quality rules  │  │ - Dashboard           │  │
                    │     │  │ - DAG            │  │ - Permissions         │  │
                    │     │  │ - SynoDB seeds   │  │                       │  │
                    │     │  └──────────────────┘  └───────────────────────┘  │
                    │     │                                                    │
                    │     │  ┌──────────────────────────────────────────────┐ │
                    │     │  │ GOVERN                                        │ │
                    │     │  │ ──────                                        │ │
                    │     │  │ Trace lineage, compliance docs, DPC          │ │
                    │     │  │                                               │ │
                    │     │  │ Generates:                                    │ │
                    │     │  │ - data_product_catalog.yaml                  │ │
                    │     │  │ - Lineage diagrams                           │ │
                    │     │  │ - Compliance reports                         │ │
                    │     │  └──────────────────────────────────────────────┘ │
                    │     └───────────────────────────────────────────────────┘
                    │
                    │  Can loop back for second dataset:
                    └──── ROUTE → ONBOARD (dataset 2) → ENRICH (link to dataset 1)
```

---

## Decision Tree: Which Prompt to Use

```
START
  │
  ▼
  Do you have data to onboard?
  │
  ├── YES ──────────────────────────────────────────────────────────┐
  │                                                                  │
  │   Is it real production data?                                   │
  │   │                                                              │
  │   ├── YES ─── Run ROUTE first                                   │
  │   │           │                                                  │
  │   │           ├── FOUND ──── Use existing or modify             │
  │   │           │                                                  │
  │   │           ├── PARTIAL ── Complete missing zones              │
  │   │           │               (run ONBOARD for missing parts)   │
  │   │           │                                                  │
  │   │           └── NOT FOUND ── Run ONBOARD                      │
  │   │                            │                                 │
  │   │                            ├── Is it related to another     │
  │   │                            │   dataset?                      │
  │   │                            │   │                             │
  │   │                            │   ├── YES ── Run ENRICH        │
  │   │                            │   └── NO ─── Skip ENRICH       │
  │   │                            │                                 │
  │   │                            ├── Do stakeholders need          │
  │   │                            │   dashboards?                   │
  │   │                            │   │                             │
  │   │                            │   ├── YES ── Run CONSUME       │
  │   │                            │   └── NO ─── Skip CONSUME      │
  │   │                            │                                 │
  │   │                            └── Need compliance docs?        │
  │   │                                │                             │
  │   │                                ├── YES ── Run GOVERN        │
  │   │                                └── NO ─── Done              │
  │   │                                                              │
  │   └── NO (need demo/test data) ─── Run GENERATE                │
  │                                     │                            │
  │                                     └── Then run ONBOARD        │
  │                                         (on generated data)     │
  │                                                                  │
  └── NO ─── What do you need?                                     │
              │                                                      │
              ├── Link existing datasets ──── Run ENRICH            │
              ├── Dashboard on existing Gold ── Run CONSUME         │
              ├── Lineage documentation ──── Run GOVERN             │
              └── Understand the data ──── Run GOVERN               │
```

---

## Prompt-to-Agent Mapping

Each prompt maps to one or more agents in the multi-agent architecture:

```
PROMPT                 AGENT(S)                    EXECUTION MODEL
──────                 ────────                    ───────────────

ROUTE          ──→     Router Agent                Inline (main conversation)
                       Searches workloads/ folder

GENERATE       ──→     Data Onboarding Agent       Inline (main conversation)
                       Generates Python scripts     No sub-agents needed

ONBOARD        ──→     Data Onboarding Agent       Inline (orchestrator)
               │       Phase 1-2: inline
               │
               ├──→    Metadata Agent              Sub-agent (Agent tool)
               │       Phase 3-4: spawned
               │
               ├──→    Transformation Agent        Sub-agent (Agent tool)
               │       Phase 4: spawned
               │
               ├──→    Quality Agent               Sub-agent (Agent tool)
               │       Phase 4: spawned
               │
               └──→    Orchestration DAG Agent     Sub-agent (Agent tool)
                       Phase 4: spawned

ENRICH         ──→     Data Onboarding Agent       Inline (orchestrator)
               │       Updates configs
               │
               └──→    Metadata Agent              Sub-agent (for FK validation)
                       Updates semantic.yaml

CONSUME        ──→     Data Onboarding Agent       Inline
                       + QuickSight API calls       No sub-agents needed

GOVERN         ──→     Data Onboarding Agent       Inline
                       Reads all configs,           No sub-agents needed
                       generates reports
```

---

## Prompt Dependency Graph

This shows which prompts must run before others:

```
                    GENERATE (optional)
                        │
                        │ produces CSV fixtures
                        │
                        ▼
    ROUTE ─────────→ ONBOARD ─────────→ ENRICH
    (required)       (required)          (optional)
    must run first   core pipeline       requires 2+ workloads
                        │
                        │
                        ├─────────────→ CONSUME
                        │               (optional)
                        │               requires Gold zone
                        │
                        └─────────────→ GOVERN
                                        (optional)
                                        requires workload exists
```

**Dependency rules**:
- `ROUTE` must always run before `ONBOARD` (prevents duplicates)
- `GENERATE` runs before `ONBOARD` only when no real data exists
- `ENRICH` requires at least 2 completed workloads
- `CONSUME` requires Gold zone tables to exist
- `GOVERN` requires at least 1 completed workload
- `ONBOARD` internally enforces sub-agent ordering: Metadata → Transform → Quality → DAG

---

## Prompt Data Flow (What Feeds What)

```
┌─────────────┐
│ Human Input  │  (your ONBOARD prompt)
│              │
│ Provides:    │
│ - Source     │──────────────────────────────────────────────────────────────────┐
│ - Schema     │                                                                  │
│ - Semantic   │                                                                  │
│   Layer      │                                                                  │
│ - Quality    │                                                                  │
│ - Schedule   │                                                                  │
└──────┬───────┘                                                                  │
       │                                                                          │
       ▼                                                                          │
┌──────────────────────────────────────────────────────────────────────────────┐  │
│  ONBOARD PROMPT (Master Orchestrator)                                         │  │
│                                                                                │  │
│  Decomposes human input into sub-agent context:                               │  │
│                                                                                │  │
│  ┌────────────────────────────────────────────────────────────────────────┐   │  │
│  │  METADATA SUB-PROMPT receives:                                         │   │  │
│  │  - Source location, format, credentials                                │   │  │
│  │  - Column roles from human                                             │   │  │
│  │  - PII column list from human                                          │   │  │
│  │                                                                         │   │  │
│  │  Produces → source.yaml, semantic.yaml (technical metadata section)    │   │  │
│  └────────────────────────────────────────────────────────────────────────┘   │  │
│       │                                                                        │  │
│       ▼ test gate PASS                                                        │  │
│  ┌────────────────────────────────────────────────────────────────────────┐   │  │
│  │  TRANSFORM SUB-PROMPT receives:                                        │   │  │
│  │  - Schema (from Metadata Agent output)                                 │   │  │
│  │  - Cleaning rules (from human: dedup, nulls, type casting)            │   │  │
│  │  - Column roles (measures/dimensions from semantic.yaml)               │   │  │
│  │  - Gold zone format (star schema / flat / etc from human)             │   │  │
│  │                                                                         │   │  │
│  │  Produces → transformations.yaml, bronze_to_silver.py, silver_to_gold │   │  │
│  └────────────────────────────────────────────────────────────────────────┘   │  │
│       │                                                                        │  │
│       ▼ test gate PASS                                                        │  │
│  ┌────────────────────────────────────────────────────────────────────────┐   │  │
│  │  QUALITY SUB-PROMPT receives:                                          │   │  │
│  │  - Schema + profiling baselines (from Metadata Agent)                  │   │  │
│  │  - Quality thresholds (from human: 80% Silver, 95% Gold)              │   │  │
│  │  - PII classifications (from Metadata Agent)                           │   │  │
│  │                                                                         │   │  │
│  │  Produces → quality_rules.yaml, check_silver.py, check_gold.py       │   │  │
│  └────────────────────────────────────────────────────────────────────────┘   │  │
│       │                                                                        │  │
│       ▼ test gate PASS                                                        │  │
│  ┌────────────────────────────────────────────────────────────────────────┐   │  │
│  │  DAG SUB-PROMPT receives:                                              │   │  │
│  │  - All scripts (from Transform + Quality Agents)                       │   │  │
│  │  - Schedule config (from human: cron, SLA, retries)                    │   │  │
│  │  - Dependencies (from human: wait for other DAGs)                      │   │  │
│  │  - Shared operators (from shared/ folder)                              │   │  │
│  │                                                                         │   │  │
│  │  Produces → {workload}_dag.py, schedule.yaml, deploy_to_aws.py       │   │  │
│  └────────────────────────────────────────────────────────────────────────┘   │  │
│                                                                                │  │
│  All sub-agents complete → present artifacts to human → approve               │  │
│  Deployment includes MWAA step + mandatory post-deployment verification      │  │
└──────────────────────────────────────────────────────────────────────────────┘  │
       │                                                                          │
       │ Workload created in workloads/{name}/                                   │
       │                                                                          │
       ▼                                                                          │
┌──────────────────────────────────────────────────────────────────────────────┐  │
│  ENRICH PROMPT receives:                                                      │  │
│  - Two existing workloads (from completed ONBOARD runs)                       │  │
│  - FK specification (from human: source.col → target.col)                    │  │
│  - Join semantics (from human: when to join, fan-out, pre-agg)              │  │
│                                                                                │  │
│  Updates → semantic.yaml (relationships), scripts (FK validation),           │  │
│            DAG (ExternalTaskSensor), quality rules (FK integrity)             │  │
│            SynoDB (joined query seeds)                                         │  │
└──────────────────────────────────────────────────────────────────────────────┘  │
       │                                                                          │
       ▼                                                                          │
┌──────────────────────────────────────────────────────────────────────────────┐  │
│  CONSUME PROMPT receives:                                                     │  │
│  - Gold zone table names (from completed ONBOARD)                             │  │
│  - Dashboard spec (from human: visuals, datasets, permissions)               │  │
│  - Semantic context (from semantic.yaml: measures, dims, aggregations)        │←─┘
│                                                                                │
│  Creates → analytics.yaml, QuickSight data source, datasets, dashboard       │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Semantic Layer Build Pipeline

This is the most important diagram for understanding HOW the semantic layer is constructed:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SEMANTIC LAYER BUILD PIPELINE                          │
│                                                                           │
│  INPUT SOURCES                    PROCESSING              OUTPUT STORES   │
│  ═════════════                    ══════════              ═════════════   │
│                                                                           │
│  ┌──────────────┐                                                        │
│  │ HUMAN INPUT   │ ── Column roles ─────────────┐                        │
│  │ (ONBOARD      │ ── Aggregation semantics ────┤                        │
│  │  prompt)       │ ── Grain definition ─────────┤                        │
│  │               │ ── Business terms ────────────┤                        │
│  │               │ ── Synonyms ──────────────────┤                        │
│  │               │ ── Default filters ───────────┤                        │
│  │               │ ── Dimension hierarchies ─────┤                        │
│  │               │ ── Time intelligence ─────────┤    ┌───────────────┐  │
│  │               │ ── Seed questions ────────────┤    │               │  │
│  │               │ ── Data steward ──────────────┤───>│ semantic.yaml │  │
│  └──────────────┘                                │    │ (local config │  │
│                                                  │    │  file)        │  │
│  ┌──────────────┐                                │    │               │  │
│  │ GLUE CRAWLER  │ ── Column names ──────────────┤    │ SINGLE SOURCE │  │
│  │ (automatic)   │ ── Data types ────────────────┤    │ OF TRUTH      │  │
│  │               │ ── Partitions ────────────────┤    │               │  │
│  │               │ ── File format ───────────────┤    │ Combines:     │  │
│  └──────────────┘                                │    │ - Technical   │  │
│                                                  │    │   metadata    │  │
│  ┌──────────────┐                                │    │ - Business    │  │
│  │ ATHENA        │ ── Null rates ────────────────┤    │   context     │  │
│  │ PROFILING     │ ── Min/max/avg ───────────────┤    │ - AI Agent    │  │
│  │ (5% sample)   │ ── Distinct values ───────────┤    │   context     │  │
│  │               │ ── Top values ────────────────┤    │               │  │
│  │               │ ── Row count ─────────────────┤    └───────┬───────┘  │
│  └──────────────┘                                │            │          │
│                                                  │            │ deploy   │
│  ┌──────────────┐                                │            │          │
│  │ GLUE PII      │ ── PII flags ────────────────┤       ┌────┴────┐     │
│  │ DETECTION     │ ── Confidence scores ─────────┤       │         │     │
│  │ (automatic)   │ ── Masking recommendations ───┘       ▼         ▼     │
│  └──────────────┘                               ┌────────────┐ ┌──────┐ │
│                                                  │ SageMaker   │ │SynoDB│ │
│  ┌──────────────┐                               │ Catalog     │ │      │ │
│  │ METADATA      │ ── FK candidates ────────────>│ (custom     │ │Seed  │ │
│  │ AGENT         │ ── Schema evolution ─────────>│  metadata   │ │SQL + │ │
│  │ (sub-agent)   │ ── Relationship suggestions ─>│  columns)   │ │Learn │ │
│  └──────────────┘                               │             │ │      │ │
│                                                  │ READ BY:    │ │READ: │ │
│  ┌──────────────┐                               │ All agents  │ │Analy-│ │
│  │ ENRICH        │ ── Join semantics ───────────>│ at runtime  │ │sis   │ │
│  │ PROMPT        │ ── Relationship details ─────>│             │ │Agent │ │
│  │ (human input) │ ── Sample joined queries ────>│             │ │      │ │
│  └──────────────┘                               └────────────┘ └──────┘ │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Sub-Agent Spawning Sequence (Inside ONBOARD)

```
ONBOARD Prompt (Data Onboarding Agent — main conversation)
│
│  PHASE 1: Discovery (inline)
│  ──────────────────────────
│  Human answers questions → feeds all downstream agents
│  Output: structured context for each sub-agent
│
│  PHASE 2: Dedup (inline)
│  ──────────────────────
│  Check workloads/*/config/source.yaml for overlap
│  Output: clear to proceed (or block if duplicate)
│
│  PHASE 3: Profile (sub-agent spawn #1)
│  ──────────────────────────────────────
│  ┌─────────────────────────────────────────────────────────┐
│  │ Agent(                                                    │
│  │   subagent_type="general-purpose",                       │
│  │   description="Profile source data",                     │
│  │   prompt="You are the Metadata Agent..."                 │
│  │ )                                                         │
│  │                                                           │
│  │ Sub-agent runs Glue Crawler + Athena profiling           │
│  │ Returns: schema, null rates, value distributions          │
│  └─────────────────────────────────────────────────────────┘
│  │
│  ▼ TEST GATE: metadata tests pass?
│  │
│  ├── FAIL (retry 1) → re-spawn with error context
│  ├── FAIL (retry 2) → re-spawn with error context
│  ├── FAIL (retry 3) → ESCALATE to human
│  └── PASS → continue
│
│  PHASE 4.1: Metadata formalization (sub-agent spawn #2)
│  ────────────────────────────────────────────────────────
│  ┌─────────────────────────────────────────────────────────┐
│  │ Agent(                                                    │
│  │   prompt="You are the Metadata Agent. Formalize          │
│  │   schema + business context into semantic.yaml..."        │
│  │ )                                                         │
│  │                                                           │
│  │ Merges: profiler output + human business context          │
│  │ Returns: source.yaml, semantic.yaml, catalog registration │
│  └─────────────────────────────────────────────────────────┘
│  │
│  ▼ TEST GATE ── PASS
│
│  PHASE 4.2: Transform (sub-agent spawn #3)
│  ──────────────────────────────────────────
│  ┌─────────────────────────────────────────────────────────┐
│  │ Agent(                                                    │
│  │   prompt="You are the Transformation Agent.              │
│  │   Schema: {from metadata agent}                           │
│  │   Cleaning rules: {from human}                            │
│  │   Column roles: {from semantic.yaml}                      │
│  │   Gold format: {star_schema / flat}..."                   │
│  │ )                                                         │
│  │                                                           │
│  │ Returns: transformations.yaml, bronze_to_silver.py,      │
│  │          silver_to_gold.py, SQL files                     │
│  └─────────────────────────────────────────────────────────┘
│  │
│  ▼ TEST GATE ── PASS
│
│  PHASE 4.3: Quality (sub-agent spawn #4)
│  ────────────────────────────────────────
│  ┌─────────────────────────────────────────────────────────┐
│  │ Agent(                                                    │
│  │   prompt="You are the Quality Agent.                     │
│  │   Schema: {from metadata}                                 │
│  │   Baselines: {null rates, ranges from profiler}           │
│  │   Thresholds: {from human: 80% Silver, 95% Gold}..."     │
│  │ )                                                         │
│  │                                                           │
│  │ Returns: quality_rules.yaml, check_silver.py,            │
│  │          check_gold.py                                    │
│  └─────────────────────────────────────────────────────────┘
│  │
│  ▼ TEST GATE ── PASS
│
│  PHASE 4.4: DAG (sub-agent spawn #5)
│  ────────────────────────────────────
│  ┌─────────────────────────────────────────────────────────┐
│  │ Agent(                                                    │
│  │   prompt="You are the Orchestration DAG Agent.           │
│  │   Scripts: {all scripts from transform + quality}         │
│  │   Schedule: {cron from human}                             │
│  │   Dependencies: {from human}..."                          │
│  │ )                                                         │
│  │                                                           │
│  │ Returns: {workload}_dag.py, schedule.yaml                │
│  └─────────────────────────────────────────────────────────┘
│  │
│  ▼ TEST GATE ── PASS
│
│  PHASE 5: Deploy to AWS (inline, via MCP)
│  ─────────────────────────────────────────
│  After human approval, orchestrator deploys:
│  Step 5.1-5.7: S3 upload, Glue registration, IAM, LF, KMS, Query Verify, Audit
│  Step 5.8: Deploy DAG to MWAA (upload DAG + shared utils + config + scripts to MWAA S3 bucket)
│  Step 5.9: Post-Deployment Verification (mandatory smoke test:
│             Glue Catalog tables exist, Athena queries work, LF-Tags applied,
│             TBAC grants active, KMS encryption verified, MWAA DAG parse success,
│             QuickSight datasets accessible, CloudTrail audit logs present)
│  │
│  Human approves → workload complete
```

---

## Test Gate Logic (Retry / Escalate Decision Tree)

```
Sub-agent returns artifacts
        │
        ▼
Run unit + integration tests
        │
        ├── ALL PASS ──────────────────→ Proceed to next sub-agent
        │
        └── SOME FAIL
            │
            ▼
        Retry count < 2?
            │
            ├── YES ── Re-spawn sub-agent with:
            │          - Original context
            │          - Error details from failed tests
            │          - Instruction: "Fix these failures"
            │          │
            │          ▼
            │     Sub-agent returns revised artifacts
            │          │
            │          ▼
            │     Run tests again ──→ (loop back to top)
            │
            └── NO (retried twice already)
                │
                ▼
            ESCALATE TO HUMAN
            │
            Show:
            - Which sub-agent failed
            - Which tests failed
            - Error details
            - Sub-agent's attempted fixes
            │
            Human decides:
            ├── "Fix X and retry" ──→ Re-spawn with human guidance
            ├── "Skip this step" ──→ Proceed (with warning)
            └── "Abort" ──→ Stop pipeline build
```

---

## Prompt Composition Pattern

For a presentation, this shows how a single ONBOARD prompt **decomposes** into multiple agent interactions:

```
USER WRITES ONE PROMPT (ONBOARD)
════════════════════════════════

"Onboard order_transactions from S3..."
  │
  │  Contains 7 sections:
  │  1. Source details
  │  2. Schema + column roles
  │  3. Semantic layer (aggregations, terms, filters, seeds)
  │  4. Zone configs (Bronze/Silver/Gold)
  │  5. Quality rules
  │  6. Schedule
  │  7. Build instructions
  │
  ▼

SYSTEM DECOMPOSES INTO 5+ AGENT INTERACTIONS
═════════════════════════════════════════════

  Interaction 1: Router check (inline, 30 sec)
  ├── Input:  source location
  └── Output: "not found, proceed"

  Interaction 2: Discovery questions (inline, 5 min)
  ├── Input:  prompt sections 1-7
  ├── Output: validated context for each sub-agent
  └── Action: ask follow-up questions if info missing

  Interaction 3: Metadata Agent (sub-agent, 5-10 min)
  ├── Input:  source + schema + column roles
  ├── Output: source.yaml, semantic.yaml (technical), catalog entry
  └── Gate:   43 tests must pass

  Interaction 4: Transformation Agent (sub-agent, 10-15 min)
  ├── Input:  schema + cleaning rules + Gold format + column roles
  ├── Output: transformations.yaml, bronze_to_silver.py, silver_to_gold.py
  └── Gate:   61 tests must pass

  Interaction 5: Quality Agent (sub-agent, 5-10 min)
  ├── Input:  schema + baselines + thresholds
  ├── Output: quality_rules.yaml, check scripts
  └── Gate:   41 tests must pass

  Interaction 6: DAG Agent (sub-agent, 5-10 min)
  ├── Input:  all scripts + schedule + dependencies
  ├── Output: {workload}_dag.py, deploy_to_aws.py
  └── Gate:   51 tests must pass

  Interaction 7: Human review (inline, 2 min)
  ├── Input:  all artifacts + 196 test results
  └── Output: "approved" or "change X"

  Interaction 8: Deploy to AWS (inline via MCP, 10-15 min)
  ├── Input:  approved artifacts
  ├── Steps:  S3 upload, Glue registration, IAM, LF, KMS, Query Verify, Audit
  │           MWAA DAG deployment (Step 5.8: upload DAG + shared utils + config + scripts)
  │           Post-deployment verification (Step 5.9: mandatory smoke test)
  └── Output: Live workload in AWS, all tests passed


TOTAL: 1 human prompt → 8 interactions → 196 tests → 20+ files created → deployed to AWS
```

---

## Presentation Slides Outline

If presenting to a technical audience, use these slides:

### Slide 1: "One Prompt, Full Pipeline"
- Show: User writes ONBOARD prompt (left) → System produces 20+ files (right)
- Key message: One structured prompt replaces hours of manual setup

### Slide 2: "Prompt Taxonomy"
- Show: The 6-prompt table (ROUTE, GENERATE, ONBOARD, ENRICH, CONSUME, GOVERN)
- Key message: Each prompt has a clear phase and purpose

### Slide 3: "Prompt Dependency Graph"
- Show: ROUTE → ONBOARD → (ENRICH / CONSUME / GOVERN)
- Key message: Prompts chain together in a defined order

### Slide 4: "Inside ONBOARD — Sub-Agent Architecture"
- Show: The sub-agent spawning sequence diagram
- Key message: One master prompt spawns 4 sub-agents with test gates

### Slide 5: "Test Gates Ensure Quality"
- Show: The retry/escalate decision tree
- Key message: Every sub-agent's output is tested before proceeding

### Slide 6: "The Semantic Layer — How It's Built"
- Show: The semantic layer build pipeline diagram
- Key message: Automatic profiling + human business context = AI-ready metadata

### Slide 7: "What Feeds the Semantic Layer"
- Show: The automatic vs human metadata table
- Key message: Technical metadata is auto-detected; business context comes from you

### Slide 8: "The Learning Loop"
- Show: Day 1 (8 seeds, 70%) → Day 30 (100+ patterns, 90%) → Day 90 (300+, 95%)
- Key message: System gets smarter with every query

### Slide 9: "Query Walkthrough — NLP to SQL"
- Show: "Average order value by segment this quarter?" → step-by-step SQL generation
- Key message: The semantic layer tells the AI exactly how to aggregate, filter, and join

### Slide 10: "Wrong Without Semantic Layer"
- Show: Side-by-side correct SQL vs wrong SQL
- Key message: Without aggregation semantics and default filters, queries are subtly wrong
