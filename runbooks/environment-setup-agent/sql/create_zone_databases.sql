-- ==========================================================================
-- Zone Databases: Create once, shared by all workloads
-- Run this BEFORE any workload table DDL.
--
-- Databases:
--   landing_db  - Raw, immutable source data (CSV, JSON, Parquet)
--   staging_db  - Cleaned, validated data (Apache Iceberg, format-version=2)
--   publish_db  - Curated, business-ready data (Apache Iceberg star schemas)
--
-- Encryption: Each zone uses a dedicated KMS key for SSE-KMS at rest.
-- Catalog metadata is encrypted with alias/catalog-metadata-key.
--
-- Execute via Athena or Glue Job:
--   aws athena start-query-execution \
--     --query-string "$(cat create_zone_databases.sql)" \
--     --work-group primary
--
-- NOTE: Athena does not support multiple statements in one execution.
--       Run each CREATE DATABASE as a separate query, or use a Glue Job /
--       Step Functions state machine to execute sequentially.
-- ==========================================================================

-- -------------------------------------------------------------------------
-- Landing Zone Database
-- Raw source data, write-once immutable. Crawled by Glue Crawler.
-- -------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS landing_db
    COMMENT 'Landing zone - raw, immutable source data (write-once)'
    LOCATION 's3://${s3_landing_bucket}/landing/'
    WITH DBPROPERTIES (
        'data_zone'         = 'landing',
        'encryption_key'    = 'alias/landing-data-key',
        'managed_by'        = 'agentic-data-onboarding',
        'created_by'        = 'shared/sql/common/create_zone_databases.sql'
    );

-- -------------------------------------------------------------------------
-- Staging Zone Database
-- Cleaned, validated, schema-enforced Apache Iceberg tables.
-- Quality gate: score >= 0.80, no critical failures.
-- -------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS staging_db
    COMMENT 'Staging zone - cleaned, validated Iceberg tables (quality gate >= 0.80)'
    LOCATION 's3://${s3_staging_bucket}/staging/'
    WITH DBPROPERTIES (
        'data_zone'         = 'staging',
        'encryption_key'    = 'alias/staging-data-key',
        'table_format'      = 'apache_iceberg',
        'format_version'    = '2',
        'quality_threshold' = '0.80',
        'managed_by'        = 'agentic-data-onboarding',
        'created_by'        = 'shared/sql/common/create_zone_databases.sql'
    );

-- -------------------------------------------------------------------------
-- Publish Zone Database
-- Curated, business-ready Apache Iceberg tables (star schemas, aggregates).
-- Quality gate: score >= 0.95, no critical failures.
-- -------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS publish_db
    COMMENT 'Publish zone - curated, business-ready Iceberg tables (quality gate >= 0.95)'
    LOCATION 's3://${s3_publish_bucket}/publish/'
    WITH DBPROPERTIES (
        'data_zone'         = 'publish',
        'encryption_key'    = 'alias/publish-data-key',
        'table_format'      = 'apache_iceberg',
        'format_version'    = '2',
        'quality_threshold' = '0.95',
        'managed_by'        = 'agentic-data-onboarding',
        'created_by'        = 'shared/sql/common/create_zone_databases.sql'
    );
