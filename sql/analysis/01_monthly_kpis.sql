-- Business question: How are order volume, revenue and delivery performance
-- trending month by month?
-- Grain: one row per trend month (int_months.is_trend_month), bucketed by
-- order_purchase_timestamp. Sparse or incomplete months are excluded.
-- Metrics:
--   orders                all orders placed in the month, any status
--   gmv_orders            orders whose status is neither canceled nor unavailable
--   gmv                   sum of order_items.price over gmv_orders (freight excluded)
--   aov                   gmv / gmv_orders
--   eligible_orders       orders eligible for delivery metrics (stg_orders.is_delivery_metric_eligible)
--   avg_delivery_days     mean of stg_orders.delivery_days over eligible orders
--   median_delivery_days  median of the same
--   on_time_rate          share of eligible orders with is_late = false
-- Threshold: none needed; every trend month already has at least 10% of the
-- median month's orders, and nothing is ranked.
-- Caveat: the last trend months are right-censored. Orders still in transit
-- when the data was extracted are not delivered, so not eligible, which biases
-- late-2018 delivery days down and on-time rate up.
WITH monthly AS (
    SELECT
        m.month AS month_start,
        count(*) AS orders,
        count(*) FILTER (WHERE o.is_gmv_order) AS gmv_orders,
        sum(o.order_gmv) AS gmv,
        count(*) FILTER (WHERE o.is_delivery_metric_eligible) AS eligible_orders,
        avg(o.delivery_days) FILTER (WHERE o.is_delivery_metric_eligible) AS avg_delivery_days,
        median(o.delivery_days) FILTER (WHERE o.is_delivery_metric_eligible) AS median_delivery_days,
        avg(CASE WHEN o.is_late THEN 0 ELSE 1 END)
            FILTER (WHERE o.is_delivery_metric_eligible) AS on_time_rate
    FROM int_months m
    JOIN int_orders o ON o.purchase_month = m.month
    WHERE m.is_trend_month
    GROUP BY m.month
)
SELECT
    month_start,
    orders,
    gmv_orders,
    round(coalesce(gmv, 0), 2) AS gmv,
    round(gmv / nullif(gmv_orders, 0), 2) AS aov,
    eligible_orders,
    round(avg_delivery_days, 2) AS avg_delivery_days,
    round(median_delivery_days, 2) AS median_delivery_days,
    round(on_time_rate, 4) AS on_time_rate
FROM monthly
ORDER BY month_start;
