-- Create Bronze zone table for stocks workload
-- Database: ${DATABASE}_bronze
-- This is an external table pointing to raw CSV in S3
-- Bronze data is IMMUTABLE - never modified after ingestion

CREATE EXTERNAL TABLE IF NOT EXISTS ${DATABASE}_bronze.stocks (
    ticker              STRING  COMMENT 'Stock ticker symbol (PK)',
    company_name        STRING  COMMENT 'Legal company name as listed on exchange',
    sector              STRING  COMMENT 'Business sector classification',
    industry            STRING  COMMENT 'Industry classification within sector',
    exchange            STRING  COMMENT 'Stock exchange (NASDAQ, NYSE)',
    market_cap_billions STRING  COMMENT 'Market capitalization in billions USD (raw string)',
    current_price       STRING  COMMENT 'Current trading price in USD (raw string)',
    price_52w_high      STRING  COMMENT '52-week high price in USD (raw string)',
    price_52w_low       STRING  COMMENT '52-week low price in USD (raw string)',
    pe_ratio            STRING  COMMENT 'Price-to-earnings ratio (raw string, can be negative)',
    dividend_yield      STRING  COMMENT 'Annual dividend yield percentage (raw string)',
    beta                STRING  COMMENT 'Stock volatility relative to market (raw string)',
    avg_volume_millions STRING  COMMENT 'Average daily trading volume in millions (raw string)',
    listing_date        STRING  COMMENT 'IPO / listing date (YYYY-MM-DD raw string)'
)
ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
    LINES TERMINATED BY '\n'
STORED AS TEXTFILE
LOCATION 's3://${DATA_LAKE_BUCKET}/bronze/stocks/'
TBLPROPERTIES (
    'skip.header.line.count' = '1',
    'classification' = 'csv',
    'has_encrypted_data' = 'true',
    'compliance' = 'GDPR',
    'data_sensitivity' = 'LOW'
);
