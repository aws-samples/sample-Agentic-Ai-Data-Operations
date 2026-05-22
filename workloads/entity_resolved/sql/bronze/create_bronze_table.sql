-- Bronze table: raw entity_resolved CSV partitioned by ingestion date.
-- Tool routing: glue-athena MCP -> create_database + Glue Crawler for auto-registration.
-- Bronze format: Parquet (raw source preserved, partitioned by ingestion_date).

CREATE EXTERNAL TABLE IF NOT EXISTS entity_resolved_db.bronze_entity_resolved (
    entity_id              STRING,
    entity_name            STRING,
    ticker                 STRING,
    aliases                STRING,
    isin                   STRING,
    cusip                  STRING,
    sedol                  STRING,
    exchange               STRING,
    country                STRING,
    sector                 STRING,
    industry               STRING,
    fiscal_year_end_month  STRING
)
PARTITIONED BY (ingestion_date STRING)
STORED AS PARQUET
LOCATION 's3://${var:data_lake_bucket}/bronze/entity_resolved/'
TBLPROPERTIES ('classification' = 'parquet');
