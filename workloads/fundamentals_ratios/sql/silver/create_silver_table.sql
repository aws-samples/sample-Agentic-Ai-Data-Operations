-- Silver table: cleansed annual ratios -- Apache Iceberg on S3 Tables.
--
-- Schema decisions:
--   * Source columns roa, debt_to_equity, current_ratio, load_timestamp dropped
--     (100% null in current sample).

CREATE TABLE IF NOT EXISTS s3tablesbucket.fundamentals_ratios_db.silver_fundamentals_ratios (
    entity_id        STRING      NOT NULL,
    fiscal_period_id STRING      NOT NULL,
    fiscal_year      INT         NOT NULL,
    pe_ratio         DOUBLE,
    pb_ratio         DOUBLE,
    ev_ebitda        DOUBLE,
    roe              DOUBLE,
    ingestion_ts     TIMESTAMP
)
USING iceberg
PARTITIONED BY (fiscal_year)
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
