-- Bronze table: raw ff_cash_flow CSV partitioned by ingestion date.
-- Tool routing: glue-athena MCP -> create_database + Glue Crawler.

CREATE EXTERNAL TABLE IF NOT EXISTS fundamentals_cash_flow_db.bronze_fundamentals_cash_flow (
    entity_id            STRING,
    fiscal_period_id     STRING,
    fiscal_year          STRING,
    operating_cash_flow  STRING,
    capital_expenditure  STRING,
    free_cash_flow       STRING,
    dividends_paid       STRING,
    share_buybacks       STRING,
    currency             STRING,
    value_usd_fcf        STRING,
    load_timestamp       STRING
)
PARTITIONED BY (ingestion_date STRING)
STORED AS PARQUET
LOCATION 's3://${var:data_lake_bucket}/bronze/fundamentals_cash_flow/'
TBLPROPERTIES ('classification' = 'parquet');
