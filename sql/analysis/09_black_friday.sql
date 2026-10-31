-- Business question: What happened to demand and to delivery performance
-- during Black Friday 2017 (Fri 24 Nov), compared with the 4 weeks before?
-- This is event analysis, not an A/B test: there is no control group, so a
-- difference cannot be attributed to the promotion alone (season, carrier
-- capacity and other events in the same weeks are mixed in).
-- Periods (int_black_friday_periods, by purchase date, inclusive):
--   baseline 2017-10-27 to 2017-11-23 (28 days), event 2017-11-24 to 2017-11-27 (4 days).
-- Grain: one row per metric, with the baseline and event values side by side.
-- Metrics:
--   orders, orders_per_day        all orders placed, any status
--   gmv_orders                    orders neither canceled nor unavailable
--   gmv, gmv_per_day              sum of order_items.price for gmv_orders (freight excluded)
--   aov                           gmv / gmv_orders
--   eligible_orders               orders eligible for delivery metrics
--   avg/median_delivery_days      stg_orders.delivery_days over eligible orders
--   late_rate                     share of eligible orders with stg_orders.is_late
--   abs_change = event - baseline; pct_change = abs_change / baseline
-- The significance test on delivery days runs in Python (scripts/significance.py).
-- Threshold: none; two fixed periods with thousands of orders on the real data.
WITH period_orders AS (
    SELECT
        p.period,
        o.order_id,
        o.is_gmv_order,
        o.order_gmv,
        o.is_delivery_metric_eligible,
        o.delivery_days,
        o.is_late
    FROM int_black_friday_periods p
    JOIN int_orders o
      ON o.order_purchase_timestamp::DATE BETWEEN p.start_date AND p.end_date
),
period_stats AS (
    SELECT
        p.period,
        p.days,
        count(o.order_id) AS orders,
        count(o.order_id) FILTER (WHERE o.is_gmv_order) AS gmv_orders,
        coalesce(sum(o.order_gmv), 0) AS gmv,
        count(o.order_id) FILTER (WHERE o.is_delivery_metric_eligible) AS eligible_orders,
        avg(o.delivery_days) FILTER (WHERE o.is_delivery_metric_eligible) AS avg_delivery_days,
        median(o.delivery_days) FILTER (WHERE o.is_delivery_metric_eligible) AS median_delivery_days,
        avg(CASE WHEN o.is_late THEN 1 ELSE 0 END)
            FILTER (WHERE o.is_delivery_metric_eligible) AS late_rate
    FROM int_black_friday_periods p
    LEFT JOIN period_orders o USING (period)
    GROUP BY p.period, p.days
),
metric_values AS (
    SELECT period, metric, value
    FROM (
        SELECT
            period,
            days::DOUBLE AS days_in_period,
            orders::DOUBLE AS orders,
            (orders / days)::DOUBLE AS orders_per_day,
            gmv::DOUBLE AS gmv,
            (gmv / days)::DOUBLE AS gmv_per_day,
            gmv_orders::DOUBLE AS gmv_orders,
            (gmv / nullif(gmv_orders, 0))::DOUBLE AS aov,
            eligible_orders::DOUBLE AS eligible_orders,
            avg_delivery_days::DOUBLE AS avg_delivery_days,
            median_delivery_days::DOUBLE AS median_delivery_days,
            late_rate::DOUBLE AS late_rate
        FROM period_stats
    ) UNPIVOT (value FOR metric IN (
        days_in_period, orders, orders_per_day, gmv, gmv_per_day, gmv_orders, aov,
        eligible_orders, avg_delivery_days, median_delivery_days, late_rate
    ))
),
metric_order (sort_order, metric, decimals) AS (
    VALUES
        (1, 'days_in_period', 0),
        (2, 'orders', 0),
        (3, 'orders_per_day', 2),
        (4, 'gmv', 2),
        (5, 'gmv_per_day', 2),
        (6, 'gmv_orders', 0),
        (7, 'aov', 2),
        (8, 'eligible_orders', 0),
        (9, 'avg_delivery_days', 2),
        (10, 'median_delivery_days', 2),
        (11, 'late_rate', 4)
),
side_by_side AS (
    SELECT
        m.sort_order,
        m.metric,
        m.decimals,
        max(v.value) FILTER (WHERE v.period = 'baseline') AS baseline,
        max(v.value) FILTER (WHERE v.period = 'event') AS event
    FROM metric_order m
    LEFT JOIN metric_values v USING (metric)
    GROUP BY m.sort_order, m.metric, m.decimals
)
SELECT
    metric,
    round(baseline, decimals) AS baseline,
    round(event, decimals) AS event,
    round(event - baseline, decimals) AS abs_change,
    round((event - baseline) / nullif(baseline, 0), 4) AS pct_change
FROM side_by_side
ORDER BY sort_order;
