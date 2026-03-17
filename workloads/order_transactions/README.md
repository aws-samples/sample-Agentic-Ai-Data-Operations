# Order Transactions Workload

## Overview
Sales order transactions pipeline: Bronze (raw CSV) to Gold (star schema) with FK validation against customer_master.

## Source
- File: `shared/fixtures/orders.csv` (157 rows, 11 columns)
- Primary key: `order_id`
- Foreign key: `customer_id` -> `customer_master.customer_id`

## Zones

### Bronze
- Raw CSV uploaded to S3
- Glue table: `demo_database_ai_agents_bronze.orders`
- Immutable - never modified

### Gold (Star Schema)
- **order_fact**: One row per clean order (deduped, FK-validated, no future dates)
- **dim_product**: Product name + category
- **dim_region**: East, West, Central, South
- **dim_status**: Completed, Pending, Cancelled
- **order_summary**: Pre-aggregated metrics by region + category
- Database: `demo_database_ai_agents_goldzone`

## Transformations
1. Dedup on order_id (keep first) - removes 7 duplicates
2. Quarantine null PKs
3. FK validation: customer_id must exist in customer_master (5 orphans quarantined)
4. Future date quarantine: order_date > today (~8 orders)
5. Revenue validation: |revenue - qty*price*(1-disc)| <= 0.01
6. Enum validation: category, status, region

## Quality Gates
- Bronze: Informational (detects issues, no blocking)
- Gold: Score >= 0.95, no critical failures required

## Schedule
- Daily at 07:00 UTC
- Depends on: customer_master_pipeline (ExternalTaskSensor)

## Analytical Queries
See `sql/gold/top_10_queries.sql` for 10 Sales & Marketing queries including cross-workload JOINs to customer_master.

## Running Tests
```bash
cd /path/to/claude-data-operations
python3 -m pytest workloads/order_transactions/tests/ -v
```
