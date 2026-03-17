# 02 — GENERATE: Create Synthetic Data
> Use for demos, testing, and development when real data isn't available.

## Purpose

Generate realistic synthetic datasets with intentional quality issues for testing pipelines end-to-end. Supports foreign key relationships between datasets.

## When to Use

- Demo/conference preparation
- Testing pipeline logic before connecting real data
- Development when production data access is restricted
- Generating related datasets with FK relationships

## Prompt Template

```
Generate synthetic data for [DATASET_NAME]:

Rows: [NUMBER]
Columns:
- [COL1]: [TYPE] - [DESCRIPTION] - [CONSTRAINTS]
- [COL2]: [TYPE] - [DESCRIPTION] - [CONSTRAINTS]

Quality characteristics:
- [X]% nulls in [COLUMNS]
- [X]% duplicates on [KEY_COLUMN]

Foreign keys (if applicable):
- [TABLE1.COL] -> [TABLE2.COL], [CARDINALITY]
- Orphan FK rate: [X]% (intentional orphans for FK validation testing)
- Future dates: [X]% (intentional for date validation testing)

Output:
- Generator script: shared/fixtures/data_generator.py (with --seed for reproducibility)
- CSV files: shared/fixtures/[dataset].csv
- Simulated S3: Copy to /tmp/data-lake/landing/[dataset]/
- Tests for FK integrity, distributions, reproducibility
```

## Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `DATASET_NAME` | Name for the synthetic dataset | `demo_customer_master` |
| `NUMBER` | Row count | 200 |
| `COL*` | Column name | `customer_id` |
| `TYPE` | Data type | STRING, INTEGER, DECIMAL, DATE, ENUM |
| `DESCRIPTION` | What the column represents | "Unique customer identifier" |
| `CONSTRAINTS` | Format, distribution, range | "Format CUST-00001, unique" |
| `X% nulls` | Intentional null rate for quality testing | "15% nulls in email" |
| `X% duplicates` | Intentional duplicate rate | "3% duplicates on order_id" |
| `Orphan FK rate` | Intentional orphan FK percentage | "5% orphans for FK validation" |
| `Future dates` | Intentional future date percentage | "2% for date validation testing" |

## Expected Output

- Generator script at `shared/fixtures/[dataset]_generator.py`
- CSV file at `shared/fixtures/[dataset].csv`
- Copy to simulated S3 at `/tmp/data-lake/landing/[dataset]/`
- Unit tests validating distributions, null rates, FK integrity, reproducibility
- CLI command with `--seed` for reproducible generation
