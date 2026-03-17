# Demo & Testing Resources

This folder contains synthetic data generators and demo workflows for testing the data onboarding platform. **These are NOT used in production customer data onboarding.**

---

## Purpose

In production, customers provide real data sources (databases, APIs, S3 buckets, etc.). This demo folder exists solely for:
- Testing the platform without real customer data
- Demonstrations and walkthroughs
- Development and CI/CD pipelines

---

## Contents

### `data_generators/`
Synthetic data generation scripts that create fake datasets for testing:

- **`data_generator.py`** - Generates `customers.csv` (50 rows) and `orders.csv` (150 rows) with FK relationships
- **`generate_product_inventory.py`** - Generates `product_inventory.csv` with realistic quality issues
- **`bronze_data_generation.py`** - Generates mutual funds dataset (funds, market data, NAV prices) for AWS Glue

**Usage**:
```bash
# Generate customers and orders
python3 demo/data_generators/data_generator.py --customers 50 --orders 150 --seed 42

# Generate product inventory
python3 demo/data_generators/generate_product_inventory.py
```

### `sample_data/`
Pre-generated CSV files for quick testing:

- `customers.csv` (50 customers)
- `orders.csv` (150 orders linked to customers)
- `sales_transactions.csv` (50 sales records)
- `product_inventory.csv` (100 products)
- `customer_pii_test.csv` (PII detection test data)

### `workflows/`
Demo governance and workflow examples:

- **`demo_governance_workflow.py`** - Healthcare PII detection demo with Cedar policy enforcement

---

## How Production Works

In real customer onboarding:

1. **Discovery**: Data Onboarding Agent asks about the customer's data source
2. **Connection**: Agent connects to real source (PostgreSQL, S3, Snowflake, etc.)
3. **Profiling**: Agent scans a sample of real data using Glue Crawler
4. **Pipeline**: Agent generates ETL scripts that read from the real source
5. **Deployment**: Pipeline runs on schedule, pulling fresh data from customer source

**No synthetic data generation involved.**

---

## When to Use This Folder

- ✅ Running local tests (`pytest workloads/`)
- ✅ Demonstrating the platform to stakeholders
- ✅ CI/CD pipeline testing
- ✅ Learning how the system works

- ❌ Production customer data onboarding
- ❌ Real data pipelines

---

## Notes

- All data in this folder is **synthetic/fake** (randomly generated names, numbers)
- Sample CSVs are kept small (50-150 rows) for fast testing
- Real customer pipelines use AWS Glue/Athena to handle GB-TB scale data
- The data generators intentionally inject quality issues (nulls, duplicates) to test quality checks

---

**Folder Status**: For demo/testing only, not part of production data onboarding agent.
