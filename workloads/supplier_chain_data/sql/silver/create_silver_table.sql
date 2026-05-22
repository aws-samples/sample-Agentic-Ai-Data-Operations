-- Silver table: cleansed buyer-supplier relationships -- Apache Iceberg on S3 Tables.
-- PII columns (contact_email, supplier_address) tagged via Lake Formation
-- (PII_Classification=CONTAINS_PII, Data_Sensitivity=HIGH) post-deployment.

CREATE TABLE IF NOT EXISTS s3tablesbucket.supplier_chain_data_db.silver_supplier_chain_data (
    buyer_name              STRING,
    buyer_ticker            STRING      NOT NULL,
    supplier_name           STRING,
    supplier_ticker         STRING      NOT NULL,
    relationship_type       STRING      NOT NULL,
    supply_concentration_pct DOUBLE,
    product_category        STRING      NOT NULL,
    effective_date          DATE        NOT NULL,
    contract_value_usd      DOUBLE,
    supplier_address        STRING,
    contact_email           STRING,
    ingestion_ts            TIMESTAMP
)
USING iceberg
PARTITIONED BY (relationship_type)
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
