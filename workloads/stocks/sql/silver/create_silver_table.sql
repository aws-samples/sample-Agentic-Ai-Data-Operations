-- Create Silver zone Iceberg table for stocks workload
-- Database: ${DATABASE}_silver
-- Apache Iceberg on Amazon S3 Tables - ACID, time-travel, schema evolution
-- Includes GDPR metadata columns for right-to-erasure and consent tracking

CREATE TABLE IF NOT EXISTS ${DATABASE}_silver.stocks (
    -- Identifier (Primary Key)
    ticker                STRING          NOT NULL  COMMENT 'Stock ticker symbol (PK)',

    -- Dimensions
    company_name          STRING          NOT NULL  COMMENT 'Legal company name as listed on exchange',
    sector                STRING          NOT NULL  COMMENT 'Business sector classification',
    industry              STRING          NOT NULL  COMMENT 'Industry classification within sector',
    exchange              STRING          NOT NULL  COMMENT 'Stock exchange (NASDAQ, NYSE)',

    -- Measures
    market_cap_billions   DECIMAL(12,2)   NOT NULL  COMMENT 'Market capitalization in billions USD',
    current_price         DECIMAL(10,2)   NOT NULL  COMMENT 'Current trading price in USD per share',
    price_52w_high        DECIMAL(10,2)   NOT NULL  COMMENT '52-week high price in USD',
    price_52w_low         DECIMAL(10,2)   NOT NULL  COMMENT '52-week low price in USD',
    pe_ratio              DECIMAL(8,2)              COMMENT 'Price-to-earnings ratio (nullable - can be negative for loss-making)',
    dividend_yield        DECIMAL(6,4)    NOT NULL  COMMENT 'Annual dividend yield as percentage',
    beta                  DECIMAL(6,3)    NOT NULL  COMMENT 'Stock volatility relative to market (beta coefficient)',
    avg_volume_millions   DECIMAL(10,2)   NOT NULL  COMMENT 'Average daily trading volume in millions of shares',

    -- Temporal
    listing_date          DATE            NOT NULL  COMMENT 'Date when stock was first listed on exchange',

    -- GDPR Metadata
    consent_given         BOOLEAN         NOT NULL  COMMENT 'Whether data subject has given consent (default true for public data)',
    consent_timestamp     TIMESTAMP       NOT NULL  COMMENT 'Timestamp when consent was recorded',
    is_deleted            BOOLEAN         NOT NULL  COMMENT 'Soft-delete flag for right-to-erasure requests',
    deletion_requested_at TIMESTAMP                 COMMENT 'Timestamp of deletion request (null if no request)',
    data_subject_id       STRING                    COMMENT 'Identifier for the data subject (N/A for public market data)'
)
USING iceberg
LOCATION 's3://${DATA_LAKE_BUCKET}/silver/stocks/'
TBLPROPERTIES (
    'format-version' = '2',
    'write.format.default' = 'parquet',
    'write.metadata.compression-codec' = 'gzip',
    'write.parquet.compression-codec' = 'zstd',
    'table_type' = 'ICEBERG',
    'compliance' = 'GDPR',
    'data_sensitivity' = 'LOW'
);
