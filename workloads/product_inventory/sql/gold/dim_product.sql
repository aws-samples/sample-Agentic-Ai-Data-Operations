-- Create dim_product from Silver zone
-- Product master dimension with SCD Type 1 (overwrite)
-- Contains product attributes and business keys

WITH silver_data AS (
    -- Load cleaned data from Silver zone
    SELECT *
    FROM ${database}.${schema}.silver_product_inventory
),

unique_products AS (
    -- Get unique products (deduplicate if multiple warehouse locations)
    SELECT DISTINCT
        product_id,
        sku,
        product_name,
        category,
        subcategory,
        brand,
        status
    FROM silver_data
),

products_with_keys AS (
    -- Assign surrogate keys
    SELECT
        ROW_NUMBER() OVER (ORDER BY product_id) AS product_key,
        product_id,
        sku,
        product_name,
        category,
        subcategory,
        brand,
        status
    FROM unique_products
)

SELECT
    product_key,
    product_id,
    sku,
    product_name,
    category,
    subcategory,
    brand,
    status
FROM products_with_keys
ORDER BY product_key
LIMIT 10000;

-- Notes:
-- - product_key is surrogate key (sequential integer)
-- - product_id and sku are natural/business keys from source
-- - SCD Type 1: updates overwrite existing records (no history tracking)
-- - In production, this would be an Iceberg table with MERGE operations for updates
-- - Dimension provides descriptive attributes for fact table analysis
