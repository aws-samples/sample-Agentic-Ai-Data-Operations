# Visual Workflow Diagram: Complete Data Onboarding

## Master Workflow: All 6 Prompts

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                           USER REQUEST                                      │
│                   "I want to onboard customer data"                        │
│                                                                             │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
        ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
        ┃         STEP 1: ROUTE (Check Existence)             ┃
        ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                                   │
                   ┌───────────────┴───────────────┐
                   │                               │
                   ▼                               ▼
         ┌──────────────────┐          ┌──────────────────┐
         │  FOUND           │          │  NOT FOUND       │
         │  (Exists)        │          │  (New)           │
         └────────┬─────────┘          └────────┬─────────┘
                  │                             │
                  │                             ▼
                  │              ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
                  │              ┃  STEP 2: GENERATE (Optional)   ┃
                  │              ┃  Create synthetic test data    ┃
                  │              ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                  │                             │
                  │                             ▼
                  │              ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
                  │              ┃  STEP 3: ONBOARD               ┃
                  │              ┃  Build complete pipeline       ┃
                  │              ┃  Bronze → Silver → Gold        ┃
                  │              ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                  │                             │
                  └─────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼                             ▼
         ┏━━━━━━━━━━━━━━━━━━━┓       ┏━━━━━━━━━━━━━━━━━━━┓
         ┃  STEP 4: ENRICH   ┃       ┃  STEP 5: CONSUME  ┃
         ┃  Link datasets    ┃       ┃  Create dashboard ┃
         ┗━━━━━━━━━━━━━━━━━━━┛       ┗━━━━━━━━━━━━━━━━━━━┛
                    │                             │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                        ┏━━━━━━━━━━━━━━━━━━━┓
                        ┃  STEP 6: GOVERN   ┃
                        ┃  Document lineage ┃
                        ┗━━━━━━━━━━━━━━━━━━━┛
                                   │
                                   ▼
                        ┌──────────────────┐
                        │   COMPLETE       │
                        │   Data Product   │
                        └──────────────────┘
```

---

## ONBOARD Prompt Internal Flow (Most Complex)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  ONBOARD: "Onboard customer data..."                        │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
        ╔══════════════════════════════════════════════════╗
        ║        PHASE 1: DISCOVERY (Main Context)        ║
        ║                                                  ║
        ║  Data Onboarding Agent asks questions:          ║
        ║  1. Source details (location, format, creds)    ║
        ║  2. Column identification (PK, PII, exclusions) ║
        ║  3. Cleaning rules (dedup, nulls, types)        ║
        ║  4. Metrics & dimensions (roles, agg, hier)     ║
        ║  5. Quality rules (thresholds, compliance)      ║
        ║  6. Scheduling (cron, dependencies, failure)    ║
        ╚══════════════════════════════════════════════════╝
                                   │
                                   ▼
        ╔══════════════════════════════════════════════════╗
        ║    PHASE 2: DEDUPLICATION (Main Context)        ║
        ║                                                  ║
        ║  MCP: local-filesystem.search_workloads()       ║
        ║  └─> Check for duplicate sources                ║
        ║                                                  ║
        ║  MCP: core.s3.list_objects() OR                 ║
        ║       aws-dataprocessing.get_table()            ║
        ║  └─> Validate source connectivity               ║
        ╚══════════════════════════════════════════════════╝
                                   │
                                   ▼
        ╔══════════════════════════════════════════════════╗
        ║  PHASE 3: PROFILING (Spawn Metadata Agent)      ║
        ║                                                  ║
        ║  Sub-Agent: Metadata Agent (separate context)   ║
        ║  ├─> Generate profiling script                  ║
        ║  └─> Return script to main conversation         ║
        ║                                                  ║
        ║  Main Conversation executes via MCP:            ║
        ║  ├─> aws-dataprocessing.create_crawler()        ║
        ║  ├─> aws-dataprocessing.start_crawler()         ║
        ║  ├─> aws-dataprocessing.get_crawler()           ║
        ║  ├─> aws-dataprocessing.start_query_execution() ║
        ║  │    └─> Profile 5% sample                     ║
        ║  └─> sagemaker-catalog.put_custom_metadata()    ║
        ║       └─> Store tech + business metadata        ║
        ║                                                  ║
        ║  Present results to human → Confirm             ║
        ╚══════════════════════════════════════════════════╝
                                   │
                                   ▼
        ╔══════════════════════════════════════════════════╗
        ║      PHASE 4: BUILD (Spawn 4 Sub-Agents)        ║
        ╚══════════════════════════════════════════════════╝
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
  ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
  │ Transformation│      │    Quality    │      │  Orchestration│
  │     Agent     │      │     Agent     │      │   DAG Agent   │
  │               │      │               │      │               │
  │ Generates:    │      │ Generates:    │      │ Generates:    │
  │ • trans.yaml  │      │ • quality.yml │      │ • dag.py      │
  │ • scripts/    │      │ • scripts/    │      │ • tests/      │
  │ • tests/      │      │ • tests/      │      │               │
  └───────┬───────┘      └───────┬───────┘      └───────┬───────┘
          │                      │                      │
          │  Returns to          │  Returns to          │  Returns to
          │  main context        │  main context        │  main context
          │                      │                      │
          ▼                      ▼                      ▼
  ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
  │  TEST GATE    │      │  TEST GATE    │      │  TEST GATE    │
  │  Run tests in │      │  Run tests in │      │  Run tests in │
  │  main context │      │  main context │      │  main context │
  └───────┬───────┘      └───────┬───────┘      └───────┬───────┘
          │                      │                      │
          │  ✓ PASS             │  ✓ PASS             │  ✓ PASS
          │                      │                      │
          ▼                      ▼                      ▼
  ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
  │ MCP Deploy    │      │ MCP Deploy    │      │ MCP Deploy    │
  │               │      │               │      │               │
  │ • Glue ETL    │      │ • DQ Ruleset  │      │ • Step Fns    │
  │ • S3 Tables   │      │ • CW Alarms   │      │ • EventBridge │
  │ • Iceberg     │      │ • SNS Topic   │      │ • Lambda      │
  └───────────────┘      └───────────────┘      └───────────────┘
                                   │
          ┌────────────────────────┴────────────────────────┐
          │                                                  │
          └──────────────────────────┬───────────────────────┘
                                   │
                                   ▼
        ╔══════════════════════════════════════════════════╗
        ║   PHASE 5: APPROVAL & DEPLOYMENT                 ║
        ║                                                  ║
        ║  Present summary to human:                      ║
        ║  • All configs generated                        ║
        ║  • All scripts written                          ║
        ║  • All tests passed (X/X)                       ║
        ║  • MCP operations planned                       ║
        ║                                                  ║
        ║  Human approves → Execute all MCP operations    ║
        ╚══════════════════════════════════════════════════╝
                                   │
                                   ▼
                        ┌──────────────────┐
                        │   COMPLETE       │
                        │   Pipeline Live  │
                        └──────────────────┘
```

---

## MCP Server Interaction Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA ONBOARDING AGENT                               │
│                      (Main Conversation Context)                            │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                │ All AWS operations via MCP
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   Catalog &  │      │   Storage &  │      │ Orchestration│
│   Metadata   │      │  Transform   │      │  & Alerting  │
└──────────────┘      └──────────────┘      └──────────────┘
        │                      │                      │
        ├─> aws-dataprocessing │                      ├─> stepfunctions
        │    • create_crawler  │                      │    • create_state_machine
        │    • start_crawler   │                      │    • start_execution
        │    • get_table       │                      │
        │    • start_query     │                      ├─> eventbridge
        │    • create_job      │                      │    • put_rule
        │    • start_job_run   ├─> s3-tables         │    • put_targets
        │                      │    • create_table    │
        ├─> sagemaker-catalog  │    • update_table   ├─> lambda
        │    • put_metadata    │                      │    • create_function
        │    • get_metadata    ├─> core              │    • invoke_function
        │    • list_measures   │    • s3.put_object  │
        │                      │    • kms.encrypt    ├─> sns-sqs
        ├─> dynamodb           │                      │    • create_topic
        │    • put_item        └─> aws-dataprocessing│    • publish
        │    • query           │    • create_dq_rule  │
        │    • scan            │    • start_dq_run   ├─> cloudwatch
        │                      │                      │    • put_metric
        └─> local-filesystem  │                      │    • put_alarm
             • list_workloads  │                      │
             • get_config      │                      └─> cloudtrail
                               │                           • lookup_events
                               ▼
                    ┌──────────────────┐
                    │   AWS Services   │
                    │ Glue • S3 • Athena│
                    │ Step Fns • Lambda│
                    │ CloudWatch • SNS │
                    └──────────────────┘
```

---

## Data Flow Through Zones

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SOURCE DATA                                        │
│         RDS • S3 • API • Kafka • On-Prem • DynamoDB                        │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │ ONBOARD Prompt Triggered    │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
        ╔══════════════════════════════════════════════════╗
        ║              BRONZE ZONE                         ║
        ║                                                  ║
        ║  Storage: S3 (raw format - CSV/JSON/Parquet)    ║
        ║  State: Immutable (write-once)                  ║
        ║  Quality Gate: None                             ║
        ║                                                  ║
        ║  MCP Operations:                                ║
        ║  • core.s3.put_object()                         ║
        ║  • aws-dataprocessing.create_crawler()          ║
        ║                                                  ║
        ║  Data: Exact copy of source                     ║
        ║  Partitioning: By ingestion_date                ║
        ║  Retention: 7-30 days typical                   ║
        ╚══════════════════════════════════════════════════╝
                                   │
                                   │ Transformation Agent
                                   │ Glue ETL Job
                                   │
                                   ▼
        ╔══════════════════════════════════════════════════╗
        ║              SILVER ZONE                         ║
        ║                                                  ║
        ║  Storage: S3 Tables (Apache Iceberg)            ║
        ║  State: Updateable (schema-enforced)            ║
        ║  Quality Gate: Score >= 0.80                    ║
        ║                                                  ║
        ║  MCP Operations:                                ║
        ║  • aws-dataprocessing.create_job()              ║
        ║  • s3-tables.create_table() [Iceberg]           ║
        ║  • aws-dataprocessing.create_dq_ruleset()       ║
        ║  • sagemaker-catalog.put_custom_metadata()      ║
        ║                                                  ║
        ║  Data: Cleaned, validated, typed                ║
        ║  Features: Time-travel, ACID, schema evolution  ║
        ║  Partitioning: By business dimensions           ║
        ║  Retention: 1-3 years typical                   ║
        ╚══════════════════════════════════════════════════╝
                                   │
                                   │ Transformation Agent
                                   │ Glue ETL Job (aggregation)
                                   │
                                   ▼
        ╔══════════════════════════════════════════════════╗
        ║              GOLD ZONE                           ║
        ║                                                  ║
        ║  Storage: S3 Tables (Iceberg - star/flat)       ║
        ║  State: Updateable (curated)                    ║
        ║  Quality Gate: Score >= 0.95                    ║
        ║                                                  ║
        ║  MCP Operations:                                ║
        ║  • aws-dataprocessing.create_job()              ║
        ║  • s3-tables.create_table() [fact/dims]         ║
        ║  • aws-dataprocessing.create_dq_ruleset()       ║
        ║  • dynamodb.put_item() [SynoDB metrics]         ║
        ║                                                  ║
        ║  Data: Business-ready, aggregated               ║
        ║  Format: Star schema or flat (per discovery)    ║
        ║  Partitioning: By time + business dims          ║
        ║  Retention: 3-7 years typical                   ║
        ╚══════════════════════════════════════════════════╝
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼                             ▼
          ┌──────────────────┐          ┌──────────────────┐
          │    CONSUME       │          │     GOVERN       │
          │                  │          │                  │
          │ • Dashboards     │          │ • Lineage Docs   │
          │ • Reports        │          │ • Audit Logs     │
          │ • ML Models      │          │ • Compliance     │
          │ • APIs           │          │ • Impact Analysis│
          └──────────────────┘          └──────────────────┘
```

---

## Sub-Agent Spawning Pattern

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MAIN CONVERSATION                                        │
│              (Data Onboarding Agent runs here)                              │
│                                                                             │
│  • Has MCP access                                                          │
│  • Executes all AWS operations                                             │
│  • Spawns sub-agents for specialized work                                  │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   │ Agent tool (spawn)
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  SUB-AGENT 1     │      │  SUB-AGENT 2     │      │  SUB-AGENT 3     │
│  (Transformation)│      │  (Quality)       │      │  (DAG)           │
│                  │      │                  │      │                  │
│ • Separate       │      │ • Separate       │      │ • Separate       │
│   context        │      │   context        │      │   context        │
│ • NO MCP access  │      │ • NO MCP access  │      │ • NO MCP access  │
│ • Generates      │      │ • Generates      │      │ • Generates      │
│   files only     │      │   files only     │      │   files only     │
│                  │      │                  │      │                  │
│ Outputs:         │      │ Outputs:         │      │ Outputs:         │
│ • YAML configs   │      │ • YAML rules     │      │ • Python DAG     │
│ • Python scripts │      │ • Python checks  │      │ • Tests          │
│ • Tests          │      │ • Tests          │      │                  │
└────────┬─────────┘      └────────┬─────────┘      └────────┬─────────┘
         │                         │                         │
         │ Return artifacts        │ Return artifacts        │ Return artifacts
         │                         │                         │
         └─────────────────────────┼─────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MAIN CONVERSATION                                        │
│                                                                             │
│  1. Receive artifacts from sub-agents                                      │
│  2. Run test gates (pytest on returned files)                              │
│  3. If tests pass → Execute MCP operations                                 │
│  4. If tests fail → Re-spawn sub-agent with error context                  │
│                                                                             │
│  MCP Operations (main conversation only):                                  │
│  ├─> aws-dataprocessing.create_job()                                       │
│  ├─> s3-tables.create_table()                                              │
│  ├─> stepfunctions.create_state_machine()                                  │
│  └─> All other AWS deployments                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Test Gate Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      SUB-AGENT COMPLETES                                    │
│              Returns: scripts/ + tests/ + config.yaml                       │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
                        ┌──────────────────┐
                        │   TEST GATE      │
                        └──────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼                             ▼
          ┌──────────────────┐          ┌──────────────────┐
          │  UNIT TESTS      │          │ INTEGRATION TESTS│
          │                  │          │                  │
          │ • Test functions │          │ • Test scripts   │
          │ • Test configs   │          │ • Test SQL       │
          │ • Mock externals │          │ • Test pipelines │
          └────────┬─────────┘          └────────┬─────────┘
                   │                             │
                   └──────────────┬──────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
          ┌──────────────────┐        ┌──────────────────┐
          │  ALL PASS        │        │  ANY FAIL        │
          │  ✓               │        │  ✗               │
          └────────┬─────────┘        └────────┬─────────┘
                   │                           │
                   │                           ▼
                   │                  ┌──────────────────┐
                   │                  │  Retry Count < 2?│
                   │                  └────────┬─────────┘
                   │                           │
                   │              ┌────────────┴────────────┐
                   │              │                         │
                   │              ▼                         ▼
                   │    ┌──────────────────┐     ┌──────────────────┐
                   │    │  YES: Re-spawn   │     │  NO: Escalate to │
                   │    │  sub-agent with  │     │  human with full │
                   │    │  error context   │     │  error details   │
                   │    └──────────────────┘     └──────────────────┘
                   │
                   ▼
          ┌──────────────────┐
          │  PROCEED TO MCP  │
          │  DEPLOYMENT      │
          └──────────────────┘
```

---

## Complete Example: Multi-Dataset Integration

```
                        USER: "Set up e-commerce analytics"
                                        │
                                        ▼
        ┌───────────────────────────────────────────────────────────┐
        │                STEP 1: ROUTE                              │
        │  Check: customers, orders, products                       │
        │  Result: All NOT FOUND                                    │
        └───────────────────┬───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────────────────────────┐
        │            STEP 2: GENERATE (Test Data)                   │
        │  ├─> Generate 1000 customers   → s3://test/customers.csv │
        │  ├─> Generate 50 products      → s3://test/products.csv  │
        │  └─> Generate 5000 orders      → s3://test/orders.csv    │
        └───────────────────┬───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────────────────────────┐
        │           STEP 3: ONBOARD (Parallel)                      │
        │                                                           │
        │  ONBOARD customers &                                      │
        │  ONBOARD products &                                       │
        │  ONBOARD orders &                                         │
        │  wait                                                     │
        │                                                           │
        │  Each creates: Bronze → Silver → Gold                    │
        └───────────────────┬───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────────────────────────┐
        │             STEP 4: ENRICH (Relationships)                │
        │  ├─> Link orders.customer_id → customers.id              │
        │  └─> Link orders.product_id → products.id                │
        │                                                           │
        │  Stores in:                                               │
        │  • SageMaker Catalog (metadata)                          │
        │  • SynoDB (join semantics)                               │
        └───────────────────┬───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────────────────────────┐
        │           STEP 5: CONSUME (Dashboards)                    │
        │  ├─> Revenue by Customer Segment                         │
        │  ├─> Product Performance                                 │
        │  └─> Customer Lifetime Value                             │
        │                                                           │
        │  Queries Gold zone Iceberg tables via:                   │
        │  • Athena (for ad-hoc)                                   │
        │  • Redshift Spectrum (for dashboards)                    │
        └───────────────────┬───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────────────────────────┐
        │            STEP 6: GOVERN (Documentation)                 │
        │  ├─> Lineage: Source → Bronze → Silver → Gold → Dashboard│
        │  ├─> Audit: CloudTrail logs for all data access         │
        │  └─> Compliance: PII handling in customer data          │
        └───────────────────┬───────────────────────────────────────┘
                            │
                            ▼
                ┌──────────────────────────┐
                │    COMPLETE PLATFORM     │
                │                          │
                │ • 3 datasets onboarded   │
                │ • 2 relationships defined│
                │ • 3 dashboards created   │
                │ • Full lineage documented│
                └──────────────────────────┘
```

---

## Monitoring Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      MCP OPERATIONS DASHBOARD                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Active Workflows: 3                            Failed Operations: 0       │
│  Completed Today: 12                            Retry Count: 2             │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  Recent Operations:                                                         │
│                                                                             │
│  [10:23:45] ✓ aws-dataprocessing.create_crawler (customers_crawler)  2.3s │
│  [10:23:48] ✓ aws-dataprocessing.start_crawler (customers_crawler)   0.1s │
│  [10:24:05] ✓ aws-dataprocessing.start_query (profiling_query)      15.2s │
│  [10:24:22] ✓ sagemaker-catalog.put_metadata (customers_silver)      0.5s │
│  [10:24:25] ✓ s3-tables.create_table (customers_silver_iceberg)      1.8s │
│  [10:24:30] ✓ stepfunctions.create_state_machine (customers_dag)     0.9s │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  Quality Scores:                                                            │
│                                                                             │
│  customers_silver: 0.95 ████████████████████░  ✓ PASS                     │
│  products_silver:  0.88 █████████████████░░░  ✓ PASS                     │
│  orders_silver:    0.92 ██████████████████░░  ✓ PASS                     │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  Test Gates:                                                                │
│                                                                             │
│  Transformation Agent:   43/43 tests passing  ✓                           │
│  Quality Agent:          51/51 tests passing  ✓                           │
│  DAG Agent:              28/28 tests passing  ✓                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Legend

```
Symbols Used:
═══  Major workflow boundary
───  Sub-workflow boundary
│    Vertical flow
├─>  Branch/step
└─>  Final step
▼    Downward flow
✓    Success
✗    Failure
&    Parallel execution
&&   Sequential execution

Components:
╔════╗  Main conversation context (has MCP access)
┌────┐  Sub-agent context (no MCP access)
┏━━━━┓  Decision point
```

---

This visual guide shows exactly how prompts, agents, and MCP servers work together!
