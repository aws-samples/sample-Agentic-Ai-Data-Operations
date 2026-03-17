-- ============================================================================
-- Top 10 Analytical Queries for Sales & Marketing
-- Database: demo_database_ai_agents_goldzone
-- Workload: order_transactions
-- ============================================================================

-- ============================================================================
-- Query 1: Total Revenue by Region (Completed Orders Only)
-- Purpose: Regional sales performance overview
-- ============================================================================
SELECT
    r.region_name,
    SUM(f.revenue) AS total_revenue,
    COUNT(f.order_id) AS order_count,
    ROUND(AVG(f.revenue), 2) AS avg_order_value
FROM demo_database_ai_agents_goldzone.order_fact f
JOIN demo_database_ai_agents_goldzone.dim_region r
    ON f.region_id = r.region_id
WHERE f.status_name = 'Completed'
GROUP BY r.region_name
ORDER BY total_revenue DESC
LIMIT 100;

-- ============================================================================
-- Query 2: Top 10 Products by Revenue
-- Purpose: Identify best-selling products
-- ============================================================================
SELECT
    p.product_name,
    p.category,
    SUM(f.revenue) AS total_revenue,
    SUM(f.quantity) AS total_units_sold,
    ROUND(AVG(f.unit_price), 2) AS avg_unit_price
FROM demo_database_ai_agents_goldzone.order_fact f
JOIN demo_database_ai_agents_goldzone.dim_product p
    ON f.product_id = p.product_id
WHERE f.status_name = 'Completed'
GROUP BY p.product_name, p.category
ORDER BY total_revenue DESC
LIMIT 10;

-- ============================================================================
-- Query 3: Revenue by Category and Region
-- Purpose: Category performance across regions (heatmap data)
-- ============================================================================
SELECT
    p.category,
    r.region_name,
    SUM(f.revenue) AS total_revenue,
    COUNT(f.order_id) AS order_count,
    SUM(f.quantity) AS total_quantity
FROM demo_database_ai_agents_goldzone.order_fact f
JOIN demo_database_ai_agents_goldzone.dim_product p
    ON f.product_id = p.product_id
JOIN demo_database_ai_agents_goldzone.dim_region r
    ON f.region_id = r.region_id
WHERE f.status_name = 'Completed'
GROUP BY p.category, r.region_name
ORDER BY p.category, total_revenue DESC
LIMIT 100;

-- ============================================================================
-- Query 4: Monthly Revenue Trend
-- Purpose: Time-series analysis for dashboards
-- ============================================================================
SELECT
    SUBSTRING(f.order_date, 1, 7) AS month,
    SUM(f.revenue) AS total_revenue,
    COUNT(f.order_id) AS order_count,
    ROUND(AVG(f.revenue), 2) AS avg_order_value,
    SUM(f.quantity) AS total_quantity
FROM demo_database_ai_agents_goldzone.order_fact f
WHERE f.status_name = 'Completed'
GROUP BY SUBSTRING(f.order_date, 1, 7)
ORDER BY month
LIMIT 100;

-- ============================================================================
-- Query 5: Average Order Value by Category
-- Purpose: Pricing and category strategy insights
-- ============================================================================
SELECT
    p.category,
    COUNT(f.order_id) AS order_count,
    ROUND(AVG(f.revenue), 2) AS avg_order_value,
    ROUND(MIN(f.revenue), 2) AS min_order_value,
    ROUND(MAX(f.revenue), 2) AS max_order_value,
    ROUND(AVG(f.unit_price), 2) AS avg_unit_price,
    ROUND(AVG(f.discount_pct) * 100, 1) AS avg_discount_pct
FROM demo_database_ai_agents_goldzone.order_fact f
JOIN demo_database_ai_agents_goldzone.dim_product p
    ON f.product_id = p.product_id
WHERE f.status_name = 'Completed'
GROUP BY p.category
ORDER BY avg_order_value DESC
LIMIT 100;

-- ============================================================================
-- Query 6: Order Count and Revenue by Status
-- Purpose: Pipeline health - how many orders complete vs cancel
-- ============================================================================
SELECT
    s.status_name,
    COUNT(f.order_id) AS order_count,
    SUM(f.revenue) AS total_revenue,
    ROUND(AVG(f.revenue), 2) AS avg_order_value,
    ROUND(100.0 * COUNT(f.order_id) / SUM(COUNT(f.order_id)) OVER (), 1) AS pct_of_orders
FROM demo_database_ai_agents_goldzone.order_fact f
JOIN demo_database_ai_agents_goldzone.dim_status s
    ON f.status_id = s.status_id
GROUP BY s.status_name
ORDER BY order_count DESC
LIMIT 100;

-- ============================================================================
-- Query 7: Top 10 Customers by Total Spend
-- Purpose: High-value customer identification (JOIN to customer_master)
-- ============================================================================
SELECT
    c.customer_id,
    c.customer_name,
    c.segment,
    c.industry,
    SUM(f.revenue) AS total_spend,
    COUNT(f.order_id) AS order_count,
    ROUND(AVG(f.revenue), 2) AS avg_order_value
FROM demo_database_ai_agents_goldzone.order_fact f
JOIN demo_database_ai_agents_goldzone.dim_customer c
    ON f.customer_id = c.customer_id
WHERE f.status_name = 'Completed'
GROUP BY c.customer_id, c.customer_name, c.segment, c.industry
ORDER BY total_spend DESC
LIMIT 10;

-- ============================================================================
-- Query 8: Revenue by Customer Segment
-- Purpose: Segment-level analysis (JOIN to customer_master)
-- ============================================================================
SELECT
    c.segment,
    COUNT(DISTINCT f.customer_id) AS customer_count,
    COUNT(f.order_id) AS order_count,
    SUM(f.revenue) AS total_revenue,
    ROUND(AVG(f.revenue), 2) AS avg_order_value,
    ROUND(SUM(f.revenue) / COUNT(DISTINCT f.customer_id), 2) AS revenue_per_customer
FROM demo_database_ai_agents_goldzone.order_fact f
JOIN demo_database_ai_agents_goldzone.dim_customer c
    ON f.customer_id = c.customer_id
WHERE f.status_name = 'Completed'
GROUP BY c.segment
ORDER BY total_revenue DESC
LIMIT 100;

-- ============================================================================
-- Query 9: Discount Impact Analysis
-- Purpose: Understand how discounts affect revenue and order volume
-- ============================================================================
SELECT
    CASE
        WHEN f.discount_pct = 0 THEN 'No Discount'
        WHEN f.discount_pct <= 0.10 THEN '1-10%'
        WHEN f.discount_pct <= 0.15 THEN '11-15%'
        WHEN f.discount_pct <= 0.20 THEN '16-20%'
        ELSE '21%+'
    END AS discount_band,
    COUNT(f.order_id) AS order_count,
    SUM(f.revenue) AS total_revenue,
    ROUND(AVG(f.revenue), 2) AS avg_order_value,
    ROUND(AVG(f.quantity), 1) AS avg_quantity,
    ROUND(AVG(f.unit_price), 2) AS avg_unit_price
FROM demo_database_ai_agents_goldzone.order_fact f
WHERE f.status_name = 'Completed'
GROUP BY
    CASE
        WHEN f.discount_pct = 0 THEN 'No Discount'
        WHEN f.discount_pct <= 0.10 THEN '1-10%'
        WHEN f.discount_pct <= 0.15 THEN '11-15%'
        WHEN f.discount_pct <= 0.20 THEN '16-20%'
        ELSE '21%+'
    END
ORDER BY total_revenue DESC
LIMIT 100;

-- ============================================================================
-- Query 10: Category Performance by Region
-- Purpose: Detailed breakdown for regional marketing strategy
-- ============================================================================
SELECT
    r.region_name,
    p.category,
    COUNT(f.order_id) AS order_count,
    SUM(f.quantity) AS total_quantity,
    SUM(f.revenue) AS total_revenue,
    ROUND(AVG(f.revenue), 2) AS avg_order_value,
    ROUND(AVG(f.discount_pct) * 100, 1) AS avg_discount_pct,
    ROUND(100.0 * SUM(f.revenue) / SUM(SUM(f.revenue)) OVER (PARTITION BY r.region_name), 1) AS pct_of_region_revenue
FROM demo_database_ai_agents_goldzone.order_fact f
JOIN demo_database_ai_agents_goldzone.dim_product p
    ON f.product_id = p.product_id
JOIN demo_database_ai_agents_goldzone.dim_region r
    ON f.region_id = r.region_id
WHERE f.status_name = 'Completed'
GROUP BY r.region_name, p.category
ORDER BY r.region_name, total_revenue DESC
LIMIT 100;
