-- Bronze table: raw ref_classifications CSV partitioned by ingestion date.
-- Tool routing: glue-athena MCP -> create_database + Glue Crawler.

CREATE EXTERNAL TABLE IF NOT EXISTS reference_db.bronze_reference (
    entity_id              STRING,
    classification_system  STRING,
    sector_code            STRING,
    sector_name            STRING,
    industry_group_code    STRING,
    industry_group_name    STRING,
    industry_code          STRING,
    industry_name          STRING
)
PARTITIONED BY (ingestion_date STRING)
STORED AS PARQUET
LOCATION 's3://${var:data_lake_bucket}/bronze/reference/'
TBLPROPERTIES ('classification' = 'parquet');
