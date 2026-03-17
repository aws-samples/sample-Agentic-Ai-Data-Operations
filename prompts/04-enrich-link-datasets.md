# 04 — ENRICH: Link Datasets via FK
> Add relationships and join semantics between existing workloads.

## Purpose

After two or more datasets are onboarded, use ENRICH to document foreign key relationships and teach the Analysis Agent how and when to join them.

## When to Use

- After both source and target workloads exist (ONBOARD complete for both)
- When datasets share a common key (e.g., customer_id)
- To enable cross-dataset queries in the Analysis Agent

## Prompt Template

```
Add relationship between workloads:

Source: [SOURCE_WORKLOAD]
Target: [TARGET_WORKLOAD]

Relationship:
- FK: [SOURCE_TABLE.COL] -> [TARGET_TABLE.COL]
- Cardinality: [one-to-many/many-to-one]
- Description: [Business meaning]

Integrity:
- Expected validity: [PERCENTAGE]%
- Orphan handling: [QUARANTINE/DROP/KEEP]
- Nullable FK: [YES/NO - what does NULL mean?]

Join semantics for Analysis Agent:
- When to join: [What questions require this join?]
- When NOT to join: [What questions don't need it?]
- Pre-aggregation: [Aggregate before or after joining?]
- Fan-out warning: [Does join multiply rows? How to handle?]
- Columns available after join: [What new columns become queryable?]
- Sample joined queries:
  1. "[NL question]" -> [SQL pattern]
  2. "[NL question]" -> [SQL pattern]
  3. "[NL question]" -> [SQL pattern]

Update:
1. Add relationships section to [SOURCE_WORKLOAD]/config/semantic.yaml
2. Add joined seed queries to seed_questions section (tag with joins: [TARGET_WORKLOAD])
3. Create relationship tests: test_relationships.py (FK documented, cardinality, join semantics, fan-out warnings, sample queries)
4. Update README.md with relationship documentation
5. If not already done: add FK validation to bronze_to_silver.py, ExternalTaskSensor to DAG

Validate: All existing tests still pass + new relationship tests pass.
```

## Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `SOURCE_WORKLOAD` | Workload containing the FK column | `order_transactions` |
| `TARGET_WORKLOAD` | Workload containing the PK being referenced | `customer_master` |
| `SOURCE_TABLE.COL` | FK column in source | `order_transactions.customer_id` |
| `TARGET_TABLE.COL` | PK column in target | `customer_master.customer_id` |
| `Cardinality` | Relationship type | many-to-one (many orders per customer) |
| `Expected validity` | % of FK values that should match | 98% |
| `Orphan handling` | What to do with unmatched FKs | QUARANTINE |
| `When to join` | Questions that need both tables | "Revenue by customer segment" |
| `When NOT to join` | Questions that only need one table | "Total revenue by category" |
| `Pre-aggregation` | Aggregate before or after join | "Aggregate orders first, then join for segment" |
| `Fan-out warning` | Join multiplication risk | "1:many - never SUM customer fields after join" |

## Expected Output

1. Updated `semantic.yaml` with relationships and join semantics
2. Updated seed_questions with cross-table query examples
3. New `test_relationships.py` with FK, cardinality, and join semantics tests
4. Updated README.md documenting the relationship
5. FK validation in transformation scripts (if not already present)
6. ExternalTaskSensor in DAG (if not already present)
7. All existing tests still pass + new relationship tests pass
