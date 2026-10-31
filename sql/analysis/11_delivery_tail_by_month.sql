-- Business question: Is the improvement in delivery times late in the data
-- real, or an artefact of slow orders not having been delivered yet
-- (right-censoring)?
-- Grain: one row per trend month (int_months.is_trend_month), by order_purchase_timestamp.
-- Metrics:
--   orders                  all orders placed in the month, any status
--   open_orders             orders not yet delivered, canceled or unavailable
--                           (shipped, invoiced, processing, approved, created)
--   open_order_share        open_orders / orders; a censored month would show a jump here
--   eligible_orders         orders eligible for delivery metrics
--   median/p90/p99_delivery_days  continuous percentiles (quantile_cont) of
--                           stg_orders.delivery_days over eligible orders
--   max_delivery_days       slowest eligible delivery
--   min_days_observable     days from the month's last day to the last customer
--                           delivery anywhere in the data: every order of the month
--                           had at least this long to arrive. Censoring can only
--                           hide deliveries slower than this.
-- Threshold: none needed; every trend month already has at least 10% of the
-- median month's orders.
WITH data_cutoff AS (
    SELECT max(order_delivered_customer_date)::DATE AS last_delivery_date
    FROM int_orders
    WHERE is_delivery_metric_eligible
),
monthly AS (
    SELECT
        m.month AS month_start,
        count(*) AS orders,
        count(*) FILTER (WHERE o.order_status NOT IN ('delivered', 'canceled', 'unavailable')) AS open_orders,
        count(*) FILTER (WHERE o.is_delivery_metric_eligible) AS eligible_orders,
        quantile_cont(o.delivery_days, 0.5) FILTER (WHERE o.is_delivery_metric_eligible) AS median_delivery_days,
        quantile_cont(o.delivery_days, 0.9) FILTER (WHERE o.is_delivery_metric_eligible) AS p90_delivery_days,
        quantile_cont(o.delivery_days, 0.99) FILTER (WHERE o.is_delivery_metric_eligible) AS p99_delivery_days,
        max(o.delivery_days) FILTER (WHERE o.is_delivery_metric_eligible) AS max_delivery_days
    FROM int_months m
    JOIN int_orders o ON o.purchase_month = m.month
    WHERE m.is_trend_month
    GROUP BY m.month
)
SELECT
    mo.month_start,
    mo.orders,
    mo.open_orders,
    round(mo.open_orders / mo.orders, 4) AS open_order_share,
    mo.eligible_orders,
    round(mo.median_delivery_days, 2) AS median_delivery_days,
    round(mo.p90_delivery_days, 2) AS p90_delivery_days,
    round(mo.p99_delivery_days, 2) AS p99_delivery_days,
    round(mo.max_delivery_days, 2) AS max_delivery_days,
    date_diff('day', last_day(mo.month_start), c.last_delivery_date) AS min_days_observable
FROM monthly mo
CROSS JOIN data_cutoff c
ORDER BY mo.month_start;
