-- Bronze table: raw ff_balance_sheet CSV partitioned by ingestion date.
-- Tool routing: glue-athena MCP -> create_database + Glue Crawler.

CREATE EXTERNAL TABLE IF NOT EXISTS fundamentals_balance_sheet_db.bronze_fundamentals_balance_sheet (
    entity_id              STRING,
    fiscal_period_id       STRING,
    fiscal_year            STRING,
    total_assets           STRING,
    total_liabilities      STRING,
    total_equity           STRING,
    cash_and_equivalents   STRING,
    total_debt             STRING,
    currency               STRING,
    value_usd_total_assets STRING
)
PARTITIONED BY (ingestion_date STRING)
STORED AS PARQUET
LOCATION 's3://${var:data_lake_bucket}/bronze/fundamentals_balance_sheet/'
TBLPROPERTIES ('classification' = 'parquet');
