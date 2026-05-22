-- Silver table: cleansed ratings -- Apache Iceberg on S3 Tables.

CREATE TABLE IF NOT EXISTS s3tablesbucket.estimates_ratings_db.silver_estimates_ratings (
    entity_id          STRING      NOT NULL,
    rating_date        DATE        NOT NULL,
    consensus_rating   STRING      NOT NULL,
    buy_count          INT,
    hold_count         INT,
    sell_count         INT,
    target_price_mean  DOUBLE,
    target_price_high  DOUBLE,
    target_price_low   DOUBLE,
    currency           STRING,
    ingestion_ts       TIMESTAMP
)
USING iceberg
PARTITIONED BY (months(rating_date))
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
