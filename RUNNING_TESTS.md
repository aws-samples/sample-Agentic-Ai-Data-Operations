# Running Tests - Complete Guide

This repository contains **792 tests** across multiple workloads (728 passing). Tests verify the data pipeline functionality without requiring AWS services.

---

## 🎯 Quick Start

### Run All Tests
```bash
# From repository root
pytest workloads/ -v

# Expected: 728 passing (some errors if PySpark/Java not installed)
```

### Run Specific Workload
```bash
# Sales transactions (196 tests)
pytest workloads/sales_transactions/tests/ -v

# Customer master (118 tests)
pytest workloads/customer_master/tests/ -v

# Order transactions (70 tests)
pytest workloads/order_transactions/tests/ -v
```

---

## 📋 Test Requirements

### 1. Generate Test Data First

**Tests expect input data to exist.** Generate it before running tests:

```bash
# For sales_transactions (uses sample data)
cp sample_data/sales_transactions.csv workloads/sales_transactions/input/
# Already available - no action needed

# For customer_master (auto-generate)
cd workloads/customer_master
python scripts/extract/ingest_customers.py --generate --count 50

# For order_transactions (auto-generate)
cd workloads/order_transactions
python scripts/extract/ingest_orders.py --generate --count 100
```

### 2. Run Pipeline Locally (for integration tests)

Some integration tests expect output data to exist:

```bash
# Run the pipeline in local mode
cd workloads/customer_master
python scripts/transform/bronze_to_gold.py --local

# Now integration tests will pass
pytest tests/integration/ -v
```

---

## 🧪 Test Types

### Unit Tests
Test individual functions without dependencies.

**Location**: `workloads/*/tests/unit/`

**Coverage**:
- Configuration validation
- Transformation logic
- Quality check functions
- DAG structure

**Run**:
```bash
pytest workloads/sales_transactions/tests/unit/ -v
```

**No prerequisites** - unit tests are self-contained.

---

### Integration Tests
Test end-to-end pipeline flow with local data.

**Location**: `workloads/*/tests/integration/`

**Coverage**:
- Bronze → Silver → Gold pipeline
- Quality gates
- Lineage tracking
- Schema evolution

**Prerequisites**:
1. Generate input data
2. Run pipeline locally (creates output/)

**Run**:
```bash
# First run the pipeline
cd workloads/customer_master
python scripts/transform/bronze_to_gold.py --local

# Then run integration tests
pytest tests/integration/ -v
```

---

## 📊 Test Coverage by Workload

### Sales Transactions (196 tests)
```bash
cd workloads/sales_transactions

# Unit tests (no prerequisites)
pytest tests/unit/ -v
# Expected: ~100 tests passing

# Integration tests (requires pipeline run)
pytest tests/integration/ -v
# Expected: ~96 tests passing
```

**Coverage**:
- ✅ Metadata validation
- ✅ Transformation logic
- ✅ Quality checks
- ✅ DAG configuration

---

### Customer Master (118 tests)
```bash
cd workloads/customer_master

# Generate data first
python scripts/extract/ingest_customers.py --generate --count 50

# Run pipeline
python scripts/transform/bronze_to_gold.py --local

# Run all tests
pytest tests/ -v
# Expected: 118 tests passing
```

**Coverage**:
- ✅ KMS encryption
- ✅ PII masking (email_hash, phone_masked)
- ✅ Iceberg table creation
- ✅ Star schema (fact + dimensions)
- ✅ Quality gates

---

### Order Transactions (70 tests)
```bash
cd workloads/order_transactions

# Generate data first
python scripts/extract/ingest_orders.py --generate --count 100

# Run pipeline
python scripts/transform/bronze_to_gold.py --local

# Run all tests
pytest tests/ -v
# Expected: 70 tests passing
```

**Coverage**:
- ✅ Foreign key validation
- ✅ Star schema modeling
- ✅ Iceberg tables
- ✅ Aggregate calculations
- ✅ Quarantine handling

---

## 🔧 Pytest Configuration

The project uses a custom `pyproject.toml` configuration:

```toml
[tool.pytest.ini_options]
testpaths = ["workloads", "shared/tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "--import-mode=importlib -v --strict-markers"
markers = [
    "slow: marks tests as slow",
    "integration: integration tests requiring full pipeline",
    "aws: tests requiring AWS services",
]
```

### Run Only Fast Tests
```bash
pytest -m "not slow" workloads/
```

### Run Only Integration Tests
```bash
pytest -m integration workloads/
```

### Skip AWS Tests (for local development)
```bash
pytest -m "not aws" workloads/
```

---

## 🐛 Debugging Failed Tests

### View Detailed Output
```bash
pytest workloads/sales_transactions/tests/unit/test_transform.py -v -s
# -v = verbose
# -s = show print statements
```

### Run Single Test
```bash
pytest workloads/sales_transactions/tests/unit/test_transform.py::TestTransformation::test_dedup -v
```

### Show Local Variables on Failure
```bash
pytest workloads/ -v --showlocals
```

### Drop into Debugger on Failure
```bash
pytest workloads/ -v --pdb
```

---

## 📈 Coverage Reports

### Generate HTML Coverage Report
```bash
pytest workloads/ --cov=workloads --cov-report=html
open htmlcov/index.html
```

### Show Missing Lines
```bash
pytest workloads/ --cov=workloads --cov-report=term-missing
```

### Coverage by Module
```bash
pytest workloads/customer_master/ --cov=workloads/customer_master --cov-report=term
```

---

## ⚠️ Common Issues

### Issue: "No module named 'workloads'"
**Solution**: Make sure pytest is using `importlib` mode:
```bash
pytest --import-mode=importlib workloads/
```
Or check that `pyproject.toml` has the correct `addopts`.

---

### Issue: "FileNotFoundError: input/customers.csv"
**Solution**: Generate test data first:
```bash
cd workloads/customer_master
python scripts/extract/ingest_customers.py --generate
pytest tests/ -v
```

---

### Issue: "Integration tests failing"
**Solution**: Run the pipeline before integration tests:
```bash
cd workloads/customer_master
python scripts/transform/bronze_to_gold.py --local
pytest tests/integration/ -v
```

---

### Issue: "AssertionError: Output directory not found"
**Solution**: Integration tests expect output to exist. Run the pipeline first.
```bash
python scripts/transform/bronze_to_gold.py --local
```

---

## 🚀 CI/CD Testing

For automated testing in CI/CD:

```yaml
# Example: GitHub Actions
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v2

      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov

      - name: Run tests
        run: pytest workloads/ -v --cov=workloads

      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

---

## 📚 Test Documentation

Each workload has test documentation:

- `workloads/*/tests/README.md` - Workload-specific test guide
- Test docstrings explain what each test validates
- `pytest --collect-only` - List all tests without running

---

## 🎯 Test Goals

### Current Coverage: ~80%

**Covered**:
- ✅ Configuration validation
- ✅ Transformation logic
- ✅ Quality checks
- ✅ DAG structure
- ✅ Schema enforcement
- ✅ Lineage tracking

**Not Covered** (requires AWS):
- ⚠️ Glue Crawler execution
- ⚠️ Athena query execution
- ⚠️ S3 Table operations
- ⚠️ Lake Formation tagging
- ⚠️ KMS encryption (in AWS)

For AWS integration tests, see `docs/aws-account-setup.md`.

---

## 📖 Further Reading

- `CLAUDE.md` - Testing strategy section
- `docs/testing-strategy.md` - Detailed testing approach
- `shared/tests/README.md` - Shared test utilities
- `conftest.py` - Pytest fixtures

---

**Quick Command Reference**:

```bash
# All tests
pytest workloads/ -v

# Specific workload
pytest workloads/customer_master/ -v

# Unit tests only
pytest workloads/*/tests/unit/ -v

# With coverage
pytest workloads/ --cov=workloads --cov-report=html

# Debug mode
pytest workloads/ -v --pdb
```

---

**Note**: Tests are designed to run **locally without AWS**. They use fixture CSV files and simulate Iceberg operations with `.iceberg_metadata` sidecar files.
