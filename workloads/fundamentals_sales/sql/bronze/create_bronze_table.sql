-- Bronze table: raw ff_sales CSV partitioned by ingestion date.
-- Tool routing: glue-athena MCP -> create_database + Glue Crawler.

CREATE EXTERNAL TABLE IF NOT EXISTS fundamentals_sales_db.bronze_fundamentals_sales (
    entity_id        STRING,
    fiscal_period_id STRING,
    fiscal_year      STRING,
    fiscal_period    STRING,
    period_end_date  STRING,
    metric           STRING,
    value            STRING,
    currency         STRING,
    value_usd        STRING,
    source           STRING,
    load_timestamp   STRING
)
PARTITIONED BY (ingestion_date STRING)
STORED AS PARQUET
LOCATION 's3://${var:data_lake_bucket}/bronze/fundamentals_sales/'
TBLPROPERTIES ('classification' = 'parquet');
