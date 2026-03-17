-- Create fact_inventory from Silver zone
-- Fact table for inventory snapshot with measures and foreign keys
-- Grain: One row per product per warehouse location

WITH silver_data AS (
    -- Load cleaned data from Silver zone
    SELECT *
    FROM ${database}.${schema}.silver_product_inventory
),

product_lookup AS (
    -- Get product surrogate keys
    SELECT product_key, product_id
    FROM ${database}.${schema}.dim_product
),

supplier_lookup AS (
    -- Get supplier surrogate keys
    SELECT supplier_key, supplier_id
    FROM ${database}.${schema}.dim_supplier
),

warehouse_lookup AS (
    -- Get warehouse surrogate keys
    SELECT warehouse_key, warehouse_location
    FROM ${database}.${schema}.dim_warehouse
),

fact_base AS (
    SELECT
        p.product_key,
        s.supplier_key,
        w.warehouse_key,

        -- Measures from Silver
        silver_data.unit_price,
        silver_data.cost_price,
        silver_data.quantity_on_hand,
        silver_data.reorder_level,
        silver_data.reorder_quantity,
        silver_data.weight_kg,

        -- Derived measures
        (silver_data.unit_price - silver_data.cost_price) AS margin,

        CASE
            WHEN silver_data.unit_price > 0 THEN
                ((silver_data.unit_price - silver_data.cost_price) / silver_data.unit_price) * 100
            ELSE 0
        END AS margin_pct,

        (silver_data.unit_price * silver_data.quantity_on_hand) AS inventory_value,

        CASE
            WHEN silver_data.quantity_on_hand <= silver_data.reorder_level THEN true
            ELSE false
        END AS needs_reorder

    FROM silver_data

    -- Join to get surrogate keys
    LEFT JOIN product_lookup p
        ON silver_data.product_id = p.product_id

    LEFT JOIN supplier_lookup s
        ON silver_data.supplier_id = s.supplier_id

    LEFT JOIN warehouse_lookup w
        ON silver_data.warehouse_location = w.warehouse_location

    -- Ensure we have valid keys
    WHERE p.product_key IS NOT NULL
      AND w.warehouse_key IS NOT NULL
)

SELECT
    product_key,
    supplier_key,
    warehouse_key,
    unit_price,
    cost_price,
    margin,
    CAST(margin_pct AS DECIMAL(5,2)) AS margin_pct,
    quantity_on_hand,
    reorder_level,
    reorder_quantity,
    weight_kg,
    CAST(inventory_value AS DECIMAL(12,2)) AS inventory_value,
    needs_reorder
FROM fact_base
ORDER BY product_key, warehouse_key
LIMIT 10000;

-- Notes:
-- - Foreign keys link to dimension tables via surrogate keys
-- - margin = unit_price - cost_price (profit per unit)
-- - margin_pct = margin as percentage of unit_price
-- - inventory_value = total value of stock on hand
-- - needs_reorder flag helps identify items below reorder threshold
-- - In production, this would be an Iceberg table partitioned by warehouse_key
-- - ACID transactions ensure consistent reads across fact and dimension tables
