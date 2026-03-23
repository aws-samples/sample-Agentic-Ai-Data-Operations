# 05 — CONSUME: Create Dashboard
> Generate QuickSight dashboard from Gold/Publish zone data with full visual design specification.

## Purpose

Create a QuickSight dashboard definition from curated Gold/Publish zone data. Generates complete configuration including visual design (theme, colors, typography, layout), chart types with styling options, conditional formatting, KPI cards with period-over-period comparison, and permission grants.

**No QuickSight MCP server exists** — deployment uses `aws quicksight` CLI commands or the QuickSight API. The prompt generates `analytics.yaml` (config) + API payload builder (Python utility).

## When to Use

- After ONBOARD (03) is complete and Gold/Publish zone is populated
- After ENRICH (04) if the dashboard spans multiple workloads
- When business users need BI visualization

## Prompt Template

```
Create QuickSight dashboard: [DASHBOARD_NAME]

Description: [Purpose of this dashboard]
Navigation tabs: [Tab names — e.g., "Overview | Trends | Details"]

Data sources (reference exact Gold zone table names):
- Dataset 1:
  - Name: [DATASET_NAME]
  - Gold table: [DATABASE].[TABLE]
  - Mode: [SPICE / DIRECT_QUERY]
  - Reason: [SPICE for small dims, DIRECT_QUERY for large facts]
  - Refresh (if SPICE): [Frequency — e.g., "Daily at 8am after pipeline"]
  - Joins:
    - table: [DATABASE].[TABLE]
      on: [JOIN_KEY]
      type: [LEFT / INNER]

- Dataset 2: ...

Cross-workload joins (if dashboard spans multiple workloads):
- [WORKLOAD_A].customer_id = [WORKLOAD_B].customer_id

Header:
  title: [Dashboard title — large, bold, white on dark]
  subtitle: [1-2 sentence description of what the dashboard shows]
  logo: [Optional — company/team logo image path or URL]
  logo_position: [top-right / top-left]

Visual Design:
  theme: [THEME_NAME — e.g., "Midnight", "Ocean Gradient", "Corporate Dark"]
  background: [HEX — e.g., "#0f172a" dark navy, "#1a1a2e" charcoal]
  card_background: [HEX or rgba — e.g., "rgba(30, 41, 59, 0.85)" frosted glass]
  card_border_radius: [px — e.g., "12px"]
  card_shadow: [CSS shadow — e.g., "0 4px 24px rgba(0,0,0,0.3)"]
  card_padding: [px — e.g., "24px"]
  grid_gap: [px — e.g., "20px"]

  Typography:
    title_font: [font, size, weight, color — e.g., "Inter, 28px, 700, #f1f5f9"]
    subtitle_font: [font, size, weight, color — e.g., "Inter, 14px, 400, #94a3b8"]
    kpi_value_font: [font, size, weight, color — e.g., "Inter, 48px, 800, #f1f5f9"]
    kpi_label_font: [font, size, weight, color — e.g., "Inter, 13px, 500, #94a3b8"]
    chart_title_font: [font, size, weight, color — e.g., "Inter, 16px, 600, #f1f5f9"]
    axis_label_font: [font, size, color — e.g., "Inter, 11px, #64748b"]
    table_header_font: [font, size, weight, color — e.g., "Inter, 12px, 600, #94a3b8"]

  Color Palette:
    primary_dimensions:
      [DIM_VALUE_1]: "[HEX]"    # e.g., EAST: "#38bdf8"
      [DIM_VALUE_2]: "[HEX]"    # e.g., WEST: "#a78bfa"
    categories:
      [CAT_1]: "[HEX]"          # e.g., Electronics: "#60a5fa"
      [CAT_2]: "[HEX]"          # e.g., Clothing: "#f472b6"
    status_indicators:
      positive: "[HEX]"         # e.g., "#34d399" green
      warning: "[HEX]"          # e.g., "#fbbf24" amber
      negative: "[HEX]"         # e.g., "#f87171" red
      neutral: "[HEX]"          # e.g., "#94a3b8" gray
    chart_gridlines: "[HEX]"    # e.g., "rgba(148,163,184,0.15)"
    chart_axis: "[HEX]"         # e.g., "#475569"

Layout:
  type: grid
  columns: [number — e.g., 3]
  row_definitions:
    - row: 1
      description: [What this row shows — e.g., "KPI summary cards"]
      columns: [how many columns in this row]
      height: [px or auto — e.g., "120px"]
    - row: 2
      description: [e.g., "Primary charts — bar + donut + KPI detail"]
      columns: [e.g., 3]
      height: [e.g., "380px"]
    - row: 3
      description: [e.g., "Detail table + trend line chart"]
      columns: [e.g., 2]
      height: [e.g., "400px"]

Visuals:
1. [VISUAL_NAME]:
   - Type: [KPI / Bar Horizontal / Bar Vertical / Bar Stacked / Bar Grouped /
            Line / Multi-Line / Area / Pie / Donut / Heatmap / Table / Pivot Table /
            Gauge / Funnel / Waterfall / Treemap / Scatter]
   - Grid position: [row, col, col_span — e.g., "row 2, col 1, span 1"]
   - Dataset: [DATASET_NAME]
   - Measures: [Aggregations — e.g., "SUM(revenue) AS total_revenue"]
   - Dimensions: [Group by — e.g., "region, category"]
   - Sort: [field + direction — e.g., "total_revenue DESC"]
   - Filters: [Default filters — e.g., "status IN ('active', 'completed')"]
   - Limit: [Optional — max rows/bars, e.g., 10]
   - Description: [What insight does this show?]
   - Chart-specific options:
     [See Chart Type Reference below]

2. [VISUAL_NAME]: ...

Conditional Formatting:
  - field: [COLUMN_NAME]
    rules:
      - condition: [e.g., ">= 90"]
        color: [HEX — e.g., "#34d399"]
        icon: [Optional — circle, arrow_up, arrow_down, flag]
      - condition: [e.g., "50 to 89"]
        color: [HEX]
        icon: [Optional]
      - condition: [e.g., "< 50"]
        color: [HEX]
        icon: [Optional]
        highlight_row: [true/false — highlight entire row for worst values]

  - field: [period_over_period delta column]
    rules:
      - condition: "positive"
        color: "#34d399"
        prefix: "increased by "
      - condition: "negative"
        color: "#f87171"
        prefix: "decreased by "

KPI Cards:
  - id: [KPI_ID]
    value: [Aggregation — e.g., "COUNT(DISTINCT order_id)"]
    label: [Display label — e.g., "Total Orders"]
    format: [number / currency / percent]
    prefix: [Optional — e.g., "$"]
    suffix: [Optional — e.g., "%", " days"]
    comparison:
      type: [period_over_period / target / none]
      baseline: [previous_period / fixed_value]
      show_delta: [true/false]
      show_delta_pct: [true/false]
      positive_is_good: [true/false — determines green/red coloring]

Permissions:
- Group: [GROUP_NAME], access: [VIEWER / AUTHOR / ADMIN]

Output:
1. Create [WORKLOAD]/config/analytics.yaml with full dashboard definition
2. Create shared/utils/quicksight_dashboard.py (validate config + generate API payload)
3. Create tests for config validation + payload generation
4. Update README.md with dashboard documentation
```

## Chart Type Reference

Use these in the `Chart-specific options` section of each visual:

| Chart Type | Key Options |
|---|---|
| **KPI** | `value_font_size`, `comparison_type` (period_over_period / target), `sparkline` (true/false), `delta_color_positive`, `delta_color_negative` |
| **Bar Horizontal** | `bar_color_by` (dimension/fixed), `bar_border_radius` (px), `bar_thickness` (px), `scale` (linear/logarithmic), `show_values` (true/false), `value_position` (end/inside) |
| **Bar Vertical / Stacked / Grouped** | `bar_color_by`, `bar_border_radius`, `stack_by` (dim), `group_by` (dim), `show_values`, `legend_position` (top/right/bottom) |
| **Donut / Pie** | `cutout_pct` (0=pie, 60-75=donut), `center_label` (total text), `center_font_size` (px), `show_segment_labels`, `show_percentages`, `legend_position` |
| **Line / Multi-Line** | `line_tension` (0=angular, 0.4=smooth), `point_radius` (px), `line_width` (px), `fill_area`, `show_markers`, `legend_position`, `series_colors` (map) |
| **Table** | `striped_rows`, `row_background`, `row_alt_background`, `header_background`, `header_font_color`, `hover_highlight`, `conditional_columns`, `status_dots` (column + color map) |
| **Heatmap** | `color_scale` (sequential/diverging), `min_color`, `max_color`, `null_color`, `show_values` |
| **Gauge** | `min_value`, `max_value`, `target_value`, `bands` (list of {from, to, color}), `needle_color` |
| **Treemap** | `size_by` (measure), `color_by` (measure/dim), `show_labels` |
| **Scatter** | `x_axis` (measure), `y_axis` (measure), `size_by` (measure), `color_by` (dimension), `show_trend_line` |

## Visual Design Best Practices

Based on production QuickSight dark-theme dashboards:

| Element | Guideline |
|---|---|
| **Background** | Dark (#0f172a to #1a1a2e) reduces eye strain, makes data pop |
| **Cards** | Semi-transparent (rgba 0.6-0.85 alpha) for depth; 8-16px border-radius |
| **KPI Numbers** | 40-56px bold, white (#f1f5f9); label below in muted gray (#94a3b8) |
| **Period Comparison** | Show delta: "decreased by 28.34% (-1,386)" in red, or "increased by X%" in green |
| **Bar Charts** | Horizontal for category comparison (easy label reading); 4px border-radius; logarithmic scale for wide value ranges |
| **Donut Charts** | 60-75% cutout; large center number showing total; segment labels with percentages outside |
| **Line Charts** | 2-3px width; subtle markers on points; area fill only for single series |
| **Tables** | Dark striped rows; colored status dots next to category names; red highlight on worst-performing row |
| **Conditional Formatting** | Colored dots (green/amber/red) for status; highlight cell or row for critical values |
| **Legends** | Right or top position; match colors to series; truncate long labels with ellipsis |
| **Grid Lines** | Very subtle (10-15% opacity white); no vertical grid lines on bar charts |
| **Font Stack** | Inter > system-ui > -apple-system for clean typography |
| **Color Limit** | Max 7-8 distinct colors per chart; use opacity variants for related values |
| **Header** | Large bold title (28-36px), gray subtitle (14px), optional logo top-right |
| **Tabs** | Navigation tabs for multi-page dashboards (Overview, Trends, Details) |

## Parameters

| Parameter | Description | Example |
|---|---|---|
| `DASHBOARD_NAME` | Display name | "Executive Sales Dashboard" |
| `Purpose` | What it's for | "High-level KPIs for executive team" |
| `Gold table` | Source table | `gold_db.daily_sales_summary` |
| `SPICE/DIRECT_QUERY` | Import mode | SPICE for small, DIRECT_QUERY for large |
| `Visual type` | Chart type | KPI, Bar Horizontal, Donut, Multi-Line, Table |
| `Measures` | Aggregated values | `SUM(revenue)` |
| `Dimensions` | Grouping columns | `category, sales_channel` |
| `Filters` | Default WHERE | `fulfillment_status = 'Delivered'` |
| `theme` | Color theme name | "Midnight Executive", "Ocean Gradient" |
| `background` | Page background HEX | "#1a1a2e" (charcoal), "#0f172a" (navy) |
| `card_background` | Card fill | "rgba(30,41,59,0.85)" (frosted glass) |
| `Typography` | Font specs per element | "Inter, 48px, 800, #f1f5f9" for KPI values |
| `Color Palette` | Dimension → color map | `{EAST: "#38bdf8", WEST: "#a78bfa"}` |
| `Layout` | Grid structure | 3 columns, 3 rows with height specs |
| `Conditional Formatting` | Rules per field | `>= 90 → green dot, < 50 → red dot` |
| `KPI comparison` | Period delta config | period_over_period, show %, positive=green |
| `Permissions` | Access control | Executives group, VIEWER access |
| `Refresh schedule` | SPICE timing | "Daily at 7:30am after Gold zone load" |

## Expected Output

1. `config/analytics.yaml` — full dashboard definition with visual design, layout, chart configs
2. `shared/utils/quicksight_dashboard.py` — config validator + QuickSight API payload generator
3. Tests for config validation and payload generation
4. Updated README.md with dashboard documentation

## Deployment

No QuickSight MCP server is available. Deploy via CLI in this exact order:

### Prerequisites (do these FIRST or everything fails)

```bash
# 1. Find QuickSight user (NOT Admin/{region} — look up the actual user)
aws quicksight list-users --aws-account-id ACCOUNT_ID --namespace default --region REGION
# Use the UserName and Arn from the output for all --permissions below

# 2. Grant QuickSight service role S3 + Athena + Glue + LF access
#    The default AWSQuickSightS3Policy is often a deny-all placeholder.
#    Without this, data source creation fails: "Unable to verify/create output bucket"
aws iam put-role-policy \
  --role-name aws-quicksight-service-role-v0 \
  --policy-name DataLakeAccess \
  --policy-document '{
    "Version":"2012-10-17",
    "Statement":[
      {"Effect":"Allow","Action":["s3:GetObject","s3:ListBucket","s3:GetBucketLocation",
        "s3:PutObject","s3:ListBucketMultipartUploads","s3:ListMultipartUploadParts",
        "s3:AbortMultipartUpload"],
       "Resource":["arn:aws:s3:::BUCKET","arn:aws:s3:::BUCKET/*"]},
      {"Effect":"Allow","Action":["athena:StartQueryExecution","athena:GetQueryExecution",
        "athena:GetQueryResults","athena:StopQueryExecution","athena:GetWorkGroup"],
       "Resource":"*"},
      {"Effect":"Allow","Action":["glue:GetTable","glue:GetTables","glue:GetDatabase",
        "glue:GetDatabases","glue:GetPartitions"],"Resource":"*"},
      {"Effect":"Allow","Action":["lakeformation:GetDataAccess"],"Resource":"*"}
    ]}'

# 3. If tables have LF-Tags (TBAC), grant QuickSight service role access to tag values
#    Without this: "database generated SQL exception" in dashboard visuals
aws lakeformation grant-permissions \
  --principal '{"DataLakePrincipalIdentifier":"arn:aws:iam::ACCOUNT:role/service-role/aws-quicksight-service-role-v0"}' \
  --permissions SELECT DESCRIBE \
  --resource '{"LFTagPolicy":{"ResourceType":"TABLE","Expression":[{"TagKey":"PII_Classification","TagValues":["NONE","LOW","MEDIUM"]}]}}' \
  --region REGION
# Repeat for Data_Sensitivity and PII_Type tags

# 4. Grant QuickSight service role DESCRIBE on the database
aws lakeformation grant-permissions \
  --principal '{"DataLakePrincipalIdentifier":"arn:aws:iam::ACCOUNT:role/service-role/aws-quicksight-service-role-v0"}' \
  --permissions DESCRIBE \
  --resource '{"Database":{"Name":"DATABASE_NAME"}}' \
  --region REGION
```

### Create QuickSight Resources (in order — each depends on the previous)

```bash
# Step 1: Data source (Athena connection)
aws quicksight create-data-source \
  --aws-account-id ACCOUNT_ID \
  --data-source-id {workload}_athena_source \
  --name "{Workload} - Athena" \
  --type ATHENA \
  --data-source-parameters '{"AthenaParameters":{"WorkGroup":"WORKGROUP_NAME"}}' \
  --permissions '[{"Principal":"QS_USER_ARN","Actions":["quicksight:DescribeDataSource","quicksight:DescribeDataSourcePermissions","quicksight:PassDataSource","quicksight:UpdateDataSource","quicksight:DeleteDataSource","quicksight:UpdateDataSourcePermissions"]}]'
# VERIFY status is CREATION_SUCCESSFUL before proceeding:
aws quicksight describe-data-source --aws-account-id ACCOUNT_ID --data-source-id {workload}_athena_source --query 'DataSource.Status'

# Step 2: Datasets (one per Gold table, use CustomSql with explicit column list)
aws quicksight create-data-set \
  --aws-account-id ACCOUNT_ID \
  --data-set-id {workload}_{table} \
  --name "{Workload} - {Table}" \
  --import-mode DIRECT_QUERY \
  --physical-table-map '{"t1":{"CustomSql":{"DataSourceArn":"DATA_SOURCE_ARN","Name":"{table}","SqlQuery":"SELECT col1, col2, ... FROM db.table","Columns":[{"Name":"col1","Type":"STRING"},...]}}}'
  --permissions '[...]'

# Step 3: Analysis (use --definition with DataSetIdentifierDeclarations + Sheets + Visuals)
aws quicksight create-analysis \
  --aws-account-id ACCOUNT_ID \
  --analysis-id {workload}_analysis \
  --name "{Workload} Analysis" \
  --definition file://definition.json \
  --permissions '[...]'

# Step 4: Dashboard (same --definition as analysis)
aws quicksight create-dashboard \
  --aws-account-id ACCOUNT_ID \
  --dashboard-id {workload}_dashboard \
  --name "{Workload} Dashboard" \
  --definition file://definition.json \
  --permissions '[...]'
```

### Known Issues (from production deployment)

| Issue | Symptom | Fix |
|-------|---------|-----|
| **S3 deny-all policy** | Data source: "Unable to verify/create output bucket" | Add inline S3+Athena+Glue policy to QS service role |
| **Missing TBAC grants** | Dashboard: "database generated SQL exception" | Grant QS service role LF-Tag permissions |
| **Wrong QS username** | describe_user fails, script exits silently | Use `list-users` to find actual username |
| **Orphaned datasets** | Deleting data source breaks datasets | Must recreate datasets + analysis + dashboard (full chain) |
| **source-entity vs definition** | CLI error on create-analysis | Use `--definition file://` (not `--source-entity`) for programmatic creation |

## Validation

```bash
# Check analytics.yaml created with visual design section
cat workloads/{name}/config/analytics.yaml
# Expected: Full config with color_scheme, layout, visuals, conditional_formatting

# Verify dashboard accessible
aws quicksight describe-dashboard \
  --aws-account-id ACCOUNT_ID \
  --dashboard-id DASHBOARD_ID
# Expected: Dashboard details JSON

# Verify theme applied
aws quicksight describe-theme \
  --aws-account-id ACCOUNT_ID \
  --theme-id THEME_ID
# Expected: Theme with dark background, font overrides

# Check SPICE refresh
aws quicksight describe-ingestion \
  --aws-account-id ACCOUNT_ID \
  --data-set-id DATASET_ID
# Expected: Refresh schedule configured
```
