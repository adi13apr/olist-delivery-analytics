-- Business question: Which sellers' orders miss the delivery promise most
-- often, compared with other sellers in the same state?
-- Grain: one row per seller. An order with items from several sellers counts
-- once for each of those sellers (each shared the same delivery outcome).
-- Metrics:
--   eligible_orders   eligible orders (stg_orders.is_delivery_metric_eligible) containing the seller's items
--   late_orders       those with stg_orders.is_late
--   late_rate         late_orders / eligible_orders (SLA breach rate)
--   rank_in_state     RANK() within seller_state by late_rate, 1 = worst
-- Threshold: sellers need at least 30 eligible orders (variable
-- min_seller_orders, default 30); the rank only compares qualifying sellers.
-- Caveat: lateness is the whole order's outcome; carrier and customer location
-- also drive it, not just the seller. Query 08 isolates the seller's own step.
WITH order_sellers AS (
    SELECT DISTINCT order_id, seller_id
    FROM stg_order_items
    WHERE has_matching_order
),
by_seller AS (
    SELECT
        os.seller_id,
        s.seller_state,
        count(*) AS eligible_orders,
        count(*) FILTER (WHERE o.is_late) AS late_orders
    FROM int_orders o
    JOIN order_sellers os USING (order_id)
    LEFT JOIN stg_sellers s USING (seller_id)
    WHERE o.is_delivery_metric_eligible
    GROUP BY os.seller_id, s.seller_state
)
SELECT
    seller_id,
    seller_state,
    eligible_orders,
    late_orders,
    round(late_orders / eligible_orders, 4) AS late_rate,
    rank() OVER (PARTITION BY seller_state ORDER BY late_orders / eligible_orders DESC) AS rank_in_state
FROM by_seller
WHERE eligible_orders >= coalesce(getvariable('min_seller_orders'), 30)
ORDER BY seller_state, rank_in_state, seller_id;
