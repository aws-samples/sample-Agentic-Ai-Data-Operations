# Workloads Directory

This directory contains example data onboarding workloads demonstrating the platform capabilities.

---

## 🚀 Quick Start

Each workload is self-contained and can be run independently. To generate test data and run a workload:

```bash
# Example: Run product_inventory workload
cd workloads/product_inventory
python scripts/transform/bronze_to_silver.py --local
python scripts/transform/silver_to_gold.py --local

# Run tests
pytest tests/ -v
```

---

## 📦 Available Workloads

### 1. **sales_transactions** (Basic Example)
- **Purpose**: Simple e-commerce sales data
- **Zones**: Bronze → Silver → Gold
- **Test Status**: 196 tests
- **Features**: Basic transformations, quality checks
- **Input**: `sample_data/sales_transactions.csv`

```bash
cd workloads/sales_transactions
pytest tests/ -v
```

---

### 2. **customer_master** (Encryption Demo)
- **Purpose**: Customer master data with KMS encryption
- **Zones**: Landing → Staging → Publish (Bronze/Silver/Gold equivalent)
- **Test Status**: 211 tests
- **Features**: KMS encryption, PII masking, Iceberg tables
- **Input**: Auto-generated (50 synthetic customers)

```bash
cd workloads/customer_master
python scripts/extract/ingest_customers.py --local
python scripts/transform/bronze_to_gold.py --local
pytest tests/ -v
```

---

### 3. **order_transactions** (Star Schema)
- **Purpose**: Order data with star schema modeling
- **Zones**: Landing → Staging → Publish
- **Test Status**: 242 tests
- **Features**: FK relationships, star schema (fact + dimensions), Iceberg
- **Input**: Auto-generated (138 clean orders)

```bash
cd workloads/order_transactions
python scripts/extract/ingest_orders.py --local
python scripts/transform/bronze_to_gold.py --local
pytest tests/ -v
```

---

### 4. **product_inventory** (Quality Checks)
- **Purpose**: Product inventory with advanced quality rules
- **Zones**: Bronze → Silver → Gold
- **Test Status**: Configured
- **Features**: Data quality framework, quarantine handling
- **Input**: `sample_data/product_inventory.csv`

```bash
cd workloads/product_inventory
python sample_data/generate_product_inventory.py  # Generate test data
python scripts/transform/bronze_to_silver.py --local
pytest tests/ -v
```

---

### 5. **us_mutual_funds_etf** (Complete Pipeline)
- **Purpose**: Mutual funds data with full governance
- **Zones**: Bronze → Silver → Gold
- **Test Status**: Full suite (unit + integration)
- **Features**:
  - PII detection & Lake Formation tagging
  - QuickSight dashboards
  - Multi-table Gold zone
  - Complete DAG with all tasks
- **Input**: Auto-generated synthetic mutual funds data

```bash
cd workloads/us_mutual_funds_etf
python scripts/bronze/bronze_data_generation.py
python scripts/silver/silver_funds_clean.py --local
pytest tests/ -v
```

---

### 6. **healthcare_patients** (Governance Demo)
- **Purpose**: Healthcare data with HIPAA compliance
- **Zones**: Bronze → Silver → Gold
- **Features**: Cedar policy enforcement, PII detection for PHI
- **Input**: `sample_data/patients.csv`

```bash
cd workloads/healthcare_patients
python demo_governance_workflow.py
```

---

## 🏗️ Workload Structure

Each workload follows this structure:

```
workload_name/
├── config/                    # Configuration files
│   ├── source.yaml           # Source connection info
│   ├── semantic.yaml         # Business metadata
│   ├── transformations.yaml  # Transformation rules
│   ├── quality_rules.yaml    # Quality thresholds
│   └── schedule.yaml         # DAG schedule
├── scripts/                   # ETL scripts
│   ├── extract/              # Data extraction
│   ├── transform/            # Transformations
│   ├── quality/              # Quality checks
│   └── load/                 # Data loading
├── dags/                      # Airflow DAG definitions
├── sql/                       # SQL transformations
│   ├── bronze/
│   ├── silver/
│   └── gold/
├── tests/                     # Test suites
│   ├── unit/                 # Unit tests
│   └── integration/          # Integration tests
├── output/                    # Generated at runtime (gitignored)
│   ├── bronze/
│   ├── silver/
│   ├── gold/
│   ├── quarantine/
│   ├── quality/
│   └── lineage/
└── README.md                  # Workload-specific docs
```

---

## 📊 Test Data Generation

Test data is **NOT** included in the repository. Generate it by:

### Option 1: Auto-generate (Recommended)
```bash
# Generate synthetic data for a workload
cd workloads/customer_master
python scripts/extract/ingest_customers.py --generate --count 100
```

### Option 2: Use Sample Data
```bash
# Copy from sample_data/
cp sample_data/sales_transactions.csv workloads/sales_transactions/input/
```

### Option 3: Use Your Own Data
```bash
# Place your CSV in the workload input directory
cp /path/to/your/data.csv workloads/my_workload/input/
```

---

## 🧪 Running Tests

### Run All Tests
```bash
# From repository root
pytest workloads/ -v
```

### Run Specific Workload Tests
```bash
# Unit tests only
pytest workloads/sales_transactions/tests/unit/ -v

# Integration tests only
pytest workloads/sales_transactions/tests/integration/ -v

# Specific test file
pytest workloads/sales_transactions/tests/unit/test_transform.py -v
```

### Run with Coverage
```bash
pytest workloads/ --cov=workloads --cov-report=html
open htmlcov/index.html
```

---

## 🔒 Output Directories (Runtime Only)

The following directories are created at runtime and **gitignored**:

```
workload_name/output/
├── bronze/          # Raw data (immutable)
├── silver/          # Cleaned data (Iceberg)
├── gold/            # Curated data (Iceberg/star schema)
├── quarantine/      # Failed quality checks
├── quality/         # Quality reports (JSON)
└── lineage/         # Data lineage (JSON)
```

**These directories are empty in the repository.** They are populated when you run the pipeline locally or in AWS.

---

## 🌐 Running in AWS

To deploy and run a workload in AWS:

```bash
# 1. Upload scripts to S3
aws s3 sync workloads/sales_transactions/ s3://your-bucket/workloads/sales_transactions/

# 2. Register Glue tables
python workloads/sales_transactions/glue/register_tables.py

# 3. Upload DAG to MWAA
aws s3 cp workloads/sales_transactions/dags/sales_transactions_dag.py \
  s3://your-mwaa-bucket/dags/

# 4. Trigger DAG in Airflow UI
open https://your-mwaa-environment.console.aws.amazon.com
```

See `docs/aws-account-setup.md` for detailed AWS configuration.

---

## 📚 Documentation

| File | Description |
|------|-------------|
| `CLAUDE.md` | Agent configuration & rules |
| `SKILLS.md` | Agent skill definitions |
| `TOOLS.md` | AWS service mapping |
| `docs/getting-started.md` | Quick start guide |
| `docs/aws-account-setup.md` | AWS prerequisites |

---

## 🆘 Troubleshooting

### "No output directory found"
This is expected! Output directories are created at runtime. Run the pipeline first:
```bash
python scripts/transform/bronze_to_silver.py --local
```

### "Input file not found"
Generate test data first:
```bash
python scripts/extract/ingest_customers.py --generate
```

### "Tests failing"
Make sure to run the pipeline before tests (integration tests expect output):
```bash
python scripts/transform/bronze_to_silver.py --local
pytest tests/integration/ -v
```

---

## 🤝 Contributing

To add a new workload:

1. Copy an existing workload structure
2. Update `config/` files with your source/schema
3. Write transformation scripts in `scripts/`
4. Add tests in `tests/`
5. Document in the workload's `README.md`
6. Submit a pull request

See `CONTRIBUTING.md` (to be created) for detailed guidelines.

---

**Note**: This is a demonstration platform. Output data is generated at runtime and not committed to Git.
