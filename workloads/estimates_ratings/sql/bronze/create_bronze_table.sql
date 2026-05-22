-- Bronze table: raw fe_ratings CSV partitioned by ingestion date.
-- Tool routing: glue-athena MCP -> create_database + Glue Crawler.

CREATE EXTERNAL TABLE IF NOT EXISTS estimates_ratings_db.bronze_estimates_ratings (
    entity_id          STRING,
    rating_date        STRING,
    consensus_rating   STRING,
    buy_count          STRING,
    hold_count         STRING,
    sell_count         STRING,
    target_price_mean  STRING,
    target_price_high  STRING,
    target_price_low   STRING,
    currency           STRING
)
PARTITIONED BY (ingestion_date STRING)
STORED AS PARQUET
LOCATION 's3://${var:data_lake_bucket}/bronze/estimates_ratings/'
TBLPROPERTIES ('classification' = 'parquet');
