-- Business question: In which customer states did average delivery time jump
-- the most from one week to the next?
-- Grain: one row per customer state and purchase week (Monday start) that meets
-- the volume threshold. Only weeks lying entirely inside the trend window
-- (int_months) are used.
-- Metrics:
--   avg_delivery_days      mean stg_orders.delivery_days of eligible orders placed that week
--   wow_change_days        avg_delivery_days minus the previous week's, via LAG(). Only
--                          filled when the previous calendar week also meets the threshold;
--                          a gap leaves it NULL rather than comparing non-adjacent weeks.
--   state_max_wow_increase_days  the state's largest wow_change_days
--   state_increase_rank    RANK() of states by that largest increase (1 = biggest)
--   is_flagged_state       rank <= 5 and the largest increase is positive. Query 10 reads this flag.
-- Threshold: a state-week needs at least 30 eligible orders (variable
-- min_state_week_orders, default 30). Weekly averages of fewer orders swing on
-- one or two slow parcels.
WITH trend_window AS (
    SELECT
        min(month) AS first_day,
        (max(month) + INTERVAL 1 MONTH)::DATE AS end_exclusive
    FROM int_months
    WHERE is_trend_month
),
state_weeks AS (
    SELECT
        o.customer_state,
        o.purchase_week AS week_start,
        count(*) AS eligible_orders,
        avg(o.delivery_days) AS avg_delivery_days
    FROM int_orders o
    CROSS JOIN trend_window w
    WHERE o.is_delivery_metric_eligible
      AND o.purchase_week >= w.first_day
      AND o.purchase_week + 7 <= w.end_exclusive
    GROUP BY o.customer_state, o.purchase_week
),
qualifying AS (
    SELECT customer_state, week_start, eligible_orders, avg_delivery_days
    FROM state_weeks
    WHERE eligible_orders >= coalesce(getvariable('min_state_week_orders'), 30)
),
with_previous AS (
    SELECT
        customer_state,
        week_start,
        eligible_orders,
        avg_delivery_days,
        lag(week_start) OVER w AS prev_week_start,
        lag(avg_delivery_days) OVER w AS prev_avg_delivery_days
    FROM qualifying
    WINDOW w AS (PARTITION BY customer_state ORDER BY week_start)
),
changes AS (
    SELECT
        customer_state,
        week_start,
        eligible_orders,
        avg_delivery_days,
        CASE WHEN date_diff('day', prev_week_start, week_start) = 7
            THEN prev_avg_delivery_days END AS prev_avg_delivery_days,
        CASE WHEN date_diff('day', prev_week_start, week_start) = 7
            THEN avg_delivery_days - prev_avg_delivery_days END AS wow_change_days
    FROM with_previous
),
state_summary AS (
    SELECT
        customer_state,
        max(wow_change_days) AS max_wow_increase,
        CASE WHEN max(wow_change_days) IS NOT NULL
            THEN rank() OVER (ORDER BY max(wow_change_days) DESC NULLS LAST) END AS increase_rank
    FROM changes
    GROUP BY customer_state
)
SELECT
    c.customer_state,
    c.week_start,
    c.eligible_orders,
    round(c.avg_delivery_days, 2) AS avg_delivery_days,
    round(c.prev_avg_delivery_days, 2) AS prev_week_avg_delivery_days,
    round(c.wow_change_days, 2) AS wow_change_days,
    round(s.max_wow_increase, 2) AS state_max_wow_increase_days,
    s.increase_rank AS state_increase_rank,
    coalesce(s.increase_rank <= 5 AND s.max_wow_increase > 0, false) AS is_flagged_state
FROM changes c
JOIN state_summary s USING (customer_state)
ORDER BY s.increase_rank NULLS LAST, c.customer_state, c.week_start;
