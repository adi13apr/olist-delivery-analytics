-- Shared definitions for the Phase 2 analysis queries in sql/analysis/.
-- Built by scripts/load.py right after sql/01_staging.sql.

-- One row per order for business analysis.
-- * Orders with a duplicated order_id are left out: Phase 1 found no rule for
--   picking the right copy (0 such orders in the real data).
-- * Delivery columns (is_delivery_metric_eligible, delivery_days, is_late) are
--   passed through from stg_orders unchanged, never re-derived.
-- * GMV order: status is neither canceled nor unavailable.
--   order_gmv: sum of order_items.price (freight excluded) for GMV orders,
--   0 for a GMV order with no items, NULL for canceled/unavailable orders.
CREATE OR REPLACE VIEW int_orders AS
WITH items AS (
    SELECT
        order_id,
        count(*) AS item_count,
        sum(price) AS items_price
    FROM stg_order_items
    WHERE has_matching_order
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.customer_id,
    c.customer_unique_id,
    c.customer_state,
    o.order_status,
    o.order_purchase_timestamp,
    date_trunc('month', o.order_purchase_timestamp)::DATE AS purchase_month,
    -- DuckDB weeks start on Monday (ISO).
    date_trunc('week', o.order_purchase_timestamp)::DATE AS purchase_week,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,
    o.is_delivery_metric_eligible,
    o.delivery_days,
    o.is_late,
    o.order_status NOT IN ('canceled', 'unavailable') AS is_gmv_order,
    coalesce(i.item_count, 0) AS item_count,
    CASE WHEN o.order_status NOT IN ('canceled', 'unavailable')
        THEN coalesce(i.items_price, 0)
    END AS order_gmv
FROM stg_orders o
LEFT JOIN stg_customers c USING (customer_id)
LEFT JOIN items i USING (order_id)
WHERE o.exclusion_reason IS DISTINCT FROM 'duplicate_order_id';

-- Every calendar month from the first to the last purchase month, including
-- months with no orders, and whether it belongs in trend views.
-- Rule: a month qualifies when its orders are at least 10% of the median month
-- (variable min_month_share_of_median, default 0.10). Trend months are the
-- longest unbroken run of qualifying months; ties go to the later run.
CREATE OR REPLACE VIEW int_months AS
WITH bounds AS (
    SELECT min(purchase_month) AS first_month, max(purchase_month) AS last_month
    FROM int_orders
),
spine AS (
    SELECT unnest(generate_series(first_month, last_month, INTERVAL 1 MONTH))::DATE AS month
    FROM bounds
),
monthly AS (
    SELECT s.month, count(o.order_id) AS orders
    FROM spine s
    LEFT JOIN int_orders o ON o.purchase_month = s.month
    GROUP BY s.month
),
qualified AS (
    SELECT
        month,
        orders,
        orders >= coalesce(getvariable('min_month_share_of_median'), 0.10)
            * median(orders) OVER () AS meets_volume
    FROM monthly
),
-- Gaps and islands: every failing month starts a new run.
runs AS (
    SELECT
        *,
        sum(CASE WHEN meets_volume THEN 0 ELSE 1 END) OVER (ORDER BY month) AS run_id
    FROM qualified
),
longest AS (
    SELECT run_id
    FROM runs
    WHERE meets_volume
    GROUP BY run_id
    ORDER BY count(*) DESC, min(month) DESC
    LIMIT 1
)
SELECT
    r.month,
    r.orders,
    coalesce(r.meets_volume AND r.run_id = l.run_id, false) AS is_trend_month,
    CASE
        WHEN NOT r.meets_volume THEN 'below_volume_threshold'
        WHEN r.run_id IS DISTINCT FROM l.run_id THEN 'outside_longest_run'
    END AS exclusion_reason
FROM runs r
LEFT JOIN longest l ON true
ORDER BY r.month;

-- Black Friday 2017 (Fri 24 Nov) event analysis periods, both ends inclusive,
-- by purchase date. Event: Black Friday through Cyber Monday (4 days).
-- Baseline: the 4 weeks (28 days) immediately before the event.
CREATE OR REPLACE VIEW int_black_friday_periods AS
SELECT
    period,
    start_date,
    end_date,
    date_diff('day', start_date, end_date) + 1 AS days
FROM (
    VALUES
        ('baseline', DATE '2017-10-27', DATE '2017-11-23'),
        ('event', DATE '2017-11-24', DATE '2017-11-27')
) AS p (period, start_date, end_date);
