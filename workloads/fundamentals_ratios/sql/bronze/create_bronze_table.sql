-- Bronze table: raw ff_ratios CSV partitioned by ingestion date.
-- Tool routing: glue-athena MCP -> create_database + Glue Crawler.

CREATE EXTERNAL TABLE IF NOT EXISTS fundamentals_ratios_db.bronze_fundamentals_ratios (
    entity_id        STRING,
    fiscal_period_id STRING,
    fiscal_year      STRING,
    pe_ratio         STRING,
    pb_ratio         STRING,
    ev_ebitda        STRING,
    roe              STRING,
    roa              STRING,
    debt_to_equity   STRING,
    current_ratio    STRING,
    load_timestamp   STRING
)
PARTITIONED BY (ingestion_date STRING)
STORED AS PARQUET
LOCATION 's3://${var:data_lake_bucket}/bronze/fundamentals_ratios/'
TBLPROPERTIES ('classification' = 'parquet');
