# Data Analysis Agent

**Agent Type**: Consumer / Analytics
**Runs**: On-demand, after data onboarding complete
**Prerequisites**: At least one workload in Gold zone

## Purpose

The Data Analysis Agent consumes the semantic layer created by the Data Onboarding Agent. It understands business context (via SageMaker Catalog + SynoDB) and generates SQL queries, dashboards, and visualizations.

## Architecture

```
Data Analysis Agent
  │
  ├── Reads Semantic Layer
  │   ├── SageMaker Catalog (column roles: measure, dimension, temporal)
  │   ├── SynoDB (past SQL queries + metrics)
  │   └── Knowledge Graph (embeddings for semantic search)
  │
  ├── Generates SQL Queries
  │   ├── Uses column roles to build aggregations
  │   ├── Checks SynoDB for similar past queries
  │   └── Saves new useful queries back to SynoDB
  │
  └── Creates Dashboards
      ├── QuickSight datasets + dashboards
      ├── Visualization recommendations
      └── Automatic refresh schedules
```

## How It Works

**User asks**: "Show me monthly revenue by region"

**Agent reasoning**:
1. Queries SageMaker Catalog: "Which tables have 'revenue' (measure) and 'region' (dimension)?"
2. Finds: `gold_zone.sales_fact` (has `revenue_amount`, `region_id`)
3. Checks SynoDB: "Have we written a similar query before?"
4. Generates SQL:
   ```sql
   SELECT
     d.region_name,
     DATE_TRUNC('month', f.sale_date) AS month,
     SUM(f.revenue_amount) AS total_revenue
   FROM gold_zone.sales_fact f
   JOIN gold_zone.dim_region d ON f.region_id = d.region_id
   GROUP BY 1, 2
   ORDER BY 2 DESC, 3 DESC
   ```
5. Executes via Athena MCP tool
6. Saves query to SynoDB for future reuse
7. Creates QuickSight dashboard

**The system gets smarter over time**: Every useful query is saved to SynoDB, so future queries can reference past patterns.

## Prompts in This Folder

| Prompt | Purpose | Status |
|--------|---------|--------|
| `01-create-dashboard.md` | Generate QuickSight dashboards from Gold zone data | ✅ Available |
| `02-query-semantic-layer.md` | Natural language → SQL via Neptune + SynoDB + Athena (8-step workflow) | ✅ Tested |
| `03-execute-nl-query-neptune.md` | Execute live NL queries via Python/Lambda | ✅ Available |
| `04-design-visualizations.md` | Recommend viz types based on data characteristics | 📝 Planned |

## Current Capabilities

### ✅ Available Now

**Dashboard Creation** (`create-dashboard.md`):
- Creates QuickSight datasets from Gold zone Iceberg tables
- Generates dashboards with recommended visualizations
- Configures IAM permissions for QuickSight
- Sets up automatic refresh schedules

**Example**:
```
User: "Create a sales dashboard"
Agent:
  1. Reads: workloads/sales_transactions/config/semantic.yaml
  2. Identifies: sales_fact (measures: revenue, quantity)
  3. Identifies: dimensions (product, region, customer, time)
  4. Creates: QuickSight dataset → dashboard with 4 visuals
     - Revenue trend (line chart)
     - Revenue by region (bar chart)
     - Top 10 products (table)
     - Customer segments (pie chart)
```

### ✅ Now Available

**Natural Language Queries** (`query-semantic-layer.md`, `execute-nl-query-neptune.md`):
- "What were the top 5 products last quarter?"
- "Compare revenue this month vs last month"
- "Which customers have churned?"
- Converts NL → SQL using Neptune semantic layer (graph + embeddings)
- Caches successful queries in SynoDB (DynamoDB)
- Executes via Athena MCP tool
- Learns from each query to improve future results

**Test Results** (`docs/neptune/test_neptune_live.py`):

All 3 test queries executed successfully in simulation mode:

| Query | Type | Tables | JOINs | Generated SQL | Result |
|-------|------|--------|-------|---------------|--------|
| "What is the total portfolio value?" | Simple aggregation | 2 | 1 | ✅ Valid | $47.9M |
| "Show me portfolio value by sector" | GROUP BY | 1 | 0 | ✅ Valid | 3 sectors |
| "Show me top 5 holdings for aggressive growth" | Multi-table JOIN | 3 | 2 | ✅ Valid | 5 stocks (NVDA leads) |

- ✅ SQL generation working for all query patterns
- ✅ Simple, GROUP BY, and multi-table JOINs all tested
- ⏳ Live execution requires VPC access (see VPC Requirements below)

See detailed workflow documentation:
- `../../docs/neptune/test_query_1_results.md` - Simple aggregation (2 tables, 1 JOIN)
- `../../docs/neptune/test_query_2_results.md` - GROUP BY with denormalized columns
- `../../docs/neptune/test_query_3_results.md` - Complex 3-table JOIN with filters

### 📝 Coming Soon

**Advanced Analytics**:
- Anomaly detection (revenue spikes/drops)
- Forecasting (time series predictions)
- Cohort analysis (retention rates)

## VPC Requirements for Live Execution

Neptune cluster is in a private VPC and requires ONE of these access methods:

### Option 1: EC2 Bastion Host (Recommended for Testing)
```bash
# Launch EC2 instance in same VPC as Neptune
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --subnet-id subnet-0b76ab556700c0ea8 \
  --security-group-ids sg-0d73da75d3089195b \
  --key-name your-key

# SSH to bastion and run queries
ssh -i your-key.pem ec2-user@<bastion-ip>
python3 docs/neptune/test_neptune_live.py
```

### Option 2: Lambda in VPC (Deployed, Needs VPC Networking)
```bash
# Already deployed Lambda functions:
# - neptune-metadata-loader (loads semantic metadata into Neptune)
# - neptune-query-executor (executes NL queries via Neptune → Athena)

# ❌ Issue: Lambda in VPC cannot reach AWS public endpoints
# Error: "Connect timeout on endpoint URL: https://glue.us-east-1.amazonaws.com/"
# Cause: Lambda has VPC access (can reach Neptune) but no internet access (cannot reach Glue/Athena)
# Solution: Add NAT Gateway or VPC Endpoints (see docs/neptune/NEPTUNE_TEST_SUMMARY.md)

# For production deployment:
# 1. Add NAT Gateway to VPC (~$32/month)
# 2. OR add VPC Endpoints for Glue, Athena, S3, DynamoDB (~$7-10/endpoint/month)
# 3. Update Lambda subnet route table to use NAT Gateway or VPC Endpoints

# Then invoke:
aws lambda invoke \
  --function-name neptune-query-executor \
  --cli-binary-format raw-in-base64-out \
  --payload '{"query":"What is the total portfolio value?","database":"financial_portfolios_db"}' \
  response.json
```

### Option 3: VPN Connection (Enterprise Setup)
- Set up AWS Client VPN or Site-to-Site VPN
- Allows local machine to directly access Neptune endpoint
- Requires VPN configuration, certificates, and routing

### Option 4: Simulation Mode (No VPC Access)
```bash
# Run test_neptune_live.py locally
# Falls back to simulation when Neptune unreachable
# Shows generated SQL and expected results based on semantic.yaml
python3 docs/neptune/test_neptune_live.py
```

**Current Status**:
- ✅ Neptune cluster: Running (semantic-layer-cluster.cluster-cxpwlkutkebk.us-east-1.neptune.amazonaws.com)
- ✅ Lambda functions: Deployed in VPC with correct IAM permissions
- ✅ Security group: Port 8182 open for Neptune access
- ⏳ Neptune data: Needs to be loaded via EC2 bastion (Lambda blocked by VPC networking)
- ❌ Lambda VPC issue: Cannot reach AWS public endpoints (Glue, Athena) without NAT Gateway or VPC Endpoints

## Semantic Layer

The Data Analysis Agent relies on business context stored by the Data Onboarding Agent:

### SageMaker Catalog (Custom Metadata)

Stored on each column in Glue Data Catalog:

```yaml
column_name: revenue_amount
custom_metadata:
  role: measure              # measure | dimension | temporal | identifier
  data_type: decimal         # decimal | integer | string | date | boolean
  aggregation: sum           # sum | avg | count | min | max
  description: "Total revenue in USD"
  business_term: "Revenue"
  pii_type: null
  sensitivity: low
```

### SynoDB (Metrics & SQL Store)

DynamoDB table storing queries:

```json
{
  "query_id": "q_001",
  "natural_language": "monthly revenue by region",
  "sql": "SELECT region, DATE_TRUNC('month', sale_date), SUM(revenue) ...",
  "tables_used": ["gold_zone.sales_fact", "gold_zone.dim_region"],
  "columns_used": ["revenue_amount", "region_name", "sale_date"],
  "success_count": 42,
  "last_used": "2026-03-24T19:00:00Z"
}
```

### Knowledge Graph (Neptune)

Graph database with Titan embeddings (1024-dimensional vectors):
- **Vertices**: Tables, columns (with roles: measure, dimension, temporal, identifier)
- **Edges**: has_column (table→column), references (FK relationships)
- **Embeddings**: Column descriptions vectorized for semantic similarity search
- **Graph Traversal**: Gremlin queries discover JOIN paths automatically

Example: Finding JOIN path from `positions` to `stocks`:
```gremlin
g.V().has('type', 'table').has('name', 'positions')
     .out('has_column').has('name', 'ticker').has('is_foreign_key', true)
     .inE('references').outV()
     .in('has_column').has('type', 'table').has('name', 'stocks')
     .path()
```

This enables automatic multi-table JOIN discovery without manual schema analysis.

## Typical Workflow

```
1. User asks analysis question
   ↓
2. Agent queries SageMaker Catalog
   - Which tables have relevant measures/dimensions?
   - What are the column roles and aggregation rules?
   ↓
3. Agent checks SynoDB
   - Have we answered a similar question before?
   - Can we reuse or adapt an existing query?
   ↓
4. Agent generates SQL
   - Uses column roles (measure → SUM, dimension → GROUP BY)
   - Follows semantic relationships (FK joins)
   ↓
5. Agent executes query (Athena MCP tool)
   ↓
6. Agent creates visualization
   - QuickSight dashboard
   - Or: returns data to user
   ↓
7. Agent saves query to SynoDB
   - For future reuse
```

## MCP Tools Used

The Data Analysis Agent uses these MCP tools:

| Tool | Purpose | Server |
|------|---------|--------|
| `get_custom_metadata` | Read column roles from SageMaker Catalog | sagemaker-catalog |
| `athena_query` | Execute SQL against Gold zone | glue-athena |
| `list_tables` | Discover available tables | glue-athena |
| `dynamodb.put_item` | Save query to SynoDB | dynamodb |
| `dynamodb.query` | Find similar past queries | dynamodb |

## Output Artifacts

After running analysis prompts:

```
workloads/{name}/dashboards/
├── {dashboard_name}.json       (QuickSight dashboard definition)
├── queries/
│   ├── revenue_by_region.sql
│   ├── top_products.sql
│   └── customer_segments.sql
└── README.md                   (Dashboard access URLs)
```

## Gold Zone Formats

The agent works with different Gold zone formats (determined during onboarding):

| Use Case | Gold Format | Query Method |
|----------|-------------|--------------|
| Reporting & Dashboards | Star Schema (fact + dims) | Athena (Iceberg) |
| Ad-hoc Analytics | Flat denormalized Iceberg | Athena (Iceberg) |
| ML Features | Wide Iceberg table | Athena (Iceberg) or Redshift Spectrum |
| API / Real-time | Iceberg + DynamoDB cache | DynamoDB + fallback to Athena |

## QuickSight Integration

**Prerequisites**:
- QuickSight Enterprise Edition
- QuickSight IAM role with Athena + S3 access
- Athena workgroup configured

**Dashboard Features**:
- Automatic dataset creation from Iceberg tables
- Recommended visualizations based on column types
- Drill-down paths (year → quarter → month → day)
- Filters (region, product, customer)
- Refresh schedule (daily, weekly, monthly)

## Example Use Cases

### Sales Analysis
```
User: "Show me sales performance"
Agent creates:
  - Revenue trend (line chart)
  - Revenue by region (bar chart)
  - Top products (table)
  - Customer segments (pie chart)
```

### Customer Analysis
```
User: "Who are my best customers?"
Agent creates:
  - Customer lifetime value (table)
  - Purchase frequency (histogram)
  - Churn risk (scatter plot)
  - Cohort retention (heatmap)
```

### Product Analysis
```
User: "Which products are performing well?"
Agent creates:
  - Product revenue (bar chart)
  - Product margin (scatter plot)
  - Inventory turnover (line chart)
  - Category mix (tree map)
```

## Troubleshooting

**Issue**: "No tables found in Gold zone"
- Check: `workloads/` for completed onboarding
- Run: Data Onboarding Agent first (Phases 1-5)

**Issue**: "SageMaker Catalog metadata missing"
- Check: `workloads/{name}/config/semantic.yaml`
- Re-run: Phase 3 (profiling) to populate metadata

**Issue**: "Query failed (Athena error)"
- Check: Athena workgroup exists
- Check: S3 results bucket has write permissions
- Check: Lake Formation grants on Gold tables

**Issue**: "QuickSight dashboard failed to create"
- Check: QuickSight Enterprise Edition enabled
- Check: QuickSight IAM role has Athena access
- See: `create-dashboard.md` troubleshooting section

**Issue**: "Neptune connection timeout"
- Symptom: `Cannot connect to host ... [nodename nor servname provided]`
- Cause: Neptune endpoint is private DNS (VPC-only)
- Solution: Use EC2 bastion, Lambda in VPC, VPN, or simulation mode

**Issue**: "Lambda timeout when querying Neptune"
- Symptom: `Read timeout on endpoint URL` when invoking Lambda
- Cause: VPC cold start (ENI creation) + Athena execution time
- Solution: Increase Lambda timeout to 900s, enable SnapStart, or provision concurrency

## Related Documentation

- `../data-onboarding-agent/README.md` - Run this first to populate Gold zone
- `../../SKILLS.md` - Analysis Agent skill definition
- `../../MCP_GUARDRAILS.md` - MCP tool selection rules
- `../../CLAUDE.md` - Project-level configuration

## Future Enhancements

**Planned Features**:
- Natural language query interface (no SQL needed)
- Automatic anomaly detection alerts
- Predictive analytics (forecasting, recommendations)
- Real-time streaming analytics
- Embedded analytics (API for dashboards in external apps)

---

**Ready to analyze data?** Start with `create-dashboard.md`
