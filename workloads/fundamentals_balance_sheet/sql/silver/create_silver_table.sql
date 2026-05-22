-- Silver table: cleansed annual balance sheet -- Apache Iceberg on S3 Tables.

CREATE TABLE IF NOT EXISTS s3tablesbucket.fundamentals_balance_sheet_db.silver_fundamentals_balance_sheet (
    entity_id              STRING      NOT NULL,
    fiscal_period_id       STRING      NOT NULL,
    fiscal_year            INT         NOT NULL,
    total_assets           DOUBLE      NOT NULL,
    total_liabilities      DOUBLE,
    total_equity           DOUBLE,
    cash_and_equivalents   DOUBLE,
    total_debt             DOUBLE,
    currency               STRING      NOT NULL,
    value_usd_total_assets DOUBLE      NOT NULL,
    ingestion_ts           TIMESTAMP
)
USING iceberg
PARTITIONED BY (fiscal_year)
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
