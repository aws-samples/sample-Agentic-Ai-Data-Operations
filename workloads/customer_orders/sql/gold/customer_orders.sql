-- spec_hash: b53415e9719ca58d0b8986f828ce307c485ffde125c169ae6422b6672b6ca2b1
-- template_id: iceberg_ddl
-- template_hash: 1e508b5014654c4ba154b67ab39b52dc4beeea4ca0e100e16eb7b3746378f844
-- schema_version: v1
-- rendered_at: 2026-10-22T18:18:44Z
CREATE DATABASE IF NOT EXISTS customer_orders_db;

CREATE TABLE IF NOT EXISTS customer_orders_db.gold_customer_orders (
    order_id STRING,
    order_count BIGINT,
    revenue DECIMAL(22,2),
    customer_id STRING,
    product_id STRING,
    order_date DATE,
    ship_date DATE,
    quantity INT,
    unit_price DECIMAL(10,2),
    discount_pct DECIMAL(5,2),
    payment_method STRING,
    order_status STRING,
    data_subject_id STRING,
    consent_given BOOLEAN,
    consent_timestamp TIMESTAMP,
    is_deleted BOOLEAN,
    deletion_requested_at TIMESTAMP
)
USING iceberg
LOCATION 's3://${DATA_LAKE_BUCKET}/customer_orders/gold/gold_customer_orders/'
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet',
    'write.format.default' = 'parquet'
);

