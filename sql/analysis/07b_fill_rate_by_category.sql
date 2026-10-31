-- Business question: Which product categories have the most canceled or
-- unavailable orders (fill-rate proxy)?
-- Grain: one row per product category (stg_products.category). An order counts
-- once in every category it has items in, so the rows add up to more than the
-- number of orders.
-- Orders with no items at all go to '(no items recorded)'. On the real data
-- almost every unavailable order has no items (603 of 609) and so does about a
-- quarter of canceled orders, so per-category rates undercount unavailability;
-- that row keeps the total visible.
-- Metrics:
--   orders             orders with an item in the category, any status
--   canceled_rate      canceled orders / orders
--   unavailable_rate   unavailable orders / orders
--   not_fulfilled_rate (canceled + unavailable) / orders
-- Threshold: categories with fewer than 30 orders are left out (variable
-- min_category_orders, default 30). All purchase months are used.
WITH order_categories AS (
    SELECT DISTINCT
        i.order_id,
        coalesce(p.category, 'unknown_product') AS category
    FROM stg_order_items i
    LEFT JOIN stg_products p USING (product_id)
    WHERE i.has_matching_order
),
by_category AS (
    SELECT
        coalesce(oc.category, '(no items recorded)') AS category,
        count(*) AS orders,
        count(*) FILTER (WHERE o.order_status = 'canceled') AS canceled_orders,
        count(*) FILTER (WHERE o.order_status = 'unavailable') AS unavailable_orders
    FROM int_orders o
    LEFT JOIN order_categories oc USING (order_id)
    GROUP BY ALL
)
SELECT
    category,
    orders,
    canceled_orders,
    unavailable_orders,
    round(canceled_orders / orders, 4) AS canceled_rate,
    round(unavailable_orders / orders, 4) AS unavailable_rate,
    round((canceled_orders + unavailable_orders) / orders, 4) AS not_fulfilled_rate
FROM by_category
WHERE orders >= coalesce(getvariable('min_category_orders'), 30)
ORDER BY not_fulfilled_rate DESC, orders DESC, category;
