-- spec_hash: c8d97233ce1806d125a31e2efce0c1565479815f11c36aac9eb19116e9b51462
-- template_id: iceberg_ddl
-- template_hash: 1e508b5014654c4ba154b67ab39b52dc4beeea4ca0e100e16eb7b3746378f844
-- schema_version: v1
-- rendered_at: 2026-10-22T18:18:44Z
CREATE DATABASE IF NOT EXISTS customer_orders_db;

CREATE TABLE IF NOT EXISTS customer_orders_db.silver_customer_orders (
    order_id STRING,
    customer_id STRING,
    order_date DATE,
    product_id STRING,
    quantity INT,
    unit_price DECIMAL(10,2),
    discount_pct DECIMAL(5,2),
    payment_method STRING,
    order_status STRING,
    ship_date DATE,
    customer_email STRING,
    customer_phone STRING,
    customer_name STRING,
    shipping_address STRING,
    city STRING,
    state STRING,
    zip_code STRING,
    credit_card_token STRING,
    revenue DECIMAL(12,2),
    data_subject_id STRING,
    consent_given BOOLEAN,
    consent_timestamp TIMESTAMP,
    is_deleted BOOLEAN,
    deletion_requested_at TIMESTAMP
)
USING iceberg
LOCATION 's3://${DATA_LAKE_BUCKET}/customer_orders/silver/silver_customer_orders/'
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet',
    'write.format.default' = 'parquet'
);

