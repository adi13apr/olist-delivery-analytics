-- Business question: Which customer states see the delivery promise broken
-- most often?
-- Grain: one row per customer state.
-- Metrics:
--   eligible_orders  orders eligible for delivery metrics (stg_orders.is_delivery_metric_eligible)
--   late_orders      eligible orders with stg_orders.is_late (delivered on a later
--                    calendar date than the estimated date)
--   late_rate        late_orders / eligible_orders (SLA breach rate)
--   breach_rank      RANK() by late_rate, 1 = worst
-- Threshold: states with fewer than 30 eligible orders are left out (variable
-- min_state_orders, default 30); a handful of orders makes the rate meaningless.
-- All purchase months are used: this is a level, not a trend.
WITH by_state AS (
    SELECT
        customer_state,
        count(*) AS eligible_orders,
        count(*) FILTER (WHERE is_late) AS late_orders
    FROM int_orders
    WHERE is_delivery_metric_eligible
    GROUP BY customer_state
)
SELECT
    customer_state,
    eligible_orders,
    late_orders,
    round(late_orders / eligible_orders, 4) AS late_rate,
    rank() OVER (ORDER BY late_orders / eligible_orders DESC) AS breach_rank
FROM by_state
WHERE eligible_orders >= coalesce(getvariable('min_state_orders'), 30)
ORDER BY breach_rank, customer_state;
