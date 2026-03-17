-- Create Bronze zone table for order_transactions
-- Database: demo_database_ai_agents_bronze
-- This is an external table pointing to raw CSV in S3
-- Bronze data is IMMUTABLE - never modified after ingestion

CREATE EXTERNAL TABLE IF NOT EXISTS demo_database_ai_agents_bronze.orders (
    order_id      STRING  COMMENT 'Unique order identifier (PK)',
    customer_id   STRING  COMMENT 'Customer who placed the order (FK to customer_master)',
    order_date    STRING  COMMENT 'Date the order was placed (YYYY-MM-DD)',
    product_name  STRING  COMMENT 'Name of the product ordered',
    category      STRING  COMMENT 'Product category: Electronics, Furniture, Supplies',
    quantity      INT     COMMENT 'Number of units ordered',
    unit_price    DOUBLE  COMMENT 'Price per unit before discount',
    discount_pct  DOUBLE  COMMENT 'Discount percentage (0 to 0.25)',
    revenue       DOUBLE  COMMENT 'Total revenue: quantity * unit_price * (1 - discount_pct)',
    status        STRING  COMMENT 'Order status: Completed, Pending, Cancelled',
    region        STRING  COMMENT 'Sales region: East, West, Central, South'
)
ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
    LINES TERMINATED BY '\n'
STORED AS TEXTFILE
LOCATION 's3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/bronze/orders/'
TBLPROPERTIES (
    'skip.header.line.count' = '1',
    'classification' = 'csv',
    'has_encrypted_data' = 'false'
);
