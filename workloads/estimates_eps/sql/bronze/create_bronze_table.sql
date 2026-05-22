-- Bronze table: raw estimates_eps CSV partitioned by ingestion date.
-- Tool routing: glue-athena MCP -> create_database + Glue Crawler.

CREATE EXTERNAL TABLE IF NOT EXISTS estimates_eps_db.bronze_estimates_eps (
    entity_id      STRING,
    estimate_date  STRING,
    period_type    STRING,
    eps_mean       STRING,
    eps_high       STRING,
    eps_low        STRING,
    num_analysts   STRING,
    currency       STRING
)
PARTITIONED BY (ingestion_date STRING)
STORED AS PARQUET
LOCATION 's3://${var:data_lake_bucket}/bronze/estimates_eps/'
TBLPROPERTIES ('classification' = 'parquet');
