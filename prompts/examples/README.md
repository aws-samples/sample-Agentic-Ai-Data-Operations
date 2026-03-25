# Examples & Helpers

**Purpose**: Demo data generation and testing utilities (not part of core workflow)

## When to Use This Folder

- **Demos**: Creating realistic sample data for presentations or POCs
- **Testing**: Generating data with intentional quality issues to test pipelines
- **Development**: Building without access to production data sources

## Available Helpers

| File | Purpose | Time |
|------|---------|------|
| `generate-synthetic-data.md` | Template for creating synthetic datasets with FK relationships | 2-5 min |

## Why Separate from Core Workflow?

The core data onboarding workflow (`data-onboarding-agent/`) assumes you have a **real data source** (S3, database, API). Synthetic data generation is only needed when:

1. You don't have access to real data yet
2. You're building a demo for a conference/presentation
3. You're testing pipeline logic before connecting production systems

## Real-World Examples

For complete real-world onboarding examples (not synthetic data), see:
- [`../examples.md`](../examples.md) - Full prompts with semantic layer examples

## Quick Example

```bash
# Generate demo customer data
Generate synthetic data for demo_customers:
Rows: 200
Columns:
- customer_id: STRING - Format CUST-00001, unique
- company_name: STRING - Realistic B2B names
- segment: ENUM - Enterprise 15%, SMB 50%, Mid-Market 35%
- join_date: DATE - 2021-2024 range

Quality characteristics:
- 15% nulls in email (test null handling)
- 5% duplicate company_name (test dedup)
- 2% future dates (test validation)

Output:
- Generator: demo/sample_data/demo_customers_generator.py
- CSV: demo/sample_data/demo_customers.csv
- Seed: 12345 (reproducible)
```

Then onboard using the core workflow (`data-onboarding-agent/03-onboard-build-pipeline.md`).

## See Also

- [`examples.md`](../examples.md) - Real-world onboarding examples with full semantic layer
- [`data-onboarding-agent/README.md`](../data-onboarding-agent/README.md) - Core workflow prompts
