-- Create Gold zone star schema tables for order_transactions
-- Database: demo_database_ai_agents_goldzone
-- Tables: order_fact, dim_product, dim_region, dim_status, order_summary

-- =============================================================================
-- FACT TABLE: order_fact
-- One row per clean, validated order
-- =============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS demo_database_ai_agents_goldzone.order_fact (
    order_id      STRING  COMMENT 'Unique order identifier (PK)',
    customer_id   STRING  COMMENT 'FK to customer_master dim_customer',
    order_date    STRING  COMMENT 'Order date (YYYY-MM-DD)',
    product_id    STRING  COMMENT 'FK to dim_product',
    region_id     STRING  COMMENT 'FK to dim_region',
    status_id     STRING  COMMENT 'FK to dim_status',
    status_name   STRING  COMMENT 'Denormalized status for convenience',
    quantity      INT     COMMENT 'Units ordered',
    unit_price    DOUBLE  COMMENT 'Price per unit',
    discount_pct  DOUBLE  COMMENT 'Discount percentage applied',
    revenue       DOUBLE  COMMENT 'Total order revenue'
)
ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
    LINES TERMINATED BY '\n'
STORED AS TEXTFILE
LOCATION 's3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/orders/order_fact/'
TBLPROPERTIES (
    'skip.header.line.count' = '1',
    'classification' = 'csv'
);

-- =============================================================================
-- DIMENSION TABLE: dim_product
-- =============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS demo_database_ai_agents_goldzone.dim_product (
    product_id    STRING  COMMENT 'Surrogate key for product',
    product_name  STRING  COMMENT 'Product name',
    category      STRING  COMMENT 'Product category: Electronics, Furniture, Supplies'
)
ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
    LINES TERMINATED BY '\n'
STORED AS TEXTFILE
LOCATION 's3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/orders/dim_product/'
TBLPROPERTIES (
    'skip.header.line.count' = '1',
    'classification' = 'csv'
);

-- =============================================================================
-- DIMENSION TABLE: dim_region
-- =============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS demo_database_ai_agents_goldzone.dim_region (
    region_id     STRING  COMMENT 'Surrogate key for region',
    region_name   STRING  COMMENT 'Region name: East, West, Central, South'
)
ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
    LINES TERMINATED BY '\n'
STORED AS TEXTFILE
LOCATION 's3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/orders/dim_region/'
TBLPROPERTIES (
    'skip.header.line.count' = '1',
    'classification' = 'csv'
);

-- =============================================================================
-- DIMENSION TABLE: dim_status
-- =============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS demo_database_ai_agents_goldzone.dim_status (
    status_id     STRING  COMMENT 'Surrogate key for status',
    status_name   STRING  COMMENT 'Order status: Completed, Pending, Cancelled'
)
ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
    LINES TERMINATED BY '\n'
STORED AS TEXTFILE
LOCATION 's3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/orders/dim_status/'
TBLPROPERTIES (
    'skip.header.line.count' = '1',
    'classification' = 'csv'
);

-- =============================================================================
-- AGGREGATE TABLE: order_summary
-- Pre-aggregated metrics by region and category
-- =============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS demo_database_ai_agents_goldzone.order_summary (
    region            STRING  COMMENT 'Sales region',
    category          STRING  COMMENT 'Product category',
    total_revenue     DOUBLE  COMMENT 'Sum of revenue',
    total_quantity    INT     COMMENT 'Sum of quantity',
    order_count       INT     COMMENT 'Count of orders',
    avg_unit_price    DOUBLE  COMMENT 'Average unit price',
    avg_discount_pct  DOUBLE  COMMENT 'Average discount percentage'
)
ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
    LINES TERMINATED BY '\n'
STORED AS TEXTFILE
LOCATION 's3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/orders/order_summary/'
TBLPROPERTIES (
    'skip.header.line.count' = '1',
    'classification' = 'csv'
);
