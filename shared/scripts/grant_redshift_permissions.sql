
-- Grant USAGE on schema to demo_role
GRANT USAGE ON SCHEMA public TO demo_role;
GRANT USAGE ON SCHEMA bronze_schema TO demo_role;
GRANT USAGE ON SCHEMA silver_schema TO demo_role;
GRANT USAGE ON SCHEMA gold_schema TO demo_role;

-- Grant SELECT on all tables in each schema
GRANT SELECT ON ALL TABLES IN SCHEMA public TO demo_role;
GRANT SELECT ON ALL TABLES IN SCHEMA bronze_schema TO demo_role;
GRANT SELECT ON ALL TABLES IN SCHEMA silver_schema TO demo_role;
GRANT SELECT ON ALL TABLES IN SCHEMA gold_schema TO demo_role;

-- Grant SELECT on future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO demo_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA bronze_schema GRANT SELECT ON TABLES TO demo_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA silver_schema GRANT SELECT ON TABLES TO demo_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold_schema GRANT SELECT ON TABLES TO demo_role;

-- Grant access to external schemas (Spectrum - if using Glue Catalog with Redshift)
GRANT USAGE ON SCHEMA spectrum_bronze TO demo_role;
GRANT USAGE ON SCHEMA spectrum_silver TO demo_role;
GRANT USAGE ON SCHEMA spectrum_gold TO demo_role;

-- Grant SELECT on Spectrum tables
GRANT SELECT ON ALL TABLES IN SCHEMA spectrum_bronze TO demo_role;
GRANT SELECT ON ALL TABLES IN SCHEMA spectrum_silver TO demo_role;
GRANT SELECT ON ALL TABLES IN SCHEMA spectrum_gold TO demo_role;
