# Data Analysis Agent: Natural Language Query via Neptune Semantic Layer

**Agent**: Data Analysis Agent
**Purpose**: Convert natural language questions to SQL queries using Neptune semantic layer
**Prerequisites**: Gold zone data loaded, semantic layer populated in Neptune
**MCP Tools**: `neptune` (graph queries), `dynamodb` (SynoDB), `athena_query` (SQL execution)

---

## Overview

This prompt enables the Data Analysis Agent to answer natural language questions by:
1. **Semantic search** in Neptune (vector similarity on embeddings)
2. **Graph traversal** for discovering table relationships (FK joins)
3. **Query caching** via SynoDB (DynamoDB) for reusing past successful queries
4. **SQL generation** using column roles, aggregations, and business context
5. **Execution** via Athena MCP tool
6. **Learning** by saving successful queries back to SynoDB

---

## Step 1: Receive Natural Language Query

**Input from user:**
```
User: "What is the total portfolio value by region for Q1 2026?"
```

**Your task:** Parse the intent and identify key components:
- **Measure**: "total portfolio value" → likely a SUM aggregation
- **Dimension**: "by region" → GROUP BY region
- **Filter**: "Q1 2026" → WHERE condition on date
- **Aggregation**: "total" → SUM

---

## Step 2: Check SynoDB for Cached Queries (Optional)

Before generating a new query, check if a similar query has been executed before.

**MCP Tool**: `dynamodb` server → `query` action

```python
# Check SynoDB for similar queries
table_name = "synodb_queries"
partition_key = f"workload#{workload_name}"
sort_key_prefix = "query#"

# Search by natural language embedding similarity (if available)
# OR: Search by keyword match in natural_language field
```

**If found:**
- Reuse the SQL (adapt date filters if needed)
- Skip to Step 6 (Execute Query)

**If not found:**
- Proceed to Step 3 (semantic search in Neptune)

---

## Step 3: Semantic Search in Neptune

Use Neptune + Titan embeddings to find relevant tables and columns.

### 3a. Generate Embedding for User Query

**MCP Tool**: `bedrock` (if available) or use pre-computed embeddings

```python
# Generate 1024-dim Titan embedding for user query
query_text = "total portfolio value by region Q1 2026"
embedding = bedrock.invoke_titan_embeddings(query_text)
# Returns: [0.123, -0.456, 0.789, ..., 0.234]  (1024 dimensions)
```

### 3b. Vector Similarity Search in Neptune

**MCP Tool**: `neptune` server (custom MCP or via Lambda)

**Gremlin Query** (vector similarity search):
```gremlin
g.V().has('type', 'column')
     .has('embedding', near(query_embedding, k=10))
     .values('name', 'table', 'role', 'aggregation', 'business_term')
```

**Expected Result**:
```json
[
  {
    "name": "portfolio_value",
    "table": "gold_zone.portfolio_fact",
    "role": "measure",
    "aggregation": "sum",
    "business_term": "Portfolio Value"
  },
  {
    "name": "region_name",
    "table": "gold_zone.dim_region",
    "role": "dimension",
    "aggregation": null,
    "business_term": "Region"
  },
  {
    "name": "valuation_date",
    "table": "gold_zone.portfolio_fact",
    "role": "temporal",
    "aggregation": null,
    "business_term": "Valuation Date"
  }
]
```

---

## Step 4: Graph Traversal for Table Relationships

Use Neptune graph to discover how tables are related (FK joins).

**Gremlin Query** (find FK relationships):
```gremlin
g.V().has('type', 'table').has('name', 'portfolio_fact')
     .out('has_column')
     .has('is_foreign_key', true)
     .inE('references')
     .outV()
     .values('table_name', 'column_name')
```

**Expected Result**:
```json
[
  {
    "from_table": "portfolio_fact",
    "from_column": "region_id",
    "to_table": "dim_region",
    "to_column": "region_id"
  }
]
```

**This tells you:**
```sql
JOIN gold_zone.dim_region d ON f.region_id = d.region_id
```

---

## Step 5: Generate SQL from Semantic Context

Combine results from Steps 3-4 to construct SQL.

### 5a. Identify Query Components

From semantic search results:
- **Fact table**: `gold_zone.portfolio_fact`
- **Measure column**: `portfolio_value` (role: measure, aggregation: sum)
- **Dimension table**: `gold_zone.dim_region`
- **Dimension column**: `region_name` (role: dimension)
- **Temporal column**: `valuation_date` (role: temporal)

From graph traversal:
- **JOIN condition**: `f.region_id = d.region_id`

### 5b. Construct SQL

```sql
SELECT
  d.region_name,
  SUM(f.portfolio_value) AS total_portfolio_value
FROM gold_zone.portfolio_fact f
JOIN gold_zone.dim_region d ON f.region_id = d.region_id
WHERE
  f.valuation_date >= DATE '2026-01-01'
  AND f.valuation_date < DATE '2026-04-01'
GROUP BY d.region_name
ORDER BY total_portfolio_value DESC
```

### 5c. Validation Rules

Before executing, validate:
1. ✅ All tables exist in Glue Catalog
2. ✅ All columns exist in their respective tables
3. ✅ JOIN columns have compatible types (e.g., both `bigint`)
4. ✅ WHERE clause uses correct date format
5. ✅ Aggregation matches column role (e.g., SUM for measure)
6. ✅ GROUP BY includes all non-aggregated columns in SELECT

**If validation fails**: Return error to user with explanation.

---

## Step 6: Execute Query via Athena MCP

**MCP Tool**: `glue-athena` server → `athena_query` action

```python
# Execute SQL via Athena
result = athena_query(
    database="financial_portfolios_db",
    query=generated_sql,
    output_location="s3://bucket/athena-results/",
    workgroup="primary"
)
```

**Handle execution:**
- ✅ **Success**: Proceed to Step 7
- ❌ **Syntax error**: Fix SQL and retry (max 2 attempts)
- ❌ **Permission error**: Check Lake Formation grants
- ❌ **Timeout**: Suggest optimizing query (add LIMIT, partition filters)

---

## Step 7: Return Results to User

Format results for readability:

**Option A: Table format (for small result sets)**
```
Region          | Total Portfolio Value
----------------|---------------------
North America   | $4,523,456.78
Europe          | $3,112,890.45
Asia Pacific    | $2,987,654.32
Latin America   | $1,234,567.89
```

**Option B: JSON (for programmatic access)**
```json
{
  "query": "What is the total portfolio value by region for Q1 2026?",
  "sql": "SELECT d.region_name, SUM(f.portfolio_value) AS total_portfolio_value FROM...",
  "rows": [
    {"region_name": "North America", "total_portfolio_value": 4523456.78},
    {"region_name": "Europe", "total_portfolio_value": 3112890.45},
    {"region_name": "Asia Pacific", "total_portfolio_value": 2987654.32},
    {"region_name": "Latin America", "total_portfolio_value": 1234567.89}
  ],
  "row_count": 4,
  "execution_time_ms": 3421
}
```

**Option C: Visualization recommendation (if dashboard requested)**
```
Recommended visualization: Bar chart
- X-axis: region_name
- Y-axis: total_portfolio_value
- Sort: Descending by value
```

---

## Step 8: Save Successful Query to SynoDB

After a successful query, save it for future reuse.

**MCP Tool**: `dynamodb` server → `put_item` action

```python
# Save to SynoDB
synodb_entry = {
    "pk": f"workload#{workload_name}",
    "sk": f"query#{timestamp}#{query_id}",
    "query_id": query_id,
    "natural_language": "What is the total portfolio value by region for Q1 2026?",
    "sql": generated_sql,
    "tables_used": ["gold_zone.portfolio_fact", "gold_zone.dim_region"],
    "columns_used": ["portfolio_value", "region_name", "valuation_date", "region_id"],
    "success_count": 1,
    "last_used": "2026-03-27T14:30:00Z",
    "execution_time_ms": 3421,
    "row_count": 4,
    "embedding": query_embedding  # 1024-dim Titan vector
}

dynamodb.put_item(table_name="synodb_queries", item=synodb_entry)
```

**Why save?**
- Next time a similar query is asked, we can reuse the SQL (Step 2)
- Track query patterns to improve semantic layer over time
- Learn which aggregations and joins users find most useful

---

## Example End-to-End Flow

### User Query
```
User: "Show me top 5 customers by revenue in Q4 2025"
```

### Agent Execution

**Step 1: Parse Intent**
- Measure: revenue (SUM)
- Dimension: customer
- Filter: Q4 2025
- Limit: 5
- Sort: DESC

**Step 2: Check SynoDB**
- No cached query found → proceed to Neptune

**Step 3: Semantic Search in Neptune**
```gremlin
# Find columns matching "revenue" and "customer"
Results:
- revenue_amount (measure, SUM, sales_fact)
- customer_name (dimension, dim_customer)
- sale_date (temporal, sales_fact)
```

**Step 4: Graph Traversal**
```gremlin
# Find FK join
Result: sales_fact.customer_id → dim_customer.customer_id
```

**Step 5: Generate SQL**
```sql
SELECT
  c.customer_name,
  SUM(f.revenue_amount) AS total_revenue
FROM gold_zone.sales_fact f
JOIN gold_zone.dim_customer c ON f.customer_id = c.customer_id
WHERE
  f.sale_date >= DATE '2025-10-01'
  AND f.sale_date < DATE '2026-01-01'
GROUP BY c.customer_name
ORDER BY total_revenue DESC
LIMIT 5
```

**Step 6: Execute via Athena**
```
Status: SUCCESS
Rows: 5
Execution time: 2.1s
```

**Step 7: Return Results**
```
Customer Name       | Total Revenue
--------------------|---------------
Acme Corporation    | $987,654.32
Global Industries   | $876,543.21
Tech Solutions Inc  | $765,432.10
Mega Retail Group   | $654,321.09
Prime Partners      | $543,210.98
```

**Step 8: Save to SynoDB**
```
✓ Saved query q_00042 to SynoDB
```

---

## Neptune Graph Schema

Your semantic layer in Neptune has this structure:

### Vertices (Nodes)
```python
# Database vertex
{
  "id": "db:financial_portfolios_db",
  "label": "database",
  "properties": {
    "name": "financial_portfolios_db",
    "environment": "prod",
    "workload": "financial_portfolios"
  }
}

# Table vertex
{
  "id": "table:portfolio_fact",
  "label": "table",
  "properties": {
    "name": "portfolio_fact",
    "database": "financial_portfolios_db",
    "table_type": "fact",
    "row_count": 1234567,
    "embedding": [0.123, -0.456, ...],  # 1024-dim
    "business_description": "Daily portfolio valuations"
  }
}

# Column vertex
{
  "id": "col:portfolio_value",
  "label": "column",
  "properties": {
    "name": "portfolio_value",
    "table": "portfolio_fact",
    "role": "measure",  # measure | dimension | temporal | identifier
    "data_type": "decimal",
    "aggregation": "sum",
    "business_term": "Portfolio Value",
    "pii_type": null,
    "sensitivity": "low",
    "embedding": [0.789, 0.234, ...]  # 1024-dim
  }
}

# Business Term vertex (for semantic search)
{
  "id": "term:portfolio_value",
  "label": "business_term",
  "properties": {
    "term": "Portfolio Value",
    "definition": "Total market value of all assets in portfolio",
    "synonyms": ["AUM", "Asset Value", "Holdings Value"],
    "embedding": [0.345, -0.678, ...]  # 1024-dim
  }
}

# Query vertex (learned patterns from SynoDB)
{
  "id": "query:q_00042",
  "label": "query",
  "properties": {
    "natural_language": "top 5 customers by revenue",
    "sql": "SELECT c.customer_name, SUM(f.revenue) ...",
    "success_count": 15,
    "embedding": [0.567, 0.890, ...]  # 1024-dim
  }
}
```

### Edges (Relationships)
```python
# Database → Table
database --[contains]--> table

# Table → Column
table --[has_column]--> column

# Foreign Key
column --[references]--> column  # FK relationship

# Business Context
column --[described_by]--> business_term

# Query Usage
query --[uses_table]--> table
query --[uses_column]--> column
```

---

## Gremlin Query Examples

### Find all measures in a table
```gremlin
g.V().has('type', 'table').has('name', 'portfolio_fact')
     .out('has_column')
     .has('role', 'measure')
     .values('name', 'aggregation', 'business_term')
```

### Find all tables containing a business term
```gremlin
g.V().has('type', 'business_term').has('term', 'Revenue')
     .in('described_by')
     .in('has_column')
     .dedup()
     .values('name')
```

### Find the shortest join path between two tables
```gremlin
g.V().has('type', 'table').has('name', 'sales_fact')
     .repeat(out('has_column').out('references').in('has_column'))
     .until(has('type', 'table').has('name', 'dim_customer'))
     .path()
     .limit(1)
```

### Find similar past queries (vector similarity)
```gremlin
g.V().has('type', 'query')
     .has('embedding', near(user_query_embedding, k=5))
     .values('natural_language', 'sql', 'success_count')
     .order().by('success_count', desc)
```

---

## MCP Tools Reference

### Neptune Queries (Custom MCP or Lambda)

**Option 1: Custom Neptune MCP Server** (if available)
```python
# MCP tool: neptune_query
response = neptune_query(
    endpoint="your-neptune-endpoint.amazonaws.com",
    gremlin_query="g.V().has('type', 'table').values('name')",
    region="us-east-1"
)
```

**Option 2: Lambda Invocation** (if Neptune in VPC)
```python
# MCP tool: lambda (invoke)
response = lambda_invoke(
    function_name="neptune-query-executor",
    payload={
        "gremlin_query": "g.V().has('type', 'table').values('name')",
        "neptune_endpoint": "your-neptune-endpoint.amazonaws.com"
    }
)
```

### SynoDB (DynamoDB MCP)

**Query for cached queries:**
```python
# MCP tool: dynamodb query
response = dynamodb_query(
    table_name="synodb_queries",
    key_condition="pk = :workload",
    expression_attribute_values={":workload": "workload#financial_portfolios"}
)
```

**Save new query:**
```python
# MCP tool: dynamodb put_item
dynamodb_put_item(
    table_name="synodb_queries",
    item={
        "pk": "workload#financial_portfolios",
        "sk": "query#2026-03-27#q_00042",
        "natural_language": "...",
        "sql": "...",
        "embedding": [...]
    }
)
```

### Athena Execution (glue-athena MCP)

```python
# MCP tool: athena_query
result = athena_query(
    database="financial_portfolios_db",
    query="SELECT * FROM portfolio_fact LIMIT 10",
    output_location="s3://bucket/results/",
    workgroup="primary"
)
```

---

## Error Handling

### No Relevant Tables Found
```
Error: Neptune semantic search returned no matching tables for query: "customer churn rate"

Suggestion:
- Check if workload has been onboarded (Phase 1-5 complete)
- Check if semantic.yaml includes "customer" and "churn" business terms
- Try broader terms: "customer retention" or "customer status"
```

### Ambiguous Query
```
Error: Multiple interpretations found for "revenue"
- Option 1: total_revenue (SUM of revenue_amount)
- Option 2: average_revenue (AVG of revenue_amount)
- Option 3: revenue_count (COUNT of revenue transactions)

Suggestion: Please clarify - do you want total, average, or count?
```

### Permission Denied (Lake Formation)
```
Error: Athena query failed with ACCESS_DENIED

Reason: Lake Formation has not granted SELECT permission on table gold_zone.portfolio_fact

Solution: Run Lake Formation grant:
  aws lakeformation grant-permissions \
    --principal DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT:role/QuickSightRole \
    --resource Table={DatabaseName=financial_portfolios_db,Name=portfolio_fact} \
    --permissions SELECT
```

### Query Timeout
```
Error: Athena query exceeded timeout (30s)

Optimization suggestions:
1. Add partition filter: WHERE year=2026 AND month=3
2. Reduce date range: Q1 2026 → March 2026 only
3. Add LIMIT clause: LIMIT 1000
4. Check if table has partitions defined
```

---

## Testing Your Implementation

### Test 1: Simple Aggregation
```
Input: "What is the total portfolio value?"
Expected SQL: SELECT SUM(portfolio_value) FROM portfolio_fact
Expected: Single row with numeric result
```

### Test 2: GROUP BY Dimension
```
Input: "Show me portfolio value by region"
Expected SQL: SELECT region_name, SUM(portfolio_value) FROM portfolio_fact f JOIN dim_region d ON f.region_id = d.region_id GROUP BY region_name
Expected: Multiple rows, one per region
```

### Test 3: Date Filter
```
Input: "Portfolio value in Q1 2026"
Expected SQL: SELECT SUM(portfolio_value) FROM portfolio_fact WHERE valuation_date >= '2026-01-01' AND valuation_date < '2026-04-01'
Expected: Single row with filtered result
```

### Test 4: TOP N
```
Input: "Top 5 customers by revenue"
Expected SQL: SELECT customer_name, SUM(revenue) FROM sales_fact f JOIN dim_customer c ... GROUP BY customer_name ORDER BY 2 DESC LIMIT 5
Expected: 5 rows ordered by revenue descending
```

### Test 5: Complex Join (3+ tables)
```
Input: "Revenue by product category and region"
Expected SQL: Joins sales_fact → dim_product → dim_category + dim_region
Expected: Cartesian product of categories × regions
```

---

## Best Practices

### DO ✅
- **Always check SynoDB first** - reuse successful queries when possible
- **Use semantic search** - don't rely on exact keyword matches
- **Validate SQL before execution** - check column/table existence
- **Save successful queries** - populate SynoDB for future reuse
- **Return visualization recommendations** - guide users to insights
- **Handle ambiguity gracefully** - ask clarifying questions when needed

### DON'T ❌
- **Don't generate SQL without Neptune context** - guessing table names leads to errors
- **Don't skip validation** - executing invalid SQL wastes time and frustrates users
- **Don't forget to filter PII** - respect column sensitivity levels from Neptune
- **Don't return raw Athena errors** - translate to user-friendly messages
- **Don't ignore SynoDB cache** - redundant queries waste compute and cost money

---

## Output: Present Results to User

After successful execution, format your response:

```markdown
### Query Results

**Your question:** "What is the total portfolio value by region for Q1 2026?"

**Generated SQL:**
```sql
SELECT
  d.region_name,
  SUM(f.portfolio_value) AS total_portfolio_value
FROM gold_zone.portfolio_fact f
JOIN gold_zone.dim_region d ON f.region_id = d.region_id
WHERE
  f.valuation_date >= DATE '2026-01-01'
  AND f.valuation_date < DATE '2026-04-01'
GROUP BY d.region_name
ORDER BY total_portfolio_value DESC
```

**Results:**

| Region          | Total Portfolio Value |
|-----------------|----------------------|
| North America   | $4,523,456.78        |
| Europe          | $3,112,890.45        |
| Asia Pacific    | $2,987,654.32        |
| Latin America   | $1,234,567.89        |

**Insights:**
- North America leads with 45% of total Q1 portfolio value
- Asia Pacific grew 12% vs Q4 2025
- All regions showed positive performance in Q1

**Visualization:** Bar chart recommended (region on X-axis, value on Y-axis)

**Query saved to SynoDB:** ✓ (ID: q_00042)
```

---

## Related Documentation

- `../../shared/semantic_layer/README.md` - Neptune setup guide
- `../../shared/semantic_layer/COMPLETE_SETUP_GUIDE.md` - Full Neptune deployment
- `../data-onboarding-agent/03-onboard-build-pipeline.md` - Populate semantic.yaml
- `../../SKILLS.md` - Analysis Agent skill definition (section 7)
- `../../MCP_GUARDRAILS.md` - Which MCP tool to use when

---

## Troubleshooting

**Q: Neptune endpoint not found**
A: Run `shared/semantic_layer/COMPLETE_SETUP_GUIDE.md` to deploy Neptune cluster

**Q: No embeddings in Neptune**
A: Run `shared/semantic_layer/load_to_neptune.py` to populate graph with Titan embeddings

**Q: SynoDB table doesn't exist**
A: Run `prompts/environment-setup-agent/setup-aws-infrastructure.md` Step 9 (create DynamoDB table)

**Q: Gremlin query timeout**
A: Neptune is in VPC - use Lambda invocation instead of direct connection

**Q: Wrong SQL generated**
A: Check `semantic.yaml` - column roles (measure/dimension) may be incorrect

---

**Ready to query?** Provide a natural language question and let's generate SQL!
