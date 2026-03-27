# Data Analysis Agent: Execute Natural Language Query on Neptune (LIVE)

**Agent**: Data Analysis Agent
**Purpose**: Execute natural language queries against Neptune semantic layer (LIVE EXECUTION)
**Prerequisites**: Neptune cluster running, semantic layer loaded
**Run in**: Development environment

---

## Quick Start: Run a Query Now

### Step 1: Verify Neptune Connection

```bash
# Check Neptune cluster status
aws neptune describe-db-clusters \
  --region us-east-1 \
  --query 'DBClusters[*].[DBClusterIdentifier,Endpoint,Status]' \
  --output table

# Expected output:
# semantic-layer-cluster | semantic-layer-cluster.cluster-xxx.us-east-1.neptune.amazonaws.com | available
```

### Step 2: Test Query Execution

```python
#!/usr/bin/env python3
"""
Quick test: Execute NL query on Neptune
"""
from shared.semantic_layer import execute_nl_query

# Neptune endpoint (replace with your actual endpoint)
NEPTUNE_ENDPOINT = "semantic-layer-cluster.cluster-cxpwlkutkebk.us-east-1.neptune.amazonaws.com"

# Your natural language question
nl_query = "What is the total portfolio value?"

print(f"Query: {nl_query}")
print("Executing...")

try:
    gen_result, exec_result = execute_nl_query(
        nl_query=nl_query,
        workload="financial_portfolios",
        database="financial_portfolios_db",
        neptune_endpoint=NEPTUNE_ENDPOINT,
        athena_database="financial_portfolios_db",
        s3_output_location="s3://your-bucket/athena-results/",  # Replace with your S3 bucket
        region="us-east-1",
        max_results=100
    )

    # Show SQL
    print(f"\n✓ Generated SQL:")
    print("-" * 80)
    print(gen_result.sql)
    print("-" * 80)

    # Show results
    if exec_result.status == 'success':
        print(f"\n✓ Execution: {exec_result.status}")
        print(f"  Rows: {exec_result.row_count}")
        print(f"  Time: {exec_result.execution_time_ms}ms")
        print(f"\nResults:")
        for row in exec_result.rows:
            print(f"  {row}")
    else:
        print(f"\n✗ Execution failed: {exec_result.error}")

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
```

---

## Test Queries (Copy-Paste Ready)

### Query 1: Simple Aggregation

```python
from shared.semantic_layer import execute_nl_query

NEPTUNE_ENDPOINT = "semantic-layer-cluster.cluster-cxpwlkutkebk.us-east-1.neptune.amazonaws.com"

# Execute query
gen_result, exec_result = execute_nl_query(
    nl_query="What is the total portfolio value?",
    workload="financial_portfolios",
    database="financial_portfolios_db",
    neptune_endpoint=NEPTUNE_ENDPOINT,
    athena_database="financial_portfolios_db",
    s3_output_location="s3://your-bucket/athena-results/",
    region="us-east-1"
)

print(f"SQL: {gen_result.sql}")
print(f"Result: {exec_result.rows}")
```

**Expected SQL:**
```sql
SELECT SUM(p.market_value) + SUM(po.cash_balance) AS total_portfolio_value
FROM financial_portfolios_db.positions p
INNER JOIN financial_portfolios_db.portfolios po
  ON p.portfolio_id = po.portfolio_id
WHERE po.status = 'Active'
```

---

### Query 2: GROUP BY Dimension

```python
gen_result, exec_result = execute_nl_query(
    nl_query="Show me portfolio value by sector",
    workload="financial_portfolios",
    database="financial_portfolios_db",
    neptune_endpoint=NEPTUNE_ENDPOINT,
    athena_database="financial_portfolios_db",
    s3_output_location="s3://your-bucket/athena-results/",
    region="us-east-1"
)

print(f"SQL: {gen_result.sql}")
print(f"Rows returned: {exec_result.row_count}")
for row in exec_result.rows:
    print(f"  {row}")
```

**Expected SQL:**
```sql
SELECT sector, SUM(market_value) AS total_value
FROM financial_portfolios_db.positions
WHERE position_status = 'Open'
GROUP BY sector
ORDER BY total_value DESC
```

---

### Query 3: Complex Multi-Table

```python
gen_result, exec_result = execute_nl_query(
    nl_query="Show me top 5 holdings by value for aggressive growth portfolios",
    workload="financial_portfolios",
    database="financial_portfolios_db",
    neptune_endpoint=NEPTUNE_ENDPOINT,
    athena_database="financial_portfolios_db",
    s3_output_location="s3://your-bucket/athena-results/",
    region="us-east-1"
)

print(f"SQL: {gen_result.sql}")
print(f"Tables used: {', '.join(gen_result.tables_used)}")
print(f"Confidence: {gen_result.confidence:.2f}")
print(f"\nTop 5 Holdings:")
for i, row in enumerate(exec_result.rows, 1):
    print(f"{i}. {row}")
```

**Expected SQL:**
```sql
SELECT s.ticker, s.company_name, SUM(p.market_value) AS total_value
FROM financial_portfolios_db.positions p
INNER JOIN financial_portfolios_db.portfolios po
  ON p.portfolio_id = po.portfolio_id
INNER JOIN financial_portfolios_db.stocks s
  ON p.ticker = s.ticker
WHERE po.strategy = 'Aggressive Growth'
  AND po.status = 'Active'
GROUP BY s.ticker, s.company_name
ORDER BY total_value DESC
LIMIT 5
```

---

## Full Test Script (Run All 3 Queries)

Save as `test_neptune_queries.py`:

```python
#!/usr/bin/env python3
"""
Test Script: Run 3 natural language queries on Neptune
"""
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.semantic_layer import execute_nl_query

# Configuration
NEPTUNE_ENDPOINT = "semantic-layer-cluster.cluster-cxpwlkutkebk.us-east-1.neptune.amazonaws.com"
WORKLOAD = "financial_portfolios"
DATABASE = "financial_portfolios_db"
S3_OUTPUT = "s3://your-bucket/athena-results/"  # REPLACE THIS
REGION = "us-east-1"

# Test queries
queries = [
    "What is the total portfolio value?",
    "Show me portfolio value by sector",
    "Show me top 5 holdings by value for aggressive growth portfolios"
]

def run_test_queries():
    """Execute all test queries."""
    print("=" * 80)
    print("NEPTUNE SEMANTIC LAYER - TEST QUERIES")
    print("=" * 80)
    print(f"\nNeptune Endpoint: {NEPTUNE_ENDPOINT}")
    print(f"Workload: {WORKLOAD}")
    print(f"Database: {DATABASE}")
    print("\n" + "=" * 80)

    results = []

    for i, nl_query in enumerate(queries, 1):
        print(f"\n[Query {i}/{len(queries)}] {nl_query}")
        print("-" * 80)

        try:
            start_time = time.time()

            gen_result, exec_result = execute_nl_query(
                nl_query=nl_query,
                workload=WORKLOAD,
                database=DATABASE,
                neptune_endpoint=NEPTUNE_ENDPOINT,
                athena_database=DATABASE,
                s3_output_location=S3_OUTPUT,
                region=REGION,
                max_results=100
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Show SQL
            print(f"\n✓ Generated SQL:")
            print(gen_result.sql)

            # Show execution
            print(f"\n✓ Execution Status: {exec_result.status}")
            print(f"  Row Count: {exec_result.row_count}")
            print(f"  Execution Time: {exec_result.execution_time_ms}ms")
            print(f"  Total Time (incl. Neptune): {elapsed_ms}ms")
            print(f"  From Cache: {exec_result.from_cache}")

            # Show results (first 5 rows)
            if exec_result.status == 'success' and exec_result.rows:
                print(f"\n✓ Results (first 5):")
                for j, row in enumerate(exec_result.rows[:5], 1):
                    print(f"  {j}. {row}")
                if exec_result.row_count > 5:
                    print(f"  ... and {exec_result.row_count - 5} more rows")

            results.append({
                'query': nl_query,
                'status': 'success',
                'sql': gen_result.sql,
                'row_count': exec_result.row_count,
                'time_ms': elapsed_ms
            })

        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()

            results.append({
                'query': nl_query,
                'status': 'failed',
                'error': str(e)
            })

        print("-" * 80)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    successful = sum(1 for r in results if r['status'] == 'success')
    print(f"\nQueries Executed: {len(queries)}")
    print(f"Successful: {successful}")
    print(f"Failed: {len(queries) - successful}")

    if successful > 0:
        total_rows = sum(r.get('row_count', 0) for r in results if r['status'] == 'success')
        avg_time = sum(r.get('time_ms', 0) for r in results if r['status'] == 'success') / successful
        print(f"Total Rows Returned: {total_rows}")
        print(f"Average Query Time: {avg_time:.0f}ms")

    print("\n" + "=" * 80)
    print("✓ Test Complete!")
    print("=" * 80)

    return results


if __name__ == '__main__':
    results = run_test_queries()
    sys.exit(0 if all(r['status'] == 'success' for r in results) else 1)
```

**Run it:**
```bash
cd /Users/hcherian/Documents/Claude-data-operations
python3 test_neptune_queries.py
```

---

## Troubleshooting

### Issue: ModuleNotFoundError: No module named 'shared.semantic_layer'

**Solution**: Install dependencies
```bash
cd /Users/hcherian/Documents/Claude-data-operations
pip3 install -r requirements.txt

# Or install individually:
pip3 install boto3 gremlinpython pyyaml
```

### Issue: Neptune connection timeout

**Solution**: Neptune is in a VPC - use Lambda or EC2
```bash
# Option 1: Deploy Lambda (recommended)
bash shared/semantic_layer/deploy_neptune_loader_lambda.sh

# Option 2: Use EC2 bastion host
# SSH to EC2 instance in same VPC, then run queries
```

### Issue: No data in Neptune

**Solution**: Load semantic layer
```bash
# Load financial_portfolios workload
python3 shared/semantic_layer/load_to_neptune.py \
  --workload financial_portfolios \
  --database financial_portfolios_db \
  --neptune-endpoint semantic-layer-cluster.cluster-cxpwlkutkebk.us-east-1.neptune.amazonaws.com \
  --region us-east-1
```

### Issue: Athena query fails (permission denied)

**Solution**: Grant Lake Formation permissions
```bash
# Grant SELECT on all tables
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT:role/YourRole \
  --resource '{"Table":{"DatabaseName":"financial_portfolios_db","TableWildcard":{}}}' \
  --permissions SELECT
```

### Issue: S3 output location error

**Solution**: Create bucket or update path
```bash
# Create bucket
aws s3 mb s3://your-athena-results

# Or use existing bucket - update S3_OUTPUT variable in script
```

---

## Expected Performance

| Query Type | Tables | JOINs | Expected Time |
|------------|--------|-------|---------------|
| Simple aggregation | 2 | 1 | 2-3 seconds |
| GROUP BY | 1-2 | 0-1 | 3-4 seconds |
| Complex (3+ tables) | 3 | 2 | 4-6 seconds |

**Includes:**
- Neptune semantic search: <1s
- Graph traversal: <1s
- SQL generation: <1s
- Athena execution: 2-5s

**Total: 2-6 seconds from natural language to results**

---

## Next Steps

1. **Run test script** to verify Neptune works
2. **Load more workloads** (customer_master, order_transactions, etc.)
3. **Test SynoDB caching** (run same query twice - should be instant second time)
4. **Build QuickSight integration** (use prompt `01-create-dashboard.md`)

---

## Related Documentation

- `02-query-semantic-layer.md` - Detailed Neptune workflow (8 steps)
- `../../shared/semantic_layer/README.md` - Setup guide
- `../../shared/semantic_layer/COMPLETE_SETUP_GUIDE.md` - Neptune deployment
- `../../MCP_GUARDRAILS.md` - MCP tool usage

---

**Ready to query?** Copy one of the test scripts above and run it!
