-- Silver table: cleansed annual cash flow -- Apache Iceberg on S3 Tables.

CREATE TABLE IF NOT EXISTS s3tablesbucket.fundamentals_cash_flow_db.silver_fundamentals_cash_flow (
    entity_id            STRING      NOT NULL,
    fiscal_period_id     STRING      NOT NULL,
    fiscal_year          INT         NOT NULL,
    operating_cash_flow  DOUBLE,
    capital_expenditure  DOUBLE,
    free_cash_flow       DOUBLE,
    dividends_paid       DOUBLE,
    share_buybacks       DOUBLE,
    currency             STRING      NOT NULL,
    value_usd_fcf        DOUBLE,
    load_timestamp       TIMESTAMP,
    ingestion_ts         TIMESTAMP
)
USING iceberg
PARTITIONED BY (fiscal_year)
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
