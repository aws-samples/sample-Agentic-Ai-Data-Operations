-- Silver table: cleansed NTM sales estimates -- Apache Iceberg on S3 Tables.
-- Multi-metric ready: PK includes 'metric' so future metrics can land in same table.

CREATE TABLE IF NOT EXISTS s3tablesbucket.estimates_sales_ntm_db.silver_estimates_sales_ntm (
    entity_id       STRING      NOT NULL,
    estimate_date   DATE        NOT NULL,
    metric          STRING      NOT NULL,
    value           DOUBLE,
    currency        STRING      NOT NULL,
    value_usd       DOUBLE      NOT NULL,
    num_analysts    INT,
    source          STRING,
    load_timestamp  TIMESTAMP,
    ingestion_ts    TIMESTAMP
)
USING iceberg
PARTITIONED BY (metric, months(estimate_date))
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
