# Test Query 3: Complex Multi-Table Join with Filter

## Natural Language Query
**"Show me top 5 holdings by value for aggressive growth portfolios"**

---

## Agent Workflow Simulation

### Step 1: Parse Intent
- **Measure**: "holdings by value" → SUM(market_value) by ticker
- **Dimension**: "holdings" → ticker / company_name
- **Filter**: "aggressive growth portfolios" → strategy = 'Aggressive Growth'
- **Aggregation**: SUM
- **Limit**: TOP 5
- **Sort**: DESC by value

### Step 2: Check SynoDB Cache
```
Status: CACHE_MISS
Reason: No cached query for "aggressive growth portfolios"
Similar queries found:
  - "top 5 holdings by value" (similarity: 0.85)
  - "portfolio value by sector" (similarity: 0.62)
Action: Adapt similar query + add portfolio filter
```

### Step 3: Semantic Search in Neptune

**Query embedding:**
```
User query: "top 5 holdings by value for aggressive growth portfolios"
Keywords: [top, holdings, value, aggressive, growth, portfolios]
Titan embedding: [0.789, -0.345, 0.234, ...] (1024 dimensions)
```

**Neptune Results (ranked by similarity):**
```json
[
  {
    "name": "market_value",
    "table": "positions",
    "role": "measure",
    "aggregation": "sum",
    "similarity": 0.94
  },
  {
    "name": "ticker",
    "table": "positions",
    "role": "identifier",
    "similarity": 0.89
  },
  {
    "name": "company_name",
    "table": "stocks",
    "role": "dimension",
    "similarity": 0.87
  },
  {
    "name": "strategy",
    "table": "portfolios",
    "role": "dimension",
    "sample_values": ["Growth", "Value", "Balanced", "Income", "Aggressive Growth"],
    "similarity": 0.92
  }
]
```

**Tables identified:**
- `positions` (fact table - has market_value, ticker)
- `stocks` (dimension - has company_name)
- `portfolios` (dimension - has strategy filter)

### Step 4: Graph Traversal for Multi-Table JOIN

**Gremlin Query (find join path positions → stocks → portfolios):**
```gremlin
// Find path from positions to stocks
g.V().has('type', 'table').has('name', 'positions')
     .out('has_column').has('name', 'ticker').has('is_foreign_key', true)
     .inE('references')
     .outV()
     .in('has_column')
     .has('type', 'table').has('name', 'stocks')
     .path()

// Find path from positions to portfolios
g.V().has('type', 'table').has('name', 'positions')
     .out('has_column').has('name', 'portfolio_id').has('is_foreign_key', true)
     .inE('references')
     .outV()
     .in('has_column')
     .has('type', 'table').has('name', 'portfolios')
     .path()
```

**Neptune Graph Traversal Results:**
```json
{
  "join_paths": [
    {
      "from_table": "positions",
      "from_column": "ticker",
      "to_table": "stocks",
      "to_column": "ticker",
      "relationship": "many_to_one",
      "cardinality": "N:1",
      "fan_out_risk": false
    },
    {
      "from_table": "positions",
      "from_column": "portfolio_id",
      "to_table": "portfolios",
      "to_column": "portfolio_id",
      "relationship": "many_to_one",
      "cardinality": "N:1",
      "fan_out_risk": false
    }
  ]
}
```

**Join semantic from semantic.yaml:**
```yaml
join_name: "full_position_context"
tables: ["positions", "portfolios", "stocks"]
join_type: "inner"
join_condition: "positions.portfolio_id = portfolios.portfolio_id AND positions.ticker = stocks.ticker"
when_to_join: "Join all three tables when analysis requires both stock and portfolio dimensions simultaneously"
pre_aggregation_rule: "Join BEFORE aggregating to enable multi-dimensional grouping"
fan_out_warning: "No fan-out risk - both foreign keys reference unique dimension records"
```

### Step 5: Generate SQL

**Multi-table JOIN with aggregation:**
```sql
SELECT
  s.ticker,
  s.company_name,
  s.sector,
  s.industry,
  SUM(p.market_value) AS total_value,
  SUM(p.shares) AS total_shares,
  COUNT(DISTINCT p.portfolio_id) AS num_portfolios,
  AVG(p.unrealized_gain_loss_pct) AS avg_return_pct
FROM financial_portfolios_db.positions p
INNER JOIN financial_portfolios_db.portfolios po
  ON p.portfolio_id = po.portfolio_id
INNER JOIN financial_portfolios_db.stocks s
  ON p.ticker = s.ticker
WHERE po.strategy = 'Aggressive Growth'
  AND po.status = 'Active'
  AND p.position_status = 'Open'
GROUP BY s.ticker, s.company_name, s.sector, s.industry
ORDER BY total_value DESC
LIMIT 5
```

**Validation:**
- ✅ All 3 tables exist (positions, portfolios, stocks)
- ✅ All columns exist and have correct types
- ✅ JOIN conditions match FK relationships from Neptune
- ✅ GROUP BY includes all non-aggregated SELECT columns
- ✅ WHERE filter values are valid (strategy = 'Aggressive Growth')
- ✅ No fan-out risk (both JOINs are N:1)
- ✅ Aggregations match column roles (SUM for measures)

### Step 6: Execute via Athena MCP

```python
result = athena_query(
    database="financial_portfolios_db",
    query=generated_sql,
    output_location="s3://bucket/athena-results/",
    workgroup="primary"
)
```

**Execution:**
```json
{
  "status": "SUCCEEDED",
  "execution_time_ms": 4567,
  "rows_returned": 5,
  "bytes_scanned": 5678910,
  "data_scanned_mb": 5.42
}
```

### Step 7: Return Results to User

**Raw Results:**
```json
[
  {
    "ticker": "NVDA",
    "company_name": "NVIDIA Corporation",
    "sector": "Technology",
    "industry": "Semiconductors",
    "total_value": 3456789.50,
    "total_shares": 12500.0000,
    "num_portfolios": 4,
    "avg_return_pct": 127.45
  },
  {
    "ticker": "TSLA",
    "company_name": "Tesla, Inc.",
    "sector": "Consumer Discretionary",
    "industry": "Automobiles",
    "total_value": 2987654.25,
    "total_shares": 15000.0000,
    "num_portfolios": 3,
    "avg_return_pct": 89.32
  },
  {
    "ticker": "MSFT",
    "company_name": "Microsoft Corporation",
    "sector": "Technology",
    "industry": "Software",
    "total_value": 2654321.75,
    "total_shares": 8000.0000,
    "num_portfolios": 5,
    "avg_return_pct": 45.67
  },
  {
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "total_value": 2345678.00,
    "total_shares": 13000.0000,
    "num_portfolios": 5,
    "avg_return_pct": 38.21
  },
  {
    "ticker": "GOOGL",
    "company_name": "Alphabet Inc.",
    "sector": "Technology",
    "industry": "Internet Services",
    "total_value": 1987654.50,
    "total_shares": 6500.0000,
    "num_portfolios": 3,
    "avg_return_pct": 52.89
  }
]
```

**Formatted Response:**

---

### Query Results

**Your question:** "Show me top 5 holdings by value for aggressive growth portfolios"

**Generated SQL:**
```sql
SELECT
  s.ticker,
  s.company_name,
  s.sector,
  s.industry,
  SUM(p.market_value) AS total_value,
  SUM(p.shares) AS total_shares,
  COUNT(DISTINCT p.portfolio_id) AS num_portfolios,
  AVG(p.unrealized_gain_loss_pct) AS avg_return_pct
FROM financial_portfolios_db.positions p
INNER JOIN financial_portfolios_db.portfolios po
  ON p.portfolio_id = po.portfolio_id
INNER JOIN financial_portfolios_db.stocks s
  ON p.ticker = s.ticker
WHERE po.strategy = 'Aggressive Growth'
  AND po.status = 'Active'
  AND p.position_status = 'Open'
GROUP BY s.ticker, s.company_name, s.sector, s.industry
ORDER BY total_value DESC
LIMIT 5
```

**Results:**

| Rank | Ticker | Company | Sector | Industry | Total Value | Shares | Portfolios | Avg Return |
|------|--------|---------|--------|----------|-------------|--------|------------|------------|
| 1 | NVDA | NVIDIA Corporation | Technology | Semiconductors | $3,456,789.50 | 12,500 | 4 | **+127.45%** |
| 2 | TSLA | Tesla, Inc. | Consumer Discretionary | Automobiles | $2,987,654.25 | 15,000 | 3 | +89.32% |
| 3 | MSFT | Microsoft Corporation | Technology | Software | $2,654,321.75 | 8,000 | 5 | +45.67% |
| 4 | AAPL | Apple Inc. | Technology | Consumer Electronics | $2,345,678.00 | 13,000 | 5 | +38.21% |
| 5 | GOOGL | Alphabet Inc. | Technology | Internet Services | $1,987,654.50 | 6,500 | 3 | +52.89% |

**Insights:**
- **Top holding**: NVIDIA with $3.5M (127% return!) — riding the AI/GPU wave
- **Tech dominance**: 4 of top 5 are Technology sector (NVDA, MSFT, AAPL, GOOGL)
- **High returns**: All top 5 positions are profitable (avg +70.7% return)
- **Diversification**: Holdings span 4 portfolios (good cross-portfolio correlation)
- **Aggressive strategy working**: Strong performance validates aggressive growth approach

**Risk Analysis:**
- ⚠️ **High concentration**: Top 5 represent 78% of aggressive growth portfolio value
- ⚠️ **Sector risk**: 80% exposure to Technology sector (single-sector risk)
- ⚠️ **Volatility**: NVIDIA +127% could reverse quickly — consider taking profits
- ✅ **Strong fundamentals**: All 5 are blue-chip stocks with solid earnings

**Recommendations:**
1. **Rebalance**: Consider reducing NVIDIA position (>25% of top 5)
2. **Diversify**: Add non-Tech holdings (Healthcare, Financials)
3. **Risk management**: Set stop-loss at 20% below current NVIDIA price
4. **Take profits**: Consider selling 10-20% of NVIDIA, reallocate to defensive sectors

**Visualization:** Horizontal bar chart
- **X-axis:** Total value
- **Y-axis:** Company name (ticker)
- **Color:** By avg return % (green gradient for profitability)
- **Annotation:** Show % return on each bar

---

### Step 8: Save to SynoDB

```json
{
  "pk": "workload#financial_portfolios",
  "sk": "query#2026-03-27#q_00003",
  "query_id": "q_00003",
  "natural_language": "Show me top 5 holdings by value for aggressive growth portfolios",
  "sql": "SELECT s.ticker, s.company_name, s.sector, s.industry, SUM(p.market_value)...",
  "tables_used": ["positions", "portfolios", "stocks"],
  "columns_used": ["ticker", "company_name", "sector", "industry", "market_value", "shares", "portfolio_id", "strategy", "status", "position_status", "unrealized_gain_loss_pct"],
  "join_strategy": "full_position_context",
  "success_count": 1,
  "last_used": "2026-03-27T10:22:18Z",
  "execution_time_ms": 4567,
  "row_count": 5,
  "embedding": [0.789, -0.345, ...],
  "result_summary": "NVDA leads with $3.5M (+127%), top 5 all Tech/growth stocks",
  "visualization_type": "horizontal_bar_chart",
  "grouping_dimension": "ticker",
  "aggregation_measure": "market_value",
  "filter_applied": "strategy = 'Aggressive Growth'",
  "complexity": "high",
  "num_joins": 2,
  "query_pattern": "top_n_with_filter"
}
```

**Status:** ✅ Query saved to SynoDB (ID: q_00003)

---

## Summary

✅ **Successfully processed complex multi-table JOIN query**
- Semantic search identified 3 tables needed (positions, portfolios, stocks)
- Graph traversal discovered 2 FK relationships automatically
- Generated correct 2-JOIN SQL with proper aggregation and filtering
- Applied business rule: only Active portfolios + Open positions
- Returned TOP 5 results ordered by value
- Execution time: 4.6 seconds (excellent for 3-table join)
- Provided actionable insights + risk analysis + recommendations
- Saved complex query pattern to SynoDB for future reuse

**Key Learning:**
- Neptune graph enabled automatic JOIN discovery (no manual schema analysis needed)
- Semantic.yaml provided `join_semantics` guidance (pre-aggregation rule, fan-out warnings)
- Agent used business context to add smart defaults (Active portfolios, Open positions)
- SynoDB now has a reusable pattern for "top N by strategy" queries

**Query Complexity Comparison:**
| Query | Tables | JOINs | Filters | Execution Time |
|-------|--------|-------|---------|---------------|
| Q1: Total value | 2 | 1 | 2 | 2.3s |
| Q2: Value by sector | 1 | 0 | 1 | 3.1s |
| Q3: Top 5 aggressive growth | 3 | 2 | 3 | 4.6s |

**Neptune's Impact:** Without Neptune, engineer would need to manually figure out the JOINs, aggregations, and filters — estimated 30-60 minutes. Neptune-powered agent did it in ~5 seconds.
