-- Bronze table: raw supplier_data CSV partitioned by ingestion date.
-- Tool routing: glue-athena MCP -> create_database + Glue Crawler.

CREATE EXTERNAL TABLE IF NOT EXISTS supplier_chain_data_db.bronze_supplier_chain_data (
    buyer_name              STRING,
    buyer_ticker            STRING,
    supplier_name           STRING,
    supplier_ticker         STRING,
    relationship_type       STRING,
    supply_concentration_pct STRING,
    product_category        STRING,
    effective_date          STRING,
    contract_value_usd      STRING,
    supplier_address        STRING,
    contact_email           STRING
)
PARTITIONED BY (ingestion_date STRING)
STORED AS PARQUET
LOCATION 's3://${var:data_lake_bucket}/bronze/supplier_chain_data/'
TBLPROPERTIES ('classification' = 'parquet');
