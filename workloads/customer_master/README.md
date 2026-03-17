# Customer Master Pipeline

**Owner**: CRM Team / Sales
**Schedule**: Daily at 06:00 UTC
**Status**: Active

## Overview

Customer master data pipeline: Bronze (raw CSV) to Gold (star schema).
Source: CRM system customer export (52 rows, 11 columns).

## Data Flow

```
shared/fixtures/customers.csv
  |
  v
Bronze Zone (S3, raw CSV, immutable)
  |  Dedup on customer_id (2 duplicates removed)
  |  PII masking: email -> SHA-256, phone -> mask last 4
  |  Enum validation: segment, status, country
  |  Type casting: annual_value, credit_limit -> decimal
  v
Gold Zone (S3, star schema CSV, registered in Glue)
  - customer_fact (50 rows)
  - dim_segment (3 rows: Enterprise, SMB, Individual)
  - dim_country (4 rows: US, UK, CA, DE)
  - dim_status (3 rows: Active, Inactive, Churned)
  - customer_summary_by_segment (3 rows)
```

## AWS Resources

- **S3 Bronze**: `s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/bronze/customers/`
- **S3 Gold**: `s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/customers/`
- **Glue Bronze DB**: `demo_database_ai_agents_bronze` (table: `customers`)
- **Glue Gold DB**: `demo_database_ai_agents_goldzone` (tables: `customer_fact`, `dim_segment`, `dim_country`, `dim_status`, `customer_summary_by_segment`)

## Quality Gates

- **Bronze**: score >= 0.80, no critical failures
- **Gold**: score >= 0.95, no critical failures, PII verified masked

## Running Locally

```bash
# Run transformation (no S3 upload)
python3 workloads/customer_master/scripts/transform/bronze_to_gold.py

# Run quality checks
python3 workloads/customer_master/scripts/quality/check_bronze.py
python3 workloads/customer_master/scripts/quality/check_gold.py

# Run tests
python3 -m pytest workloads/customer_master/tests/ -v

# Register Glue tables
python3 workloads/customer_master/glue/register_tables.py
```
