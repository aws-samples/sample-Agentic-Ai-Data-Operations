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
| `02-query-semantic-layer.md` | Natural language → SQL via Neptune + SynoDB + Athena | ✅ Available |
| `03-design-visualizations.md` | Recommend viz types based on data characteristics | 📝 Placeholder |

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

**Natural Language Queries** (`query-semantic-layer.md`):
- "What were the top 5 products last quarter?"
- "Compare revenue this month vs last month"
- "Which customers have churned?"
- Converts NL → SQL using Neptune semantic layer (graph + embeddings)
- Caches successful queries in SynoDB (DynamoDB)
- Executes via Athena MCP tool
- Learns from each query to improve future results

### 📝 Coming Soon

**Advanced Analytics**:
- Anomaly detection (revenue spikes/drops)
- Forecasting (time series predictions)
- Cohort analysis (retention rates)

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

### Knowledge Graph (OpenSearch)

Vector embeddings for semantic search:
- Find similar queries by meaning (not exact text match)
- Discover related tables/columns
- Suggest drill-down paths

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
