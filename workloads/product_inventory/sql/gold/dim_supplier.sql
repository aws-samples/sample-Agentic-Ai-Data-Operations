-- Create dim_supplier from Silver zone
-- Supplier dimension with SCD Type 1 (overwrite)
-- Contains supplier master data

WITH silver_data AS (
    -- Load cleaned data from Silver zone
    SELECT *
    FROM ${database}.${schema}.silver_product_inventory
),

unique_suppliers AS (
    -- Get unique suppliers
    SELECT DISTINCT
        supplier_id,
        supplier_name
    FROM silver_data
    WHERE supplier_id IS NOT NULL  -- Exclude records with missing supplier
),

suppliers_with_keys AS (
    -- Assign surrogate keys
    SELECT
        ROW_NUMBER() OVER (ORDER BY supplier_id) AS supplier_key,
        supplier_id,
        supplier_name
    FROM unique_suppliers
)

SELECT
    supplier_key,
    supplier_id,
    supplier_name
FROM suppliers_with_keys
ORDER BY supplier_key
LIMIT 10000;

-- Notes:
-- - supplier_key is surrogate key (sequential integer)
-- - supplier_id is natural/business key from source
-- - Records with NULL supplier_id are excluded from dimension
-- - Fact table will have NULL supplier_key for products with missing supplier
-- - SCD Type 1: updates overwrite existing records (no history tracking)
-- - In production, this would be an Iceberg table with MERGE operations
