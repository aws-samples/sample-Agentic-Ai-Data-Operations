-- Bronze table: raw fe_sales_ntm CSV partitioned by ingestion date.
-- Tool routing: glue-athena MCP -> create_database + Glue Crawler.

CREATE EXTERNAL TABLE IF NOT EXISTS estimates_sales_ntm_db.bronze_estimates_sales_ntm (
    entity_id       STRING,
    estimate_date   STRING,
    metric          STRING,
    value           STRING,
    currency        STRING,
    value_usd       STRING,
    num_analysts    STRING,
    source          STRING,
    load_timestamp  STRING
)
PARTITIONED BY (ingestion_date STRING)
STORED AS PARQUET
LOCATION 's3://${var:data_lake_bucket}/bronze/estimates_sales_ntm/'
TBLPROPERTIES ('classification' = 'parquet');
