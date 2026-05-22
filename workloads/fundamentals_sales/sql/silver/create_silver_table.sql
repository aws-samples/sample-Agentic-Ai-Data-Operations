-- Silver table: cleansed reported sales -- Apache Iceberg on S3 Tables.
-- Multi-metric ready: PK includes 'metric' so future metrics (FF_GROSS_PROFIT, etc.)
-- can land in the same table.

CREATE TABLE IF NOT EXISTS s3tablesbucket.fundamentals_sales_db.silver_fundamentals_sales (
    entity_id        STRING      NOT NULL,
    fiscal_period_id STRING      NOT NULL,
    fiscal_year      INT         NOT NULL,
    fiscal_period    STRING      NOT NULL,
    period_end_date  DATE,
    metric           STRING      NOT NULL,
    value            DOUBLE,
    currency         STRING      NOT NULL,
    value_usd        DOUBLE      NOT NULL,
    source           STRING,
    load_timestamp   TIMESTAMP,
    ingestion_ts     TIMESTAMP
)
USING iceberg
PARTITIONED BY (metric, fiscal_year, fiscal_period)
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
