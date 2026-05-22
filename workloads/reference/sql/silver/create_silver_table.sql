-- Silver table: cleansed entity classifications -- Apache Iceberg on S3 Tables.

CREATE TABLE IF NOT EXISTS s3tablesbucket.reference_db.silver_reference (
    entity_id              STRING      NOT NULL,
    classification_system  STRING      NOT NULL,
    sector_code            STRING      NOT NULL,
    sector_name            STRING      NOT NULL,
    industry_group_code    STRING      NOT NULL,
    industry_group_name    STRING      NOT NULL,
    industry_code          STRING      NOT NULL,
    industry_name          STRING      NOT NULL,
    ingestion_ts           TIMESTAMP
)
USING iceberg
PARTITIONED BY (classification_system)
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
