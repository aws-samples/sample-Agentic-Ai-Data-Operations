# Agentic Data Onboarding Platform

A multi-agent data pipeline platform that autonomously onboards datasets through **Bronze → Silver → Gold** zones using AI-driven orchestration and AWS services.

---

## How It Works

A user describes their data source in natural language. The **Data Onboarding Agent** coordinates specialized sub-agents to generate a complete, tested pipeline — config files, transformation scripts, quality checks, and an Airflow DAG — without writing any code manually.

```
User: "Onboard customer data from PostgreSQL, daily refresh, PII masking required"

   ┌─────────────────────────────────────────────────────────┐
   │  Data Onboarding Agent (orchestrator)                   │
   │                                                         │
   │  Phase 1: Discovery ─── asks source, schema, rules      │
   │  Phase 2: Dedup ─────── checks existing workloads       │
   │  Phase 3: Profile ───── samples data, detects PII       │
   │  Phase 4: Build ─────── spawns sub-agents:               │
   │     ├── Metadata Agent ──────→ config/ + catalog         │
   │     ├── Transformation Agent → scripts/ + sql/           │
   │     ├── Quality Agent ───────→ quality rules + gates     │
   │     └── DAG Agent ───────────→ dags/ + schedule          │
   │                                                         │
   │  Each sub-agent writes tests → must pass before next     │
   └─────────────────────────────────────────────────────────┘

Output: workloads/{dataset_name}/   (ready to deploy to MWAA)
```

---

## Architecture

### Data Zones (Medallion Pattern)

| Zone | Purpose | Format | Quality Gate |
|------|---------|--------|--------------|
| **Bronze** | Raw, immutable ingestion | Source format (CSV, JSON, Parquet) | None |
| **Silver** | Cleaned, validated, schema-enforced | Apache Iceberg on S3 Tables | Score >= 80% |
| **Gold** | Curated, business-ready | Iceberg (star schema or flat) | Score >= 95% |

### Agent Architecture

| Agent | Role | Runs In |
|-------|------|---------|
| **Router** | Checks if data already onboarded | Main conversation (inline) |
| **Data Onboarding** | Orchestrates all phases, human-facing | Main conversation |
| **Metadata** | Profiles data, generates config, catalogs schema | Sub-agent |
| **Transformation** | Generates PySpark scripts for Bronze→Silver→Gold | Sub-agent |
| **Quality** | Defines quality rules, implements gates | Sub-agent |
| **DAG** | Generates Airflow DAG with scheduling | Sub-agent |
| **Analysis** | Derives SQL from natural language using semantic layer | Sub-agent |

Sub-agents do NOT execute AWS operations — they generate artifacts and tests only. AWS execution happens via MCP servers in the main conversation during deployment.

### AWS Services

| Service | Purpose |
|---------|---------|
| S3 + S3 Tables | Data lake storage (Bronze/Silver/Gold zones) |
| AWS Glue | ETL jobs, crawlers, Data Catalog |
| Amazon Athena | SQL queries on Iceberg tables |
| Apache Iceberg | Table format (ACID, time-travel, schema evolution) |
| AWS KMS | Encryption at rest (zone-specific keys) |
| Lake Formation | Column-level security via LF-Tags |
| Amazon MWAA | Airflow orchestration |
| SageMaker Catalog | Business metadata (custom columns) |

---

## Project Structure

```
.
├── workloads/                        # Onboarded datasets (one folder per dataset)
│   ├── sales_transactions/           # Example: e-commerce sales
│   ├── customer_master/              # Example: customer data with KMS + PII
│   ├── order_transactions/           # Example: orders with star schema + FK
│   ├── product_inventory/            # Example: inventory with quality checks
│   ├── us_mutual_funds_etf/          # Example: mutual funds (most complete)
│   └── healthcare_patients/          # Example: HIPAA governance demo
│
├── shared/                           # Reusable code across workloads
│   ├── utils/                        # pii_detection, quality_checks, encryption
│   ├── policies/                     # Cedar policies (guardrails + authorization)
│   ├── mcp/                          # MCP orchestrator + custom servers
│   ├── fixtures/                     # Shared test fixtures (CSV stubs)
│   └── templates/                    # Templates for new workloads
│
├── demo/                             # Demo/testing resources (not production)
│   ├── data_generators/              # Synthetic data scripts
│   ├── sample_data/                  # Pre-generated CSV files
│   ├── orchestrator_examples/        # Multi-workload DAG examples
│   └── workflows/                    # Demo governance workflows
│
├── docs/                             # Setup guides and architecture docs
├── prompts/                          # Reusable prompt patterns (ROUTE → ONBOARD → ENRICH → CONSUME → GOVERN)
│
├── CLAUDE.md                         # Agent configuration and conventions
├── SKILLS.md                         # Agent skill definitions and prompts
├── TOOLS.md                          # AWS service mapping per agent phase
├── MCP_GUARDRAILS.md                 # MCP tool selection rules
├── WORKFLOW.md                       # Visual workflow diagrams
├── MCP_SETUP.md                      # MCP server configuration guide
├── SECURITY.md                       # Security practices and sanitization
├── RUNNING_TESTS.md                  # Test execution guide (649 tests)
├── conftest.py                       # Pytest configuration
└── pyproject.toml                    # Python project config
```

### Workload Structure (generated per dataset)

```
workloads/{dataset_name}/
├── config/
│   ├── source.yaml                   # Connection details, format, frequency
│   ├── semantic.yaml                 # Column roles, business context, PII flags
│   ├── transformations.yaml          # Cleaning rules, Gold zone schema
│   ├── quality_rules.yaml            # Thresholds, critical rules
│   └── schedule.yaml                 # Cron, dependencies, failure handling
├── scripts/
│   ├── extract/                      # Ingestion from source to Bronze
│   ├── transform/                    # Bronze→Silver→Gold (PySpark + local mode)
│   ├── quality/                      # Quality check execution
│   └── load/                         # Catalog registration
├── dags/
│   └── {dataset_name}_dag.py         # Airflow DAG (independent per workload)
├── sql/
│   ├── bronze/                       # DDL for raw tables
│   ├── silver/                       # DDL for cleaned tables
│   └── gold/                         # DDL for curated tables
├── tests/
│   ├── unit/                         # Self-contained tests (no dependencies)
│   └── integration/                  # Tests requiring pipeline output
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.9+
- AWS account with Glue, Athena, S3, MWAA configured
- Claude Code CLI

### Run Tests Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run all 649 tests (no AWS required)
pytest workloads/ -v

# Run specific workload
pytest workloads/sales_transactions/tests/ -v

# Unit tests only (no prerequisites)
pytest workloads/*/tests/unit/ -v
```

See [RUNNING_TESTS.md](RUNNING_TESTS.md) for complete test guide including data generation.

### Onboard a New Dataset

Using Claude Code, describe your data source:

```
"Onboard customer_orders from our PostgreSQL database.
 Daily refresh at 6 AM UTC. Contains PII (email, phone).
 Need star schema in Gold zone for reporting dashboards."
```

The agent will:
1. Ask clarifying questions (schema, cleaning rules, quality thresholds)
2. Check for duplicate sources in existing workloads
3. Profile a sample of your data
4. Generate all pipeline artifacts with tests
5. Present artifacts for your approval before writing

### Deploy to AWS

```bash
# Upload workload to MWAA S3 bucket
aws s3 sync workloads/{dataset}/ s3://{mwaa-bucket}/dags/workloads/{dataset}/
aws s3 sync shared/ s3://{mwaa-bucket}/dags/shared/

# The workload's DAG will appear in MWAA Airflow UI
```

See [docs/aws-account-setup.md](docs/aws-account-setup.md) for AWS configuration details.

---

## Key Features

### PII Detection and Governance
- AI-driven detection of 12 PII types (EMAIL, PHONE, SSN, CREDIT_CARD, etc.)
- Lake Formation LF-Tags for column-level access control
- 4 sensitivity levels: CRITICAL, HIGH, MEDIUM, LOW
- Integrated into profiling phase — runs automatically on every dataset

### Quality Gates
- 5 dimensions: Completeness, Accuracy, Consistency, Validity, Uniqueness
- Critical rule failures block zone promotion regardless of overall score
- Anomaly detection for outliers, distribution shifts, volume changes
- Historical comparison against baseline

### Cedar Policy Guardrails
- 16 forbid policies preventing unsafe operations (e.g., Bronze mutation, quality bypass)
- 7 agent authorization policies controlling which agent can do what
- Dual-mode: local evaluation (cedarpy) or AWS Verified Permissions

### Test-Driven Pipeline Generation
- Every sub-agent writes unit + integration tests alongside artifacts
- Tests must pass before the orchestrator proceeds (max 2 retries)
- 649 tests across 6 workloads, all runnable locally without AWS

---

## Example Workloads

| Workload | Tests | Key Features |
|----------|-------|-------------|
| `sales_transactions` | 196 | Basic Bronze→Silver→Gold, quality checks |
| `customer_master` | 211 | KMS encryption, PII masking, Iceberg tables |
| `order_transactions` | 242 | FK validation, star schema, aggregate calculations |
| `product_inventory` | — | Advanced quality rules, quarantine handling |
| `us_mutual_funds_etf` | Full suite | PII detection, QuickSight dashboards, complete DAG |
| `healthcare_patients` | — | HIPAA compliance, Cedar policy enforcement |

---

## Documentation

| Document | Purpose |
|----------|---------|
| [CLAUDE.md](CLAUDE.md) | Agent configuration, security rules, data zone rules |
| [SKILLS.md](SKILLS.md) | Agent skill definitions, spawn prompts, workflows |
| [TOOLS.md](TOOLS.md) | AWS service mapping per pipeline phase |
| [MCP_GUARDRAILS.md](MCP_GUARDRAILS.md) | MCP tool selection rules per phase |
| [WORKFLOW.md](WORKFLOW.md) | Visual workflow and data flow diagrams |
| [MCP_SETUP.md](MCP_SETUP.md) | MCP server configuration |
| [SECURITY.md](SECURITY.md) | Security practices |
| [RUNNING_TESTS.md](RUNNING_TESTS.md) | Test execution guide |
| [docs/aws-account-setup.md](docs/aws-account-setup.md) | AWS prerequisites |
| [docs/getting-started.md](docs/getting-started.md) | Quick start guide |

---

## Technology Stack

- **Language**: Python (Glue PySpark + Airflow DAGs)
- **Table Format**: Apache Iceberg (ACID, time-travel, schema evolution)
- **Orchestration**: Apache Airflow (MWAA)
- **Cloud**: AWS (S3, Glue, Athena, Lake Formation, KMS, MWAA)
- **Testing**: pytest (unit + integration, property-based with fast-check)
- **Policy Engine**: Cedar (via Amazon Verified Permissions)
- **AI Integration**: MCP (Model Context Protocol) for standardized AWS access

---

## License

MIT License - See [LICENSE](LICENSE) for details.
