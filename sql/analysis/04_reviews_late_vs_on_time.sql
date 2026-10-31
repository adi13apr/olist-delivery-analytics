-- Business question: How much does a late delivery hurt customer satisfaction?
-- Grain: one row per delivery outcome (late, on_time) over eligible orders.
-- Metrics:
--   eligible_orders        orders eligible for delivery metrics
--   reviewed_orders        those with a review; only the latest review per order
--                          counts (stg_reviews.is_latest_for_order)
--   orders_without_review  eligible orders with no review; counted here, never scored
--   avg_review_score       mean score (1-5) over reviewed orders
--   low_score_share        share of reviewed orders scoring 1 or 2 (order defect proxy)
-- Threshold: none needed; both groups hold thousands of orders on the real data.
WITH latest_review AS (
    SELECT order_id, review_score
    FROM stg_reviews
    WHERE is_latest_for_order
),
by_outcome AS (
    SELECT
        CASE WHEN o.is_late THEN 'late' ELSE 'on_time' END AS delivery_status,
        count(*) AS eligible_orders,
        count(r.order_id) AS reviewed_orders,
        avg(r.review_score) AS avg_review_score,
        count(*) FILTER (WHERE r.review_score <= 2) AS low_score_orders
    FROM int_orders o
    LEFT JOIN latest_review r USING (order_id)
    WHERE o.is_delivery_metric_eligible
    GROUP BY delivery_status
)
SELECT
    delivery_status,
    eligible_orders,
    reviewed_orders,
    eligible_orders - reviewed_orders AS orders_without_review,
    round(avg_review_score, 2) AS avg_review_score,
    low_score_orders,
    round(low_score_orders / nullif(reviewed_orders, 0), 4) AS low_score_share
FROM by_outcome
ORDER BY delivery_status;
