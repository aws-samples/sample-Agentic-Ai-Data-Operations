-- Bronze to Silver Transformation for product_inventory
-- Athena SQL equivalent of bronze_to_silver.py transformations
--
-- This query cleans and validates raw product inventory data:
--   1. Deduplicates on product_id + sku
--   2. Filters negative quantities (would be quarantined)
--   3. Filters future restock dates (would be quarantined)
--   4. Normalizes category casing to title case
--   5. Trims whitespace from product_name
--   6. Maps invalid status 'aktive' to 'active'
--   7. Flags missing supplier information
--   8. Flags margin anomalies (cost > price)
--   9. Flags missing expiry dates for Grocery items
--  10. Fills missing reorder_level with 0

WITH bronze_data AS (
    -- Load raw data from Bronze zone
    SELECT *
    FROM ${database}.${schema}.bronze_product_inventory
),

deduplicated AS (
    -- Step 1: Remove duplicates, keep first occurrence
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY product_id, sku ORDER BY product_id) AS rn
    FROM bronze_data
),

cleaned AS (
    SELECT
        -- Original columns
        product_id,
        sku,

        -- Step 5: Trim whitespace from product_name
        TRIM(product_name) AS product_name,

        -- Step 4: Normalize category casing (Athena doesn't have INITCAP, use regex)
        CONCAT(
            UPPER(SUBSTR(TRIM(category), 1, 1)),
            LOWER(SUBSTR(TRIM(category), 2))
        ) AS category,

        subcategory,
        brand,
        unit_price,
        cost_price,
        quantity_on_hand,

        -- Step 10: Fill missing reorder_level with 0
        COALESCE(reorder_level, 0) AS reorder_level,

        reorder_quantity,
        warehouse_location,
        supplier_id,

        -- Step 7: Fill missing supplier_name
        COALESCE(supplier_name, 'Unknown Supplier') AS supplier_name,

        last_restocked_date,
        expiry_date,
        weight_kg,

        -- Step 6: Fix invalid status values
        CASE
            WHEN LOWER(status) = 'aktive' THEN 'active'
            ELSE status
        END AS status,

        -- Step 7: Flag missing supplier
        CASE
            WHEN supplier_id IS NULL OR supplier_name IS NULL THEN true
            ELSE false
        END AS is_supplier_missing,

        -- Step 8: Flag margin anomaly
        CASE
            WHEN cost_price > unit_price THEN true
            ELSE false
        END AS is_margin_anomaly,

        -- Step 9: Flag missing expiry for Grocery
        CASE
            WHEN CONCAT(
                UPPER(SUBSTR(TRIM(category), 1, 1)),
                LOWER(SUBSTR(TRIM(category), 2))
            ) = 'Grocery' AND expiry_date IS NULL THEN true
            ELSE false
        END AS is_expiry_missing,

        -- Step 10: Flag missing reorder_level
        CASE
            WHEN reorder_level IS NULL THEN true
            ELSE false
        END AS is_reorder_missing,

        -- Processing metadata
        CURRENT_TIMESTAMP AS processing_timestamp

    FROM deduplicated
    WHERE rn = 1  -- Step 1: Keep only first occurrence
      -- Step 2: Exclude negative quantities (would be quarantined)
      AND quantity_on_hand >= 0
      -- Step 3: Exclude future restock dates (would be quarantined)
      AND (last_restocked_date IS NULL OR CAST(last_restocked_date AS DATE) <= CURRENT_DATE)
),

final AS (
    SELECT
        *,
        -- Calculate data quality score
        1.0
        - (CAST(is_supplier_missing AS DOUBLE) * 0.1)
        - (CAST(is_margin_anomaly AS DOUBLE) * 0.2)
        - (CAST(is_expiry_missing AS DOUBLE) * 0.1)
        - (CAST(is_reorder_missing AS DOUBLE) * 0.05) AS data_quality_score
    FROM cleaned
)

SELECT * FROM final
ORDER BY product_id
LIMIT 10000;

-- Notes:
-- - Records with negative quantity_on_hand are excluded (would be quarantined in actual pipeline)
-- - Records with future last_restocked_date are excluded (would be quarantined in actual pipeline)
-- - In production, quarantined records would be written to separate table/location
-- - Iceberg table format provides ACID guarantees and time-travel capabilities
-- - This SQL can be used in Glue ETL jobs or Athena queries
