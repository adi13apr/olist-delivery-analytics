-- Business question: How many customers come back, and how much revenue do
-- they bring?
-- Grain: one row per segment: one_time (1 order) and repeat (more than 1 order).
-- A customer is a customer_unique_id; customer_id is issued per order in Olist,
-- so it cannot identify returning customers.
-- Metrics:
--   orders          orders that are neither canceled nor unavailable (a cancel
--                   followed by a reorder does not make a repeat customer)
--   gmv             sum of order_items.price over those orders (freight excluded)
--   customer_share  segment customers / all customers
--   gmv_share       segment gmv / all gmv
-- Threshold: none; two segments over the whole customer base.
WITH customer_orders AS (
    SELECT
        customer_unique_id,
        count(*) AS orders,
        sum(order_gmv) AS gmv
    FROM int_orders
    WHERE is_gmv_order
    GROUP BY customer_unique_id
),
segments AS (
    SELECT
        CASE WHEN orders > 1 THEN 'repeat' ELSE 'one_time' END AS segment,
        count(*) AS customers,
        sum(orders) AS orders,
        sum(gmv) AS gmv
    FROM customer_orders
    GROUP BY segment
)
SELECT
    segment,
    customers,
    orders,
    round(gmv, 2) AS gmv,
    round(orders / customers, 2) AS orders_per_customer,
    round(customers / sum(customers) OVER (), 4) AS customer_share,
    round(gmv / sum(gmv) OVER (), 4) AS gmv_share
FROM segments
ORDER BY segment;
