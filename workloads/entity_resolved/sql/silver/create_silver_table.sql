-- Silver table: cleansed entity master — Apache Iceberg on S3 Tables.
-- Tool routing: glue-athena MCP -> Iceberg DDL (Silver is ALWAYS Iceberg).
--
-- Schema decisions:
--   * sedol dropped (100% null in source)
--   * aliases pipe-delimited string -> array<string>
--   * fiscal_year_end_month cast string -> int
--   * cusip kept nullable (non-US/CA entities legitimately lack one)
--   * No partitioning: ~55-row reference table.

CREATE TABLE IF NOT EXISTS s3tablesbucket.entity_resolved_db.silver_entity_resolved (
    entity_id              STRING          NOT NULL,
    entity_name            STRING          NOT NULL,
    ticker                 STRING          NOT NULL,
    aliases                ARRAY<STRING>,
    isin                   STRING,
    cusip                  STRING,
    exchange               STRING,
    country                STRING          NOT NULL,
    sector                 STRING,
    industry               STRING,
    fiscal_year_end_month  INT,
    ingestion_ts           TIMESTAMP
)
USING iceberg
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
