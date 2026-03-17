# Prompt Examples: Real-World Data Onboarding

> These are complete, ready-to-use examples of the modular prompts filled out with realistic data scenarios.
> Each ONBOARD example includes a full **Semantic Layer** section that enables the AI Analysis Agent to derive correct SQL from natural language questions.

---

## Example 1: Onboard Customer Master Data

### Context
You have a CSV file with customer demographic and contact information that needs to be loaded into your data warehouse.

### Prompt
```
Check if data from customer master records has already been onboarded.

Source details:
- Location: s3://prod-data-lake/raw/crm/customers_export.csv
- Format: CSV
- Description: Customer demographic data including contact info, segment classification, and account status

Report: existing workload status or confirm new data.
```

**If not found, follow with:**

```
Onboard new dataset: customer_master

Source:
- Type: S3
- Location: s3://prod-data-lake/raw/crm/customers_export.csv
- Format: CSV (pipe-delimited)
- Frequency: Daily (extracted from CRM at 5am)
- Credentials: arn:aws:secretsmanager:us-east-1:123456789012:secret:data-pipeline/crm-readonly
- Estimated size: 5 GB, ~2M rows

Schema:
- customer_id: STRING, unique customer identifier, identifier
- first_name: STRING, customer first name, dimension
- last_name: STRING, customer last name, dimension
- email: STRING, email address, dimension (PII)
- phone: STRING, phone number, dimension (PII)
- address: STRING, street address, dimension (PII)
- city: STRING, city, dimension
- state: STRING, state/province code, dimension
- postal_code: STRING, ZIP/postal code, dimension
- country: STRING, country code (ISO 3166), dimension
- segment: ENUM, customer segment (Enterprise/SMB/Individual), dimension
- industry: STRING, customer industry vertical, dimension
- join_date: DATE, account creation date, temporal
- last_purchase_date: DATE, most recent order date, temporal
- status: ENUM, account status (Active/Inactive/Churned), dimension
- lifetime_value: DECIMAL(15,2), total historical revenue, measure
- credit_limit: DECIMAL(15,2), approved credit limit, measure

Semantic Layer (for AI Analysis Agent):

  Fact table grain: One row per customer (snapshot — current state, not events)

  Measures (with aggregation semantics):
  - lifetime_value: SUM (when aggregating across customers) / AVG (when comparing segments) - "Total historical revenue from this customer" - unit: USD
  - credit_limit: AVG - "Approved credit limit, SUM is meaningless across customers" - unit: USD
  - (derived) customer_count: COUNT DISTINCT customer_id - "Number of unique customers"
  - (derived) active_pct: COUNT(status='Active') / COUNT(*) - "Percentage of active customers"

  Dimensions (with allowed values):
  - segment: "Customer business size tier" - values: [Enterprise, SMB, Individual]
  - industry: "Customer industry vertical" - values: ~25 industries (Technology, Healthcare, Finance, Retail, Manufacturing, etc.)
  - country: "Customer country (ISO code)" - values: ~40 countries, top: [US, UK, CA, DE, FR]
  - state: "State/province code" - values: US states + international provinces
  - city: "Customer city" - values: ~500 cities (high cardinality)
  - status: "Account lifecycle status" - values: [Active, Inactive, Churned]

  Temporal:
  - join_date: "Date customer account was created" - grain: day - primary: YES
  - last_purchase_date: "Date of most recent order" - grain: day - primary: NO (nullable for customers with no orders)

  Identifiers:
  - customer_id: "Unique customer identifier" - role: PK

  Derived columns:
  - name_concat = first_name || ' ' || last_name - "Full customer name, computed at Silver zone"

  Dimension hierarchies:
  - geography: country -> state -> city (drill from country to city)
  - customer_tier: segment (flat — Enterprise > SMB > Individual by value)
  - time: year -> quarter -> month -> day (on join_date)

  Default filters:
  - "Customer count" -> WHERE status IN ('Active', 'Inactive') (exclude churned unless explicitly asked)
  - "Active customers" -> WHERE status = 'Active'
  - "All customers" -> no filter (when user says "all" or "including churned")
  - "New customers" -> WHERE join_date >= DATE_TRUNC('month', CURRENT_DATE)

  Business terms & synonyms:
  - "customers" / "clients" / "accounts" / "users": COUNT(DISTINCT customer_id) - "Unique customer records"
  - "churn rate" / "attrition": COUNT(status='Churned') / COUNT(*) - "Percentage of customers who churned"
  - "retention rate": 1 - churn_rate - "Percentage of customers retained"
  - "LTV" / "lifetime value" / "CLV" / "customer lifetime value": SUM(lifetime_value) or AVG(lifetime_value) per segment
  - "new customers" / "acquisitions": COUNT(*) WHERE join_date in period
  - "enterprise" / "large accounts": WHERE segment = 'Enterprise'
  - "SMB" / "small business" / "mid-market": WHERE segment = 'SMB'
  - "tenure" / "customer age": DATEDIFF(CURRENT_DATE, join_date) - "Days since account creation"
  - "dormant" / "inactive": WHERE status = 'Inactive'

  Time intelligence:
  - Fiscal year start: January
  - Week starts on: Monday
  - Common comparisons: MoM, QoQ, YoY (customer count growth), cohort analysis by join_date
  - Timezone: UTC

  Data freshness:
  - Refresh frequency: Daily (batch at 6am UTC)
  - Latest data available: T-1 day
  - "Customer status reflects end-of-day yesterday. Today's churns won't appear until tomorrow."

  Seed questions (what business users will ask):
  1. "How many active customers do we have?" -> COUNT(DISTINCT customer_id) WHERE status='Active'
  2. "Customer count by segment?" -> COUNT(*) GROUP BY segment WHERE status IN ('Active','Inactive')
  3. "Average lifetime value by segment?" -> AVG(lifetime_value) GROUP BY segment
  4. "Monthly new customer trend?" -> COUNT(*) GROUP BY DATE_TRUNC('month', join_date) ORDER BY month
  5. "Churn rate this quarter?" -> COUNT(status='Churned') / COUNT(*) WHERE join_date < quarter_start
  6. "Top 10 customers by lifetime value?" -> ORDER BY lifetime_value DESC LIMIT 10
  7. "Customer distribution by country?" -> COUNT(*) GROUP BY country ORDER BY count DESC
  8. "Enterprise vs SMB average LTV?" -> AVG(lifetime_value) GROUP BY segment WHERE segment IN ('Enterprise','SMB')

  Data steward:
  - Owner: CRM Team / Customer Success
  - Domain: Customer
  - Sensitivity: Confidential (contains PII: email, phone, address)

Bronze:
- Keep raw format: YES (preserve original pipe-delimited CSV)
- Partitioning: By ingestion date (year=YYYY/month=MM/day=DD)
- Retention: 365 days

Silver:
- Cleaning:
  - Deduplicate on: customer_id (keep most recent by join_date)
  - Handle nulls: KEEP email/phone nulls (optional fields), DROP if customer_id null
  - Type casting: join_date STRING -> DATE, last_purchase_date STRING -> DATE
  - Standardization: state -> uppercase, country -> ISO 3166-1 alpha-2
  - PII masking: email (SHA256 hash), phone (mask middle 6 digits), address (drop from Silver)
  - Validation: segment IN (Enterprise, SMB, Individual), status IN (Active, Inactive, Churned)
- Format: Apache Iceberg
- Partitioning: By country, segment (for access control)

Gold:
- Use case: Reporting & Customer Analytics
- Format: Star Schema
  - Fact: customer_activity (customer_id, join_date, last_purchase_date, lifetime_value, order_count)
  - Dimension: dim_customer (customer_id, name_concat, segment, industry, country, status)
  - Dimension: dim_geography (country, state, city, region_grouping)
  - Aggregate: customer_summary_by_segment (segment, customer_count, avg_lifetime_value, active_pct)
- Quality threshold: 95%

Quality Rules:
- Completeness: customer_id, first_name, last_name, segment, country, status must be non-null (98%)
- Uniqueness: customer_id must be unique in Silver/Gold (100%)
- Validity: email matches regex, phone matches format, country in ISO list
- Accuracy: lifetime_value >= 0, join_date <= current_date, segment in enum
- Consistency: last_purchase_date >= join_date (if not null)
- Critical rules: customer_id uniqueness, non-null segment, valid status enum

Schedule:
- Frequency: 0 6 * * * (daily at 6am UTC)
- Dependencies: None (source system runs at 5am)
- SLA: 90 minutes
- Failure handling: Retry 3 times (5min, 10min, 20min backoff), alert data-engineering@company.com

Build complete pipeline with tests.
```

---

## Example 2: Onboard Transaction Data with Foreign Key

### Context
You have daily transaction logs from an e-commerce platform. Each transaction references a customer_id from the customer_master workload.

### Prompt
```
Check if data from e-commerce transaction logs has already been onboarded.

Source details:
- Location: s3://prod-data-lake/raw/transactions/daily/
- Format: JSON (newline-delimited)
- Description: E-commerce order transactions including product details, pricing, and fulfillment status

Report: existing workload status or confirm new data.
```

**If not found:**

```
Onboard new dataset: order_transactions

Source:
- Type: S3
- Location: s3://prod-data-lake/raw/transactions/daily/*.json
- Format: JSON (newline-delimited, gzip compressed)
- Frequency: Hourly (new files every hour)
- Credentials: arn:aws:secretsmanager:us-east-1:123456789012:secret:data-pipeline/ecommerce-readonly
- Estimated size: 50 GB/day, ~10M transactions/day

Schema:
- transaction_id: STRING, unique transaction identifier (UUID), identifier
- customer_id: STRING, FK to customer_master.customer_id, identifier
- order_date: TIMESTAMP, transaction timestamp (UTC), temporal
- product_sku: STRING, product stock keeping unit, dimension
- product_name: STRING, product display name, dimension
- category: STRING, product category, dimension
- quantity: INTEGER, units purchased, measure
- unit_price: DECIMAL(10,2), price per unit (USD), measure
- discount_amount: DECIMAL(10,2), discount applied (USD), measure
- tax_amount: DECIMAL(10,2), sales tax (USD), measure
- shipping_amount: DECIMAL(10,2), shipping fee (USD), measure
- total_amount: DECIMAL(10,2), final charged amount (USD), measure
- payment_method: ENUM, payment type (Credit Card/PayPal/Wire Transfer), dimension
- fulfillment_status: ENUM, order status (Pending/Shipped/Delivered/Cancelled/Returned), dimension
- warehouse_id: STRING, fulfillment warehouse, dimension
- sales_channel: ENUM, order source (Web/Mobile App/API/Retail), dimension
- promo_code: STRING, promotion code used (nullable), dimension

Semantic Layer (for AI Analysis Agent):

  Fact table grain: One row per transaction (one order, not per line item)

  Measures (with aggregation semantics):
  - revenue: SUM - "Net revenue = total_amount - tax_amount - shipping_amount" - unit: USD
  - total_amount: SUM - "Gross charged amount including tax and shipping" - unit: USD
  - quantity: SUM - "Total units purchased" - unit: count
  - unit_price: AVG - "Average price per unit across orders (SUM is meaningless)" - unit: USD
  - discount_amount: SUM - "Total discount given" - unit: USD
  - tax_amount: SUM - "Total sales tax collected" - unit: USD
  - shipping_amount: SUM - "Total shipping fees" - unit: USD
  - (derived) order_count: COUNT DISTINCT transaction_id - "Number of unique orders"
  - (derived) avg_order_value: SUM(revenue) / COUNT(DISTINCT transaction_id) - "AOV"
  - (derived) items_per_order: SUM(quantity) / COUNT(DISTINCT transaction_id) - "Average basket size in units"

  Dimensions (with allowed values):
  - category: "Product category" - values: [Electronics, Clothing, Home & Garden, Books, Sports, Groceries]
  - product_name: "Product display name" - values: ~2000 products (high cardinality)
  - product_sku: "Product SKU code" - values: ~2000 SKUs (high cardinality)
  - payment_method: "Payment type" - values: [Credit Card, PayPal, Wire Transfer]
  - fulfillment_status: "Order lifecycle status" - values: [Pending, Shipped, Delivered, Cancelled, Returned]
  - warehouse_id: "Fulfillment center" - values: [WH-EAST, WH-WEST, WH-CENTRAL, WH-SOUTH]
  - sales_channel: "How order was placed" - values: [Web, Mobile App, API, Retail]
  - promo_code: "Promotion code" - values: ~50 codes (nullable, 60% null = no promo)

  Temporal:
  - order_date: "When the order was placed (UTC)" - grain: hour (timestamp) - primary: YES

  Identifiers:
  - transaction_id: "Unique order identifier (UUID)" - role: PK
  - customer_id: "FK to customer_master" - role: FK - references: customer_master.customer_id

  Derived columns:
  - revenue = total_amount - tax_amount - shipping_amount - "Net revenue, computed at Silver zone"

  Dimension hierarchies:
  - product_hierarchy: category -> product_name (drill from category to individual products)
  - fulfillment_funnel: Pending -> Shipped -> Delivered (ordered lifecycle stages)
  - time: year -> quarter -> month -> week -> day -> hour (standard calendar on order_date)

  Default filters:
  - "Revenue queries" -> WHERE fulfillment_status = 'Delivered' (only count delivered revenue)
  - "Order count" -> WHERE fulfillment_status NOT IN ('Cancelled', 'Returned') (exclude cancelled and returned)
  - "All orders" -> no filter (when user explicitly says "all" or "including cancelled")
  - "Returns" -> WHERE fulfillment_status = 'Returned'
  - "Cancellations" -> WHERE fulfillment_status = 'Cancelled'

  Business terms & synonyms:
  - "sales" / "revenue" / "income" / "turnover": SUM(revenue) WHERE fulfillment_status='Delivered' - "Net revenue from delivered orders"
  - "gross revenue" / "gross sales": SUM(total_amount) - "Includes tax and shipping"
  - "AOV" / "average order value" / "basket size": SUM(revenue) / COUNT(DISTINCT transaction_id) - "Average net revenue per order"
  - "order count" / "transactions" / "volume": COUNT(DISTINCT transaction_id)
  - "conversion" / "delivery rate": COUNT(fulfillment_status='Delivered') / COUNT(*) - "% of orders successfully delivered"
  - "cancellation rate" / "cancel rate": COUNT(fulfillment_status='Cancelled') / COUNT(*)
  - "return rate": COUNT(fulfillment_status='Returned') / COUNT(*)
  - "discount rate" / "promo usage": COUNT(promo_code IS NOT NULL) / COUNT(*) - "% of orders using promo codes"
  - "channel" / "source": sales_channel column
  - "warehouse" / "fulfillment center": warehouse_id column
  - "YTD" / "year to date": WHERE order_date >= DATE_TRUNC('year', CURRENT_DATE)
  - "last quarter" / "previous quarter": WHERE order_date >= DATE_TRUNC('quarter', CURRENT_DATE - INTERVAL '3' MONTH) AND order_date < DATE_TRUNC('quarter', CURRENT_DATE)

  Time intelligence:
  - Fiscal year start: January
  - Week starts on: Monday
  - Common comparisons: MoM, QoQ, YoY, WoW, DoD (day-over-day for hourly data)
  - Timezone: UTC (all timestamps stored in UTC)

  Data freshness:
  - Refresh frequency: Hourly (new batch every hour)
  - Latest data available: T-1 hour (current hour is still loading)
  - "Hourly data loads at :15 past. If user asks about this hour, latest complete hour is previous."

  Seed questions (what business users will ask):
  1. "What is total revenue this month?" -> SUM(revenue) WHERE fulfillment_status='Delivered' AND order_date >= DATE_TRUNC('month', CURRENT_DATE)
  2. "Revenue by category?" -> SUM(revenue) GROUP BY category WHERE fulfillment_status='Delivered' ORDER BY revenue DESC
  3. "Daily order volume trend?" -> COUNT(DISTINCT transaction_id) GROUP BY DATE(order_date) ORDER BY date
  4. "Average order value by sales channel?" -> SUM(revenue)/COUNT(DISTINCT transaction_id) GROUP BY sales_channel
  5. "Top 10 products by revenue?" -> SUM(revenue) GROUP BY product_name ORDER BY revenue DESC LIMIT 10
  6. "Cancellation rate by category?" -> COUNT(fulfillment_status='Cancelled')/COUNT(*) GROUP BY category
  7. "Revenue by payment method?" -> SUM(revenue) GROUP BY payment_method WHERE fulfillment_status='Delivered'
  8. "MoM revenue growth?" -> SUM(revenue) per month, LAG window function for growth %
  9. "Which warehouse ships fastest?" -> AVG(DATEDIFF(ship_date, order_date)) GROUP BY warehouse_id
  10. "Promo code effectiveness?" -> AVG(discount_amount), COUNT(*) GROUP BY promo_code WHERE promo_code IS NOT NULL

  Data steward:
  - Owner: E-Commerce Platform Team
  - Domain: Sales / E-Commerce
  - Sensitivity: Internal (contains customer_id FK, no direct PII)

Bronze:
- Keep raw format: YES (preserve original JSON)
- Partitioning: By order_date (year/month/day/hour)
- Retention: 90 days

Silver:
- Cleaning:
  - Deduplicate on: transaction_id (keep first, log duplicates)
  - Handle nulls: DROP if transaction_id/customer_id/order_date null, KEEP promo_code nulls
  - Type casting: All string amounts -> DECIMAL, order_date STRING -> TIMESTAMP
  - Calculate: revenue = total_amount - tax_amount - shipping_amount
  - FK validation: customer_id must exist in customer_master.customer_id (98% threshold)
  - Quarantine: Write failed FK validations to quarantine/invalid_customer_refs/
  - Validation: quantity > 0, unit_price > 0, total_amount > 0
  - Consistency: total_amount = (quantity * unit_price) - discount_amount + tax_amount + shipping_amount
- Format: Apache Iceberg
- Partitioning: By order_date (YEAR/MONTH), category (for query optimization)

Gold:
- Use case: Reporting & Dashboards
- Format: Star Schema
  - Fact: transaction_fact (transaction_id, customer_id FK, product_sku FK, order_date, quantity, revenue, total_amount)
  - Dimension: dim_product (product_sku, product_name, category)
  - Dimension: dim_fulfillment (warehouse_id, warehouse_name, region)
  - Aggregate: daily_sales_summary (order_date, category, sales_channel, transaction_count, revenue_sum, avg_order_value)
  - Aggregate: customer_purchase_metrics (customer_id, first_order_date, last_order_date, order_count, lifetime_revenue)
- Quality threshold: 95%

Quality Rules:
- Completeness: transaction_id, customer_id, order_date, product_sku, total_amount non-null (98%)
- Uniqueness: transaction_id unique in Silver/Gold (100%)
- Validity: quantity > 0, unit_price > 0, fulfillment_status in enum
- Accuracy: customer_id exists in customer_master (98% - allow 2% new customers not yet synced)
- Consistency: revenue calculation matches, order_date <= current_timestamp
- Critical rules: transaction_id uniqueness, positive amounts, valid fulfillment_status

Schedule:
- Frequency: 0 */1 * * * (hourly at minute 0)
- Dependencies: Wait for customer_master DAG daily run to complete (ExternalTaskSensor)
- SLA: 45 minutes
- Failure handling: Retry 3 times (2min, 5min, 10min backoff), alert data-engineering@company.com

Build complete pipeline with tests.
```

**Then add the relationship with full join semantics:**

```
Add relationship between workloads:

Source: order_transactions
Target: customer_master

Relationship:
- FK: order_transactions.customer_id -> customer_master.customer_id
- Cardinality: many-to-one (many transactions per customer)
- Join type: left (include transactions even if customer not found, for orphan analysis)
- Description: "Each transaction is placed by one customer; customers can have multiple transactions over time. Enables customer lifetime value, cohort analysis, and segment-based revenue breakdowns."

Integrity:
- Expected validity: 98% (2% may be new customers not yet in daily snapshot)
- Orphan handling: QUARANTINE (write to quarantine/invalid_customer_refs/ with timestamp)
- Nullable FK: NO (customer_id is required on transactions)
- Validation frequency: Every run (hourly)

Join semantics for Analysis Agent:
- When to join:
  - JOIN NEEDED: "revenue by customer segment", "top customers by spend", "churn impact on revenue",
    "enterprise vs SMB order patterns", "customer lifetime value", "cohort analysis"
  - JOIN NOT NEEDED: "total revenue by category" (category is on transactions),
    "order count by channel" (sales_channel is on transactions),
    "daily sales trend" (order_date is on transactions)
- Pre-aggregation:
  - For customer-level metrics: Aggregate transactions FIRST (SUM revenue per customer_id),
    THEN join to customer_master for segment/industry/country
  - For filtering by customer attributes: JOIN first (WHERE customer_master.segment = 'Enterprise'),
    THEN aggregate transactions
- Fan-out warning:
  - Joining customer_master -> transactions is 1:many (one customer row becomes N transaction rows)
  - NEVER SUM(customer.lifetime_value) after joining to transactions -- multiplied by order count!
  - NEVER COUNT(*) for customer count after joining -- use COUNT(DISTINCT customer_id)
  - AVG(customer.credit_limit) after join is WRONG -- each customer counted N times
- Columns available after join:
  - From customer_master: first_name, last_name, segment, industry, country, state, city, status, join_date, lifetime_value
  - Enables: GROUP BY segment, GROUP BY country, WHERE segment = 'Enterprise',
    customer cohort analysis, geographic revenue breakdowns
- Sample joined queries:
  1. "Revenue by customer segment?" -> Agg orders first: SUM(t.revenue) GROUP BY c.segment, JOIN on customer_id, WHERE t.fulfillment_status='Delivered'
  2. "Top 10 customers by lifetime spend?" -> SUM(t.revenue) per customer_id, JOIN for c.name, ORDER BY DESC LIMIT 10
  3. "Enterprise customer order frequency?" -> COUNT(DISTINCT t.transaction_id) / COUNT(DISTINCT c.customer_id) WHERE c.segment='Enterprise'
  4. "Revenue from churned customers?" -> SUM(t.revenue) WHERE c.status='Churned' AND t.fulfillment_status='Delivered'
  5. "New customer acquisition cohort: orders in first 30 days?" -> WHERE t.order_date <= c.join_date + INTERVAL '30' DAY

Update semantic.yaml, transformation scripts, quality rules, DAG with FK validation, tests, README, and SynoDB seed queries.
```

---

## Example 3: Product Inventory Data (Batch + Streaming)

### Context
Product inventory data comes from two sources: nightly batch export and real-time updates from warehouse management system.

### Prompt
```
Onboard new dataset: product_inventory

Source:
- Type: Hybrid (S3 batch + Kinesis stream)
- Batch location: s3://prod-data-lake/raw/inventory/daily/*.parquet
- Stream: arn:aws:kinesis:us-east-1:123456789012:stream/inventory-updates
- Format: Parquet (batch), JSON (stream)
- Frequency: Batch daily at 2am, stream real-time
- Credentials: arn:aws:secretsmanager:us-east-1:123456789012:secret:data-pipeline/inventory-readonly
- Estimated size: Batch 10 GB/day, Stream 1 GB/hour

Schema:
- product_sku: STRING, product identifier, identifier
- warehouse_id: STRING, storage location, dimension
- quantity_on_hand: INTEGER, current stock level, measure
- quantity_reserved: INTEGER, allocated for pending orders, measure
- quantity_available: INTEGER, available to promise (on_hand - reserved), measure
- reorder_point: INTEGER, minimum stock before reorder, measure
- reorder_quantity: INTEGER, standard reorder amount, measure
- last_restock_date: DATE, most recent replenishment, temporal
- snapshot_timestamp: TIMESTAMP, when measurement was taken, temporal
- update_source: ENUM, data origin (Batch/Stream), dimension

Semantic Layer (for AI Analysis Agent):

  Fact table grain: One row per product per warehouse per snapshot (point-in-time inventory reading)

  Measures (with aggregation semantics):
  - quantity_on_hand: SUM (across warehouses for product total) / AVG (across time for trend) - "Current stock units" - unit: count
  - quantity_reserved: SUM (across warehouses) - "Units allocated to pending orders" - unit: count
  - quantity_available: SUM (across warehouses) - "Units available to sell (on_hand - reserved)" - unit: count
  - reorder_point: AVG - "Min stock threshold, AVG across warehouses (SUM is meaningless)" - unit: count
  - reorder_quantity: AVG - "Standard reorder amount (SUM across products is meaningless)" - unit: count
  - (derived) stockout_flag: CASE WHEN quantity_available <= 0 THEN 1 ELSE 0 END - "Is product out of stock?"
  - (derived) days_of_supply: quantity_available / avg_daily_sales - "Days until stockout at current rate"
  - (derived) below_reorder: CASE WHEN quantity_on_hand <= reorder_point THEN 1 ELSE 0 END - "Needs reorder?"

  Dimensions (with allowed values):
  - warehouse_id: "Fulfillment warehouse" - values: [WH-EAST, WH-WEST, WH-CENTRAL, WH-SOUTH]
  - update_source: "How this reading was captured" - values: [Batch, Stream]

  Temporal:
  - snapshot_timestamp: "When inventory was measured" - grain: minute (stream) / day (batch) - primary: YES
  - last_restock_date: "When product was last replenished" - grain: day - primary: NO

  Identifiers:
  - product_sku: "Product identifier" - role: PK (composite with warehouse_id + snapshot_timestamp)

  Derived columns:
  - quantity_available = quantity_on_hand - quantity_reserved - "Computed at Silver zone"

  Dimension hierarchies:
  - warehouse: warehouse_id (flat in this dataset, but could join to warehouse_master for region/country)
  - time: year -> quarter -> month -> week -> day -> hour (on snapshot_timestamp)

  Default filters:
  - "Current inventory" -> latest snapshot per product/warehouse (MAX(snapshot_timestamp) per product_sku + warehouse_id)
  - "Stockouts" -> WHERE quantity_available <= 0
  - "Needs reorder" -> WHERE quantity_on_hand <= reorder_point
  - "Batch data only" -> WHERE update_source = 'Batch' (for daily reports, excludes noisy stream updates)

  Business terms & synonyms:
  - "stock" / "inventory" / "on hand": quantity_on_hand - "Total physical units in warehouse"
  - "available" / "ATP" / "available to promise": quantity_available - "Units not reserved"
  - "reserved" / "allocated" / "held": quantity_reserved - "Units allocated to pending orders"
  - "stockout" / "out of stock" / "OOS": WHERE quantity_available <= 0
  - "reorder" / "needs reorder" / "below minimum": WHERE quantity_on_hand <= reorder_point
  - "fill rate": (orders_fulfilled / orders_received) - requires join to order_transactions
  - "warehouse utilization": quantity_on_hand / warehouse_capacity - requires warehouse_master join

  Time intelligence:
  - Fiscal year start: January
  - Week starts on: Monday
  - Common comparisons: DoD (day-over-day stock changes), WoW, MoM
  - Timezone: UTC
  - Important: For trend queries, use ONLY batch snapshots (daily) not stream (noisy)

  Data freshness:
  - Batch: Daily (loads at 3am UTC), latest = T-1 day
  - Stream: Real-time (5-minute micro-batches), latest = T-5 minutes
  - "For daily reports, use batch data. For alerts and dashboards, use stream data."

  Seed questions (what business users will ask):
  1. "How much stock do we have across all warehouses?" -> SUM(quantity_on_hand) from latest snapshot
  2. "Which products are out of stock?" -> WHERE quantity_available <= 0, latest snapshot
  3. "Products below reorder point?" -> WHERE quantity_on_hand <= reorder_point, COUNT per warehouse
  4. "Inventory value by warehouse?" -> SUM(quantity_on_hand * unit_cost) GROUP BY warehouse_id (needs product_master join)
  5. "Stock trend for product X?" -> quantity_on_hand over time WHERE product_sku = 'X', batch snapshots only
  6. "Which warehouse has the most stockouts?" -> COUNT(stockout_flag=1) GROUP BY warehouse_id
  7. "Days of supply for top products?" -> quantity_available / avg_daily_sales per product
  8. "Restock urgency: products below reorder point with high sales velocity?" -> RANK by (reorder_point - quantity_on_hand) * daily_sales_rate

  Data steward:
  - Owner: Supply Chain / Operations Team
  - Domain: Inventory / Supply Chain
  - Sensitivity: Internal (no PII, but inventory levels are commercially sensitive)

Bronze:
- Keep raw format: YES (separate paths for batch/stream)
- Batch path: bronze_db.inventory_batch/
- Stream path: bronze_db.inventory_stream/
- Partitioning: By snapshot_timestamp (year/month/day/hour)
- Retention: Batch 365 days, Stream 30 days

Silver:
- Cleaning:
  - Merge: Union batch and stream, deduplicate on (product_sku, warehouse_id, snapshot_timestamp)
  - Keep most recent: If duplicate, keep record with latest snapshot_timestamp
  - Handle nulls: FILL reorder_point/reorder_quantity with product defaults, DROP if product_sku null
  - Calculate: quantity_available = quantity_on_hand - quantity_reserved
  - Validate: quantity_on_hand >= 0, quantity_reserved >= 0, quantity_available >= 0
  - Type casting: All timestamps -> standardize to UTC
- Format: Apache Iceberg (enables time-travel for historical inventory queries)
- Partitioning: By snapshot_timestamp (MONTH), warehouse_id

Gold:
- Use case: Real-time inventory dashboards + analytics
- Format: Hybrid (materialized views + aggregates)
  - Current state: inventory_current (latest snapshot per product/warehouse)
  - Historical: inventory_history (time-series for trend analysis)
  - Aggregate: inventory_summary_by_category (category, total_on_hand, total_available, stockout_count)
  - Aggregate: warehouse_capacity (warehouse_id, utilization_pct, products_at_reorder_point)
- Quality threshold: 95%

Quality Rules:
- Completeness: product_sku, warehouse_id, snapshot_timestamp non-null (99%)
- Validity: All quantities >= 0, quantity_available <= quantity_on_hand
- Accuracy: quantity_available = quantity_on_hand - quantity_reserved
- Consistency: snapshot_timestamp <= current_timestamp
- Anomaly detection: Flag if quantity_on_hand drops >50% in 24 hours
- Critical rules: Non-negative quantities, timestamp validity

Schedule:
- Batch DAG: 0 3 * * * (daily at 3am, after batch export completes)
- Stream DAG: Continuous (Kinesis consumer with 5-minute micro-batches)
- Dependencies: None
- SLA: Batch 60 minutes, Stream 10 minutes
- Failure handling: Retry 3 times, alert ops-team@company.com + page for stream failures

Build complete pipeline with tests for both batch and stream paths.
```

---

## Example 4: Create Executive Dashboard

### Context
After onboarding customer_master and order_transactions, create an executive dashboard showing key business metrics.

### Prompt
```
Create QuickSight dashboard: Executive Sales Dashboard

Description: High-level KPIs for executive team showing customer growth, revenue trends, and regional performance

Data sources:
- Dataset 1:
  - Name: customer_metrics
  - Source table: gold_db.customer_summary_by_segment
  - Import mode: SPICE
  - Reason: Small dataset (~100 rows), updates daily, fast dashboard load
  - Refresh schedule: Daily at 7:30am (after Gold zone load)

- Dataset 2:
  - Name: transaction_metrics
  - Source table: gold_db.transaction_fact
  - Import mode: DIRECT_QUERY
  - Reason: Large dataset (10M+ rows), need real-time data
  - Refresh schedule: N/A (live queries)

- Dataset 3:
  - Name: sales_trends
  - Source table: gold_db.daily_sales_summary
  - Import mode: SPICE
  - Reason: Pre-aggregated, 365 days x categories (~10K rows), fast time-series rendering
  - Refresh schedule: Hourly (incremental, append new day)

Visuals:
1. Total Active Customers:
   - Type: KPI
   - Dataset: customer_metrics
   - Measures: SUM(customer_count) WHERE status='Active'
   - Comparison: vs previous period (30 days ago)
   - Filters: status = 'Active'
   - Description: Current count of active customer accounts with MoM growth

2. Monthly Recurring Revenue:
   - Type: KPI
   - Dataset: transaction_metrics
   - Measures: SUM(revenue) WHERE order_date >= CURRENT_DATE - 30
   - Comparison: vs previous month
   - Filters: fulfillment_status = 'Delivered', order_date >= last 30 days
   - Description: Revenue from delivered orders in trailing 30 days

3. Customer Lifetime Value by Segment:
   - Type: Horizontal Bar Chart
   - Dataset: customer_metrics
   - Measures: AVG(lifetime_value)
   - Dimensions: segment (Enterprise, SMB, Individual)
   - Sort: by avg_lifetime_value DESC
   - Filters: status IN ('Active', 'Inactive')
   - Description: Average customer value by business segment

4. Revenue Trend (12 months):
   - Type: Line Chart
   - Dataset: sales_trends
   - Measures: SUM(revenue_sum)
   - Dimensions: order_date (by month)
   - Filters: order_date >= CURRENT_DATE - 365
   - Color: by sales_channel (Web, Mobile, API, Retail)
   - Description: Monthly revenue trend over past year, split by channel

5. Regional Performance:
   - Type: Filled Map (geographic)
   - Dataset: customer_metrics
   - Measures: SUM(customer_count), SUM(lifetime_value)
   - Dimensions: country (ISO code)
   - Color gradient: by lifetime_value
   - Tooltip: country, customer_count, total_revenue
   - Description: Customer distribution and revenue by country

6. Top 10 Products by Revenue:
   - Type: Horizontal Bar Chart
   - Dataset: transaction_metrics
   - Measures: SUM(revenue)
   - Dimensions: product_name
   - Sort: by revenue DESC
   - Limit: 10
   - Filters: order_date >= CURRENT_DATE - 90, fulfillment_status != 'Cancelled'
   - Description: Highest-revenue products in last 90 days

7. Sales Funnel (by Status):
   - Type: Funnel Chart
   - Dataset: transaction_metrics
   - Measures: COUNT(DISTINCT transaction_id)
   - Dimensions: fulfillment_status (in order: Pending -> Shipped -> Delivered)
   - Filters: order_date >= CURRENT_DATE - 30
   - Description: Order fulfillment conversion in last 30 days

8. YoY Growth Table:
   - Type: Pivot Table
   - Dataset: sales_trends
   - Rows: category
   - Columns: YEAR(order_date)
   - Values: SUM(revenue_sum), COUNT(transaction_count)
   - Calculated field: YoY_growth = (revenue_current - revenue_previous) / revenue_previous
   - Sort: by current year revenue DESC
   - Description: Year-over-year revenue growth by product category

Permissions:
- Users: arn:aws:iam::123456789012:user/ceo, arn:aws:iam::123456789012:user/cfo, arn:aws:iam::123456789012:user/vp-sales
- Groups: Executives, Sales_Leadership
- Access level: VIEWER (read-only)

Dashboard layout:
- Row 1: KPIs (Total Active Customers, Monthly Recurring Revenue) side-by-side
- Row 2: Revenue Trend line chart (full width)
- Row 3: Customer LTV bar chart (left) + Regional Performance map (right)
- Row 4: Top 10 Products bar chart (left) + Sales Funnel (right)
- Row 5: YoY Growth pivot table (full width)

Create dashboard, grant permissions, configure SPICE refresh, and return dashboard URL + embed code.
```

---

## Example 5: Generate Synthetic Demo Data

### Context
You're building a demo for a conference presentation and need realistic customer and order data.

### Prompt
```
Generate synthetic data for demo_customer_master:

Rows: 200 rows
Columns:
- customer_id: STRING - Unique identifier - Format DEMO-CUST-00001 to DEMO-CUST-00200
- company_name: STRING - Company name - Realistic B2B company names from faker
- contact_name: STRING - Primary contact - Realistic full names
- email: STRING - Email address - {first}.{last}@{company}.com format, 15% nulls for quality testing
- phone: STRING - Phone number - Format +1-555-NNN-NNNN
- industry: ENUM - Industry vertical - Distribution: Technology 30%, Healthcare 20%, Finance 20%, Retail 15%, Manufacturing 15%
- segment: ENUM - Business segment - Distribution: Enterprise (>$100M revenue) 15%, Mid-Market ($10M-$100M) 35%, SMB (<$10M) 50%
- region: ENUM - Geographic region - Distribution: North America 50%, EMEA 30%, APAC 15%, LATAM 5%
- join_date: DATE - Customer onboarding date - Range 2021-01-01 to 2024-12-31, realistic distribution (more recent)
- contract_value: DECIMAL - Annual contract value - Realistic per segment: Enterprise $500K-$5M, Mid-Market $50K-$500K, SMB $5K-$50K
- contract_term: INTEGER - Contract length in months - Values: 12, 24, 36 (weighted: 20%, 50%, 30%)
- status: ENUM - Account status - Distribution: Active 80%, Onboarding 10%, Churned 8%, Suspended 2%
- account_manager: STRING - Assigned CSM - 20 unique names (some customers share managers)
- notes: STRING - Internal notes - Realistic sales notes or empty (70% empty)

Quality characteristics:
- 15% null values in email (realistic data issue)
- 8% null values in phone
- 5% duplicate company_name (intentional, different customer_ids)
- 2% future join_dates (data error for testing)
- 3% contract_value = 0 or negative (data error)

Output:
- Generator script: shared/fixtures/demo_customer_master_generator.py
- CSV file: shared/fixtures/demo_customer_master.csv
- Seed: 12345 for reproducibility
- Unit tests: validate distributions, nulls, edge cases
- CLI: python3 -m shared.fixtures.demo_customer_master_generator --rows 200 --seed 12345
```

**Then generate related orders:**

```
Generate synthetic data for demo_order_transactions with FK to demo_customer_master:

Rows: 600 rows (avg 3 orders per customer, range 0-15 orders per customer)
Columns:
- order_id: STRING - Unique identifier - Format DEMO-ORD-000001 to DEMO-ORD-000600
- customer_id: STRING - FK to demo_customer_master.customer_id - 95% valid FKs, 5% orphans (testing)
- order_date: DATE - Order date - Between customer join_date and 2025-03-31, realistic distribution
- product_category: ENUM - Product type - Distribution: Software License 40%, Professional Services 30%, Hardware 20%, Training 10%
- product_name: STRING - Product description - Realistic product names per category
- quantity: INTEGER - Units ordered - Range 1-50, realistic per category (Licenses higher qty than Services)
- unit_price: DECIMAL - Price per unit - Realistic per category: Software $500-$5000, Services $1500-$10000, Hardware $200-$2000, Training $500-$2000
- discount_pct: DECIMAL - Discount percentage - Range 0-0.30, weighted: 0% (50%), 0.10 (30%), 0.15 (15%), 0.20+ (5%)
- total_amount: DECIMAL - Order total - Calculated: quantity * unit_price * (1 - discount_pct)
- payment_terms: ENUM - Payment schedule - Distribution: Net 30 (60%), Net 60 (25%), Net 90 (10%), Prepaid (5%)
- fulfillment_status: ENUM - Order status - Distribution: Completed 70%, In Progress 20%, Cancelled 8%, Pending 2%
- sales_rep: STRING - Sales person - 15 unique names (matches account_manager trends)
- order_source: ENUM - How order was placed - Distribution: Direct Sales 50%, Partner Channel 30%, Online Portal 15%, Renewal 5%

Quality characteristics:
- 5% orphan customer_ids (not in customer master, for FK validation testing)
- 3% duplicate order_ids (data quality issue)
- 2% order_date < customer.join_date (temporal integrity violation)
- 5% total_amount != quantity * unit_price * (1 - discount_pct) (calculation error)
- 10% null values in sales_rep

Referential integrity:
- 95% of orders have valid customer_id
- 5% orphans for FK validation testing
- Order distribution: customers with high contract_value have more orders
- Temporal integrity: 98% of orders have order_date >= customer.join_date

Output:
- Generator script: shared/fixtures/demo_order_transactions_generator.py
- CSV file: shared/fixtures/demo_order_transactions.csv
- Seed: 12345 (same as customer for reproducibility)
- FK validation tests: verify 95% valid, 5% orphans
- Temporal tests: verify order_date >= join_date
- CLI: python3 -m shared.fixtures.demo_order_transactions_generator --rows 600 --customer-csv shared/fixtures/demo_customer_master.csv --seed 12345
```

---

## Example 6: Analyze Lineage for Compliance Audit

### Context
Your compliance team needs documentation of how customer PII flows through the system for GDPR/CCPA audit.

### Prompt
```
Analyze data lineage for customer_master and order_transactions with focus on PII handling:

Scope: Both workloads, with emphasis on data privacy compliance

Analysis:
1. Source-to-target lineage:
   - Trace PII columns: email, phone, address from source through all zones
   - Document transformations: Where is PII masked? Encrypted? Dropped?
   - Identify retention: How long is raw PII kept in each zone?

2. PII classifications:
   - List all columns classified as PII/PHI/PCI
   - Document masking methods used (hash, redact, drop)
   - Show which zones contain unmasked PII (Bronze only?)

3. Access controls:
   - Which IAM roles can access Bronze (raw PII)?
   - Which roles can access Silver (masked)?
   - Which roles can access Gold (aggregated, no PII)?

4. Compliance checkpoints:
   - Encryption: KMS keys used per zone
   - Audit logs: What operations are logged?
   - Data retention: Bronze 90 days, Silver 365 days, Gold 7 years
   - Right to deletion: How to purge customer data?

5. Data flow diagram:
   - ASCII or Mermaid diagram showing PII flow
   - Annotate with encryption, masking, access control points
   - Highlight compliance controls

Output:
1. pii_lineage_report.md (detailed analysis)
2. pii_flow_diagram.md (visual with annotations)
3. compliance_controls.yaml (structured compliance metadata)
4. data_retention_policy.md (retention rules per zone)
5. access_control_matrix.md (who can access what)

Format for compliance team review (non-technical audience).
```

---

## How the Semantic Layer Works (End-to-End)

Understanding how the semantic layer is built helps you fill in the ONBOARD and ENRICH prompts correctly. The semantic layer is **not a single tool** — it's assembled from multiple sources during onboarding and consumed by the Analysis Agent at query time.

### The Three Stores

The semantic layer lives across three AWS components:

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SEMANTIC LAYER                                   │
│                                                                       │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌──────────────┐ │
│  │ Glue Data Catalog    │  │ SageMaker Catalog    │  │ SynoDB       │ │
│  │                      │  │ (custom metadata     │  │ (Metrics &   │ │
│  │ WHAT: Table schemas  │  │  columns)             │  │  SQL Store)  │ │
│  │ - column names       │  │                      │  │              │ │
│  │ - data types         │  │ WHAT: Business        │  │ WHAT: Query  │ │
│  │ - partitions         │  │  context ON TOP of    │  │  examples    │ │
│  │ - S3 locations       │  │  Glue Catalog         │  │              │ │
│  │ - table format       │  │ - column roles        │  │ - Seed SQL   │ │
│  │                      │  │ - default_aggregation │  │   (ONBOARD)  │ │
│  │ FILLED BY:           │  │ - synonyms            │  │ - Learned    │ │
│  │ - Glue Crawler       │  │ - default_filters     │  │   SQL (from  │ │
│  │   (automatic)        │  │ - business_terms      │  │   Analysis   │ │
│  │                      │  │ - pii_flags           │  │   Agent)     │ │
│  │ READ BY:             │  │ - relationships        │  │              │ │
│  │ - All agents         │  │ - hierarchies         │  │ FILLED BY:   │ │
│  │ - Athena             │  │ - grain               │  │ - Deploy     │ │
│  │ - Glue ETL           │  │ - time_intelligence   │  │   script     │ │
│  │                      │  │ - data_freshness      │  │   (seeds)    │ │
│  │                      │  │                      │  │ - Analysis   │ │
│  │                      │  │ FILLED BY:            │  │   Agent      │ │
│  │                      │  │ - Metadata Agent      │  │   (learned)  │ │
│  │                      │  │   (technical stats)   │  │              │ │
│  │                      │  │ - Human (business     │  │ READ BY:     │ │
│  │                      │  │   context via ONBOARD)│  │ - Analysis   │ │
│  │                      │  │ - Deploy script       │  │   Agent      │ │
│  │                      │  │   (from semantic.yaml)│  │   only       │ │
│  │                      │  │                      │  │              │ │
│  │                      │  │ READ BY:              │  │              │ │
│  │                      │  │ - Analysis Agent      │  │              │ │
│  │                      │  │ - Transformation Agent│  │              │ │
│  │                      │  │ - Quality Agent       │  │              │ │
│  └─────────────────────┘  └─────────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### How semantic.yaml Gets Filled (Step by Step)

During onboarding, the semantic.yaml config file is built from two sources: **automatic profiling** and **human input (your ONBOARD prompt)**. At deploy time, it's loaded into SageMaker Catalog + SynoDB.

```
Step 1: Human provides ONBOARD prompt with schema + semantic layer
        ─────────────────────────────────────────────────────
        You provide:
        - Column roles (measure/dimension/temporal/identifier)
        - Aggregation semantics (SUM/AVG for each measure)
        - Grain ("one row per order")
        - Business terms & synonyms
        - Default filters
        - Dimension hierarchies
        - Time intelligence
        - Seed questions

Step 2: Glue Crawler auto-discovers schema
        ────────────────────────────────────
        Crawler scans your S3 source and detects:
        - Column names and data types (STRING, INTEGER, DOUBLE, DATE)
        - File format (CSV, JSON, Parquet)
        - Partitioning scheme
        → Registered in Glue Data Catalog

Step 3: Athena profiling on 5% sample
        ────────────────────────────────
        Athena runs profiling SQL and captures:
        - null_rate per column (e.g., email: 10% nulls)
        - min, max, avg for numeric columns
        - distinct_values for all columns
        - top_values for low-cardinality dimensions
        - row_count
        → Technical stats merged into semantic.yaml

Step 4: Metadata Agent runs PII detection + FK discovery
        ──────────────────────────────────────────────────
        Glue PII detection scans for:
        - Email patterns, SSN patterns, phone patterns, credit card patterns
        - Confidence scores (e.g., email: 95% confident)
        FK candidate detection:
        - Column names ending in _id
        - Value overlap with other tables
        → PII classifications + relationship suggestions added to semantic.yaml

Step 5: Human confirms business context
        ─────────────────────────────────
        You review and confirm:
        - Column role assignments (correct? any changes?)
        - PII classifications (did auto-detect miss anything?)
        - FK relationships (correct join keys?)
        → Final semantic.yaml written

Step 6: Deploy to SageMaker Catalog + SynoDB
        ─────────────────────────────────────
        Deploy script reads semantic.yaml and writes:
        - Custom metadata columns to SageMaker Catalog (on table + column entries)
        - Seed queries to SynoDB
        → Semantic layer is live, Analysis Agent can now answer questions
```

### What Each Section of semantic.yaml Comes From

| semantic.yaml Field | Automatic (Profiler) | Human (ONBOARD Prompt) | Why It Matters for AI Agent |
|---------------------|---------------------|-------------------|----------------------------|
| `dataset.grain` | - | "One row per order" | Prevents double-counting (COUNT(*) vs COUNT DISTINCT) |
| `columns.measures.default_aggregation` | - | "SUM" or "AVG" | **#1 cause of wrong queries** if missing |
| `columns.measures.unit` | - | "USD" / "count" / "pct" | Agent formats results correctly |
| `columns.measures.derived_from` | - | "qty * price * (1-disc)" | Agent knows field is computed |
| `columns.measures.null_rate` | Athena profiling | - | Agent knows data quality issues |
| `columns.measures.min/max/avg` | Athena profiling | - | Agent validates query results |
| `columns.dimensions.top_values` | Athena profiling | - | Agent knows valid WHERE values |
| `columns.dimensions.synonyms` | - | ["territory","area"] | Maps user language to column names |
| `columns.dimensions.default_filter` | - | "completed" | Implicit WHERE clause |
| `columns.temporal.is_primary_temporal` | - | "YES" | Agent knows which date column to use |
| `columns.identifiers.role` | Metadata Agent | Human confirms | Agent knows PK/FK for JOINs |
| `columns.pii.classification` | Glue PII detection | Human confirms | Agent masks sensitive data in results |
| `dimension_hierarchies` | - | "category -> product" | Agent can drill down |
| `default_filters` | - | "status = 'Completed'" | Implicit business logic |
| `business_terms` | - | "AOV = SUM/COUNT" | Maps NL terms to SQL expressions |
| `time_intelligence` | - | "FY starts Jan" | Agent handles MoM, YoY correctly |
| `data_freshness` | DAG schedule (auto) | Human confirms | "Latest data is yesterday" |
| `relationships.join_semantics` | - | ENRICH prompt | Agent joins tables correctly |
| `metrics_and_sql.seed_queries` | - | ONBOARD seed questions | **Training data** for first queries |

### The Learning Loop: How the System Gets Smarter

```
                    ┌─────────────────────────────────┐
                    │ Day 1: Deploy                    │
                    │                                   │
                    │ semantic.yaml loaded to:          │
                    │ - SageMaker Catalog (context)     │
                    │ - SynoDB (8 seed queries)         │
                    │                                   │
                    │ Analysis Agent accuracy: ~70%     │
                    │ (relies on column roles + seeds)  │
                    └───────────────┬───────────────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────────┐
                    │ Day 7: Agent has answered 50 Qs  │
                    │                                   │
                    │ Best 20 queries saved to SynoDB   │
                    │ Agent accuracy: ~80%              │
                    │ (matches more patterns)           │
                    └───────────────┬───────────────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────────┐
                    │ Day 30: 200 queries answered      │
                    │                                   │
                    │ SynoDB has 100+ proven patterns   │
                    │ Agent accuracy: ~90%              │
                    │ (rarely generates from scratch)   │
                    └───────────────┬───────────────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────────┐
                    │ Day 90: 500+ queries answered     │
                    │                                   │
                    │ SynoDB has 300+ proven patterns   │
                    │ Agent accuracy: ~95%+             │
                    │ Most questions match a pattern    │
                    │ New similar questions answered     │
                    │ instantly with high confidence     │
                    └─────────────────────────────────┘
```

**Key insight**: The more questions users ask, the smarter the system gets. Each good query is saved as a pattern for future use. This is why **seed questions in ONBOARD matter** — they bootstrap the learning loop.

### How the Analysis Agent Uses It (Query Walkthrough)

**User asks**: "What is the average order value by customer segment this quarter?"

```
Step 1: Parse NL question
        - "average order value" → look up in business_terms
        - Found: AOV = SUM(revenue) / COUNT(DISTINCT transaction_id)
        - "customer segment" → look up synonyms
        - Found: segment column is on customer_master table (not on orders)
        - "this quarter" → look up time_intelligence
        - Found: fiscal_year_start = January, standard quarters

Step 2: Check SynoDB for similar past queries
        - Search: "average order value" + "segment"
        - Found match (80% similarity): prior query for "AOV by segment"
        - Reuse pattern, adjust for "this quarter" filter

Step 3: Determine JOIN strategy
        - "segment" is on customer_master, not order_transactions
        - Read relationship: orders.customer_id → customers.customer_id
        - Read pre_aggregation_rule: "Aggregate orders FIRST, then join"
        - Read fan_out_warning: "Use COUNT(DISTINCT customer_id) after join"

Step 4: Read default filters
        - Revenue queries → WHERE fulfillment_status = 'Delivered'

Step 5: Read grain
        - grain: "one row per transaction"
        - Use COUNT(DISTINCT transaction_id) not COUNT(*)

Step 6: Generate SQL
        WITH order_agg AS (
            SELECT customer_id,
                   SUM(revenue) AS total_revenue,
                   COUNT(DISTINCT transaction_id) AS order_count
            FROM gold_db.transaction_fact
            WHERE fulfillment_status = 'Delivered'
              AND order_date >= DATE_TRUNC('quarter', CURRENT_DATE)
            GROUP BY customer_id
        )
        SELECT c.segment,
               ROUND(SUM(o.total_revenue) / SUM(o.order_count), 2) AS avg_order_value,
               SUM(o.total_revenue) AS total_revenue,
               SUM(o.order_count) AS total_orders
        FROM order_agg o
        LEFT JOIN gold_db.dim_customer c ON o.customer_id = c.customer_id
        GROUP BY c.segment
        ORDER BY total_revenue DESC
        LIMIT 10000;

Step 7: Save to SynoDB (if query was useful and new)
        - Query pattern saved for future "AOV by segment" questions
```

**Without the semantic layer, the Agent would have generated**:
```sql
-- WRONG: No default filter, wrong aggregation, fan-out, no grain awareness
SELECT c.segment, AVG(t.revenue) AS avg_order_value
FROM gold_db.transaction_fact t
JOIN gold_db.dim_customer c ON t.customer_id = c.customer_id
GROUP BY c.segment;
-- Problems:
-- 1. AVG(revenue) ≠ AOV (should be SUM/COUNT DISTINCT)
-- 2. No WHERE fulfillment_status = 'Delivered'
-- 3. No "this quarter" filter
-- 4. No pre-aggregation → fan-out inflates averages
```

---

## Pro Tips

### When to Use Which Pattern

- **ROUTE always first** - Prevents duplicate work
- **GENERATE for demos** - No access to production data needed
- **ONBOARD for new data** - Complete pipeline from scratch (fill semantic layer carefully!)
- **ENRICH after ONBOARD** - Link datasets after they exist (include join semantics)
- **CONSUME for stakeholders** - Make data accessible to business users
- **GOVERN for governance** - Documentation, audits, impact analysis

### Semantic Layer is the Most Important Part

The Semantic Layer section in ONBOARD is what enables the AI Analysis Agent to answer natural language questions correctly. **Spend the most time here.**

Priority order:
1. **Aggregation semantics** - SUM vs AVG is the #1 source of wrong queries
2. **Default filters** - "revenue" means completed orders only? Or all?
3. **Business terms & synonyms** - users say "sales", column is named "revenue"
4. **Fact table grain** - prevents double-counting
5. **Seed questions** - training data for the Analysis Agent

### Making Prompts More Specific

**Too vague:**
```
Onboard customer data
```

**Better:**
```
Onboard customer_master from s3://bucket/customers.csv with PII masking, daily refresh
```

**Best (includes semantic layer):**
```
Onboard customer_master from s3://prod-data/crm/customers.csv (CSV, 2M rows, daily at 6am)
- Mask: email, phone, address
- Measures: lifetime_value (SUM), credit_limit (AVG)
- Dimensions: segment, country, status
- Default filter: revenue queries use status='Active' or 'Inactive' only
- Synonyms: "clients" = customers, "LTV" = lifetime_value, "churn" = status='Churned'
- Seed questions: "How many active customers?", "LTV by segment?", "Churn rate this quarter?"
- Gold: Star schema for reporting, 95% quality threshold
- Schedule: Daily 6am UTC, 90min SLA
```

### Common Mistakes to Avoid

**Semantic Layer Mistakes:**

- "All measures default to SUM" -> unit_price and discount_pct should be AVG
- "No default filters" -> "total revenue" includes cancelled orders (probably wrong)
- "No synonyms" -> user says "sales" but column is "revenue", Agent finds nothing
- "No grain defined" -> Agent uses COUNT(*) instead of COUNT(DISTINCT order_id)
- "No seed questions" -> Agent has no training examples, first queries are inaccurate

**Pipeline Mistakes:**

- Skipping ROUTE -> Creating duplicate workloads
- Vague schema -> Missing columns in Gold
- No quality rules -> Bad data reaches Gold
- Hardcoded secrets -> Security violation
- No retention policy -> Bronze grows forever

---

For more patterns and details, see:
- `SKILLS.md` -> Full modular prompt patterns section
- `PROMPTS_QUICK_REFERENCE.md` -> Quick copy-paste templates
- `CLAUDE.md` -> Architecture and conventions
