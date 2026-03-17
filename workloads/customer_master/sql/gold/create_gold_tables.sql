-- create_gold_tables.sql
-- Creates Gold zone star schema tables in Glue Data Catalog
-- Database: demo_database_ai_agents_goldzone
-- Location: s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/customers/

-- Note: This DDL is for documentation. Actual registration uses aws glue create-table CLI.
-- Gold zone is curated, star schema format for QuickSight dashboards.

-- 1. Customer Fact Table
CREATE EXTERNAL TABLE demo_database_ai_agents_goldzone.customer_fact (
    customer_id   STRING    COMMENT 'Primary key (CUST-NNN)',
    name          STRING    COMMENT 'Customer name',
    email_hash    STRING    COMMENT 'SHA-256 hash of email (PII masked)',
    phone_masked  STRING    COMMENT 'Phone with all but last 4 digits masked',
    segment       STRING    COMMENT 'FK to dim_segment',
    industry      STRING    COMMENT 'Industry vertical',
    country_code  STRING    COMMENT 'FK to dim_country',
    status        STRING    COMMENT 'FK to dim_status',
    join_date     STRING    COMMENT 'Customer join date YYYY-MM-DD',
    annual_value  DOUBLE    COMMENT 'Annual contract value USD',
    credit_limit  DOUBLE    COMMENT 'Credit limit USD'
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 's3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/customers/customer_fact/'
TBLPROPERTIES ('skip.header.line.count' = '1', 'classification' = 'csv');

-- 2. Dimension: Segment
CREATE EXTERNAL TABLE demo_database_ai_agents_goldzone.dim_segment (
    segment_id    INT       COMMENT 'Surrogate key',
    segment_name  STRING    COMMENT 'Enterprise | SMB | Individual'
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 's3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/customers/dim_segment/'
TBLPROPERTIES ('skip.header.line.count' = '1', 'classification' = 'csv');

-- 3. Dimension: Country
CREATE EXTERNAL TABLE demo_database_ai_agents_goldzone.dim_country (
    country_code  STRING    COMMENT 'ISO country code',
    country_name  STRING    COMMENT 'Full country name'
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 's3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/customers/dim_country/'
TBLPROPERTIES ('skip.header.line.count' = '1', 'classification' = 'csv');

-- 4. Dimension: Status
CREATE EXTERNAL TABLE demo_database_ai_agents_goldzone.dim_status (
    status_id     INT       COMMENT 'Surrogate key',
    status_name   STRING    COMMENT 'Active | Inactive | Churned'
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 's3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/customers/dim_status/'
TBLPROPERTIES ('skip.header.line.count' = '1', 'classification' = 'csv');

-- 5. Aggregate: Summary by Segment
CREATE EXTERNAL TABLE demo_database_ai_agents_goldzone.customer_summary_by_segment (
    segment              STRING    COMMENT 'Segment name',
    customer_count       INT       COMMENT 'Number of customers',
    total_annual_value   DOUBLE    COMMENT 'Sum of annual values',
    avg_annual_value     DOUBLE    COMMENT 'Average annual value',
    total_credit_limit   DOUBLE    COMMENT 'Sum of credit limits'
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 's3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/customers/customer_summary_by_segment/'
TBLPROPERTIES ('skip.header.line.count' = '1', 'classification' = 'csv');
