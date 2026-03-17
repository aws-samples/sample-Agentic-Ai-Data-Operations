-- Create dim_warehouse from Silver zone
-- Warehouse location dimension with derived region attribute
-- SCD Type 1 (overwrite)

WITH silver_data AS (
    -- Load cleaned data from Silver zone
    SELECT *
    FROM ${database}.${schema}.silver_product_inventory
),

unique_warehouses AS (
    -- Get unique warehouse locations
    SELECT DISTINCT
        warehouse_location
    FROM silver_data
    WHERE warehouse_location IS NOT NULL
),

warehouses_with_region AS (
    -- Derive region from warehouse location code
    SELECT
        warehouse_location,
        CASE
            WHEN UPPER(warehouse_location) LIKE '%EAST%' THEN 'EAST'
            WHEN UPPER(warehouse_location) LIKE '%WEST%' THEN 'WEST'
            WHEN UPPER(warehouse_location) LIKE '%CENTRAL%' THEN 'CENTRAL'
            ELSE 'UNKNOWN'
        END AS region
    FROM unique_warehouses
),

warehouses_with_keys AS (
    -- Assign surrogate keys
    SELECT
        ROW_NUMBER() OVER (ORDER BY warehouse_location) AS warehouse_key,
        warehouse_location,
        region
    FROM warehouses_with_region
)

SELECT
    warehouse_key,
    warehouse_location,
    region
FROM warehouses_with_keys
ORDER BY warehouse_key
LIMIT 10000;

-- Notes:
-- - warehouse_key is surrogate key (sequential integer)
-- - warehouse_location is natural/business key from source
-- - region is derived from warehouse_location code pattern (EAST/WEST/CENTRAL)
-- - SCD Type 1: updates overwrite existing records (no history tracking)
-- - In production, this would be an Iceberg table with MERGE operations
-- - Region enables geographic aggregation and analysis in fact queries
