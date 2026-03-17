-- create_bronze_table.sql
-- Creates Bronze zone external table for customers in Glue Data Catalog
-- Database: demo_database_ai_agents_bronze
-- Location: s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/bronze/customers/

-- Note: This DDL is for documentation. Actual registration uses aws glue create-table CLI.
-- Bronze zone is immutable — raw CSV preserved as ingested.

CREATE EXTERNAL TABLE demo_database_ai_agents_bronze.customers (
    customer_id   STRING    COMMENT 'Primary key, format CUST-NNN',
    name          STRING    COMMENT 'Customer full name (PII)',
    email         STRING    COMMENT 'Customer email (PII, ~13% nulls)',
    phone         STRING    COMMENT 'Customer phone (PII)',
    segment       STRING    COMMENT 'Enterprise | SMB | Individual',
    industry      STRING    COMMENT 'Industry vertical',
    country       STRING    COMMENT 'Country code: US | UK | CA | DE',
    status        STRING    COMMENT 'Active | Inactive | Churned',
    join_date     STRING    COMMENT 'Date joined, format YYYY-MM-DD',
    annual_value  STRING    COMMENT 'Annual contract value USD',
    credit_limit  STRING    COMMENT 'Credit limit USD'
)
ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 's3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/bronze/customers/'
TBLPROPERTIES (
    'skip.header.line.count' = '1',
    'classification' = 'csv',
    'has_encrypted_data' = 'false'
);
