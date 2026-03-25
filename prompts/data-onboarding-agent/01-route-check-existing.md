# 01 — ROUTE: Check Existing Source
> Always run first to prevent duplicate onboarding.

## Purpose

Before starting any new onboarding, check if the data source has already been onboarded in an existing workload. This prevents duplicate pipelines and wasted effort.

## When to Use

- **Always** before running ONBOARD (03)
- When a user asks about a new data source
- When you are unsure if a dataset already exists in the system

## Prompt Template

```
Check if data from [SOURCE_DESCRIPTION] has already been onboarded.

Source details:
- Location: [S3_PATH or DATABASE.TABLE]
- Format: [CSV/JSON/Parquet]
- Description: [What this data represents]

Report: existing workload status or confirm new data.
```

## Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `SOURCE_DESCRIPTION` | Plain-English description of the data | "customer master records" |
| `S3_PATH or DATABASE.TABLE` | Where the source data lives | `s3://prod-data-lake/raw/crm/customers.csv` |
| `CSV/JSON/Parquet` | Source file format | CSV |
| `What this data represents` | Business context for matching | "Customer demographic data including contact info and account status" |

## Expected Output

One of three outcomes:

1. **Found**: Points to `workloads/{name}/` and summarizes what is there (source, zones populated, DAG schedule). Asks what you want to do with it.
2. **Not found**: Confirms this is new data. Proceed to ONBOARD (03).
3. **Partial match**: Reports what exists and what is missing. Asks if you want to complete the pipeline or start over.

## How It Works

The Router Agent searches:
- `workloads/` folder names
- `workloads/*/config/source.yaml` for location/format matches
- `workloads/*/README.md` for description matches
