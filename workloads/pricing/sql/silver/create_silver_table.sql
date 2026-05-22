-- Silver table: cleansed daily equity pricing -- Apache Iceberg on S3 Tables.

CREATE TABLE IF NOT EXISTS s3tablesbucket.pricing_db.silver_pricing (
    entity_id     STRING      NOT NULL,
    price_date    DATE        NOT NULL,
    close_price   DOUBLE      NOT NULL,
    volume        BIGINT,
    market_cap    DOUBLE,
    currency      STRING      NOT NULL,
    ingestion_ts  TIMESTAMP
)
USING iceberg
PARTITIONED BY (months(price_date))
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
