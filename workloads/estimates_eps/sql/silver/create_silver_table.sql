-- Silver table: cleansed EPS estimates -- Apache Iceberg on S3 Tables.
-- Tool routing: glue-athena MCP -> Iceberg DDL.

CREATE TABLE IF NOT EXISTS s3tablesbucket.estimates_eps_db.silver_estimates_eps (
    entity_id     STRING      NOT NULL,
    estimate_date DATE        NOT NULL,
    period_type   STRING      NOT NULL,
    eps_mean      DOUBLE      NOT NULL,
    eps_high      DOUBLE,
    eps_low       DOUBLE,
    num_analysts  INT,
    currency      STRING,
    ingestion_ts  TIMESTAMP
)
USING iceberg
PARTITIONED BY (period_type, months(estimate_date))
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
