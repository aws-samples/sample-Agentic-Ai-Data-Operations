# sales_transactions Workload

## Overview

This workload manages the ingestion, profiling, and transformation of daily sales transaction data from the e-commerce platform.

- **Domain:** Sales
- **Source Format:** CSV (comma-delimited, UTF-8)
- **Record Count:** 50 rows, 16 columns
- **Date Range:** 2024-06-01 to 2024-06-25
- **Classification:** Confidential (contains PII)

## Directory Structure

```
workloads/sales_transactions/
├── config/
│   ├── source.yaml          # Source connection, location, and schema
│   └── semantic.yaml        # Single source of truth: profiling + business context + PII
├── scripts/
│   ├── extract/              # Extraction scripts
│   ├── transform/            # Transformation scripts
│   ├── quality/              # Data quality check scripts
│   └── load/                 # Load scripts
├── dags/                     # Airflow DAG definitions
├── sql/
│   ├── bronze/               # Raw ingestion SQL
│   ├── silver/               # Cleaned/conformed SQL
│   └── gold/                 # Business-layer SQL
├── tests/
│   ├── unit/                 # Unit tests for metadata validation
│   └── integration/          # Integration tests against source data
└── README.md
```

## Key Columns

| Column | Type | Role | PII |
|--------|------|------|-----|
| order_id | string | Primary Key | No |
| customer_id | string | Foreign Key | Yes (identifier) |
| customer_name | string | Attribute | Yes (personal name) |
| email | string | Attribute | Yes (email address) |
| phone | string | Attribute | Yes (phone number) |
| order_date | date | Temporal | No |
| ship_date | date | Temporal | No |
| region | string | Dimension | No |
| product_category | string | Dimension | No |
| product_name | string | Dimension | No |
| quantity | integer | Measure | No |
| unit_price | double | Measure | No |
| discount_pct | double | Measure | No |
| revenue | double | Measure | No |
| payment_method | string | Dimension | No |
| status | string | Dimension | No |

## Data Quality Notes

- **email:** 3 null values (6.0%)
- **phone:** 1 null value (2.0%)
- **ship_date:** 7 null values (14.0%) -- all correspond to `status=pending`
- **order_id:** Confirmed unique (valid primary key)

## Running Tests

```bash
# Unit tests (metadata validation)
python -m pytest tests/unit/test_metadata.py -v

# Integration tests (CSV consistency)
python -m pytest tests/integration/test_metadata.py -v
```
