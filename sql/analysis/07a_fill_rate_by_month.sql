-- Business question: What share of orders do we fail to fulfil each month
-- (fill-rate proxy)?
-- Grain: one row per trend month (int_months.is_trend_month), by order_purchase_timestamp.
-- Metrics:
--   orders             all orders placed in the month, any status
--   canceled_rate      orders with status canceled / orders
--   unavailable_rate   orders with status unavailable / orders
--   not_fulfilled_rate (canceled + unavailable) / orders; 1 - this is the fill-rate proxy
-- Threshold: none needed; every trend month already has at least 10% of the
-- median month's orders.
WITH monthly AS (
    SELECT
        m.month AS month_start,
        count(*) AS orders,
        count(*) FILTER (WHERE o.order_status = 'canceled') AS canceled_orders,
        count(*) FILTER (WHERE o.order_status = 'unavailable') AS unavailable_orders
    FROM int_months m
    JOIN int_orders o ON o.purchase_month = m.month
    WHERE m.is_trend_month
    GROUP BY m.month
)
SELECT
    month_start,
    orders,
    canceled_orders,
    unavailable_orders,
    round(canceled_orders / orders, 4) AS canceled_rate,
    round(unavailable_orders / orders, 4) AS unavailable_rate,
    round((canceled_orders + unavailable_orders) / orders, 4) AS not_fulfilled_rate
FROM monthly
ORDER BY month_start;
