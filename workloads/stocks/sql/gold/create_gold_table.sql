-- Create Gold zone Iceberg table for stocks_analytics (flat denormalized)
-- Database: ${DATABASE}_gold
-- Apache Iceberg - all Silver columns + computed enrichment columns
-- Schema format: Flat denormalized (NOT star schema) for ad-hoc analytics

CREATE TABLE IF NOT EXISTS ${DATABASE}_gold.stocks_analytics (
    -- Identifier (Primary Key)
    ticker                  STRING          NOT NULL  COMMENT 'Stock ticker symbol (PK)',

    -- Dimensions
    company_name            STRING          NOT NULL  COMMENT 'Legal company name as listed on exchange',
    sector                  STRING          NOT NULL  COMMENT 'Business sector classification',
    industry                STRING          NOT NULL  COMMENT 'Industry classification within sector',
    exchange                STRING          NOT NULL  COMMENT 'Stock exchange (NASDAQ, NYSE)',

    -- Measures (from Silver)
    market_cap_billions     DECIMAL(12,2)   NOT NULL  COMMENT 'Market capitalization in billions USD',
    current_price           DECIMAL(10,2)   NOT NULL  COMMENT 'Current trading price in USD per share',
    price_52w_high          DECIMAL(10,2)   NOT NULL  COMMENT '52-week high price in USD',
    price_52w_low           DECIMAL(10,2)   NOT NULL  COMMENT '52-week low price in USD',
    pe_ratio                DECIMAL(8,2)              COMMENT 'Price-to-earnings ratio (nullable - can be negative)',
    dividend_yield          DECIMAL(6,4)    NOT NULL  COMMENT 'Annual dividend yield as percentage',
    beta                    DECIMAL(6,3)    NOT NULL  COMMENT 'Stock volatility relative to market',
    avg_volume_millions     DECIMAL(10,2)   NOT NULL  COMMENT 'Average daily trading volume in millions',

    -- Temporal
    listing_date            DATE            NOT NULL  COMMENT 'Date when stock was first listed on exchange',

    -- GDPR Metadata (carried from Silver)
    consent_given           BOOLEAN         NOT NULL  COMMENT 'GDPR consent flag',
    consent_timestamp       TIMESTAMP       NOT NULL  COMMENT 'GDPR consent timestamp',
    is_deleted              BOOLEAN         NOT NULL  COMMENT 'GDPR soft-delete flag',
    deletion_requested_at   TIMESTAMP                 COMMENT 'GDPR deletion request timestamp',
    data_subject_id         STRING                    COMMENT 'GDPR data subject identifier',

    -- Computed Columns (Gold enrichment)
    price_52w_range         DECIMAL(10,2)   NOT NULL  COMMENT 'price_52w_high - price_52w_low',
    price_pct_from_high     DECIMAL(8,4)    NOT NULL  COMMENT '((current_price - price_52w_high) / price_52w_high) * 100',
    market_cap_category     STRING          NOT NULL  COMMENT 'Mega Cap (>=200B) / Large Cap (>=10B) / Mid Cap (>=2B) / Small Cap',
    yield_category          STRING          NOT NULL  COMMENT 'High Yield (>=4) / Moderate Yield (>=2) / Low Yield (>0) / No Yield',
    volatility_category     STRING          NOT NULL  COMMENT 'High Volatility (>=1.5) / Market (>=1.0) / Low (>=0.5) / Defensive'
)
USING iceberg
LOCATION 's3://${DATA_LAKE_BUCKET}/gold/stocks/stocks_analytics/'
TBLPROPERTIES (
    'format-version' = '2',
    'write.format.default' = 'parquet',
    'write.metadata.compression-codec' = 'gzip',
    'write.parquet.compression-codec' = 'zstd',
    'table_type' = 'ICEBERG',
    'compliance' = 'GDPR',
    'data_sensitivity' = 'LOW',
    'schema_format' = 'flat_denormalized'
);
