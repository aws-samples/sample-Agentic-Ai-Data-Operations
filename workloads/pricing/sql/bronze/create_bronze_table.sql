-- Bronze table: raw fp_prices CSV partitioned by ingestion date.
-- Tool routing: glue-athena MCP -> create_database + Glue Crawler.

CREATE EXTERNAL TABLE IF NOT EXISTS pricing_db.bronze_pricing (
    entity_id    STRING,
    price_date   STRING,
    close_price  STRING,
    volume       STRING,
    market_cap   STRING,
    currency     STRING
)
PARTITIONED BY (ingestion_date STRING)
STORED AS PARQUET
LOCATION 's3://${var:data_lake_bucket}/bronze/pricing/'
TBLPROPERTIES ('classification' = 'parquet');
