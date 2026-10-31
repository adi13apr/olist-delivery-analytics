-- Business question: Which stage of the delivery journey makes late orders
-- late: payment approval, seller dispatch or carrier transit?
-- Grain: one row per scope and delivery outcome. Scope is 'all' (every eligible
-- order) or a customer state flagged in query 02 (is_flagged_state). Outcomes
-- are late, on_time, and late_minus_on_time (the gap between the two).
-- Stages, in fractional days, for eligible orders (stg_orders.is_delivery_metric_eligible):
--   approval  purchase -> order_approved_at
--   dispatch  order_approved_at -> order_delivered_carrier_date (seller handover)
--   transit   order_delivered_carrier_date -> order_delivered_customer_date
-- The three stages add up to the order's delivery time, so only orders whose
-- timestamps are present and in order (purchase <= approved <= carrier <= delivered)
-- are decomposed. The rest stay in eligible_orders and are counted by the first
-- matching reason in the excluded_* columns (Phase 1 checks 08 and 09 found
-- carrier dates before purchase and after delivery; carrier before approval is
-- also common). Late/on-time is stg_orders.is_late; avg_delivery_days is
-- stg_orders.delivery_days over the decomposed orders.
-- Threshold: flagged states already passed query 02's 30-orders-per-week
-- threshold; no further ranking is done here.
WITH flagged_states AS (
    SELECT DISTINCT customer_state
    FROM a02_wow_delivery_by_state
    WHERE is_flagged_state
),
stages AS (
    SELECT
        o.customer_state,
        o.is_late,
        o.delivery_days,
        CASE
            WHEN o.order_approved_at IS NULL OR o.order_delivered_carrier_date IS NULL
                THEN 'missing_stage_timestamp'
            WHEN o.order_approved_at < o.order_purchase_timestamp THEN 'approved_before_purchase'
            WHEN o.order_delivered_carrier_date < o.order_purchase_timestamp THEN 'carrier_before_purchase'
            WHEN o.order_delivered_carrier_date < o.order_approved_at THEN 'carrier_before_approval'
            WHEN o.order_delivered_customer_date < o.order_delivered_carrier_date THEN 'delivered_before_carrier'
        END AS stage_exclusion,
        date_diff('second', o.order_purchase_timestamp, o.order_approved_at) / 86400.0 AS approval_days,
        date_diff('second', o.order_approved_at, o.order_delivered_carrier_date) / 86400.0 AS dispatch_days,
        date_diff('second', o.order_delivered_carrier_date, o.order_delivered_customer_date) / 86400.0 AS transit_days
    FROM int_orders o
    WHERE o.is_delivery_metric_eligible
),
scoped AS (
    SELECT 'all' AS scope, is_late, delivery_days, stage_exclusion, approval_days, dispatch_days, transit_days
    FROM stages
    UNION ALL
    SELECT s.customer_state, s.is_late, s.delivery_days, s.stage_exclusion, s.approval_days, s.dispatch_days, s.transit_days
    FROM stages s
    JOIN flagged_states f USING (customer_state)
),
by_outcome AS (
    SELECT
        scope,
        CASE WHEN is_late THEN 'late' ELSE 'on_time' END AS delivery_status,
        count(*) AS eligible_orders,
        count(*) FILTER (WHERE stage_exclusion IS NULL) AS decomposed_orders,
        count(*) FILTER (WHERE stage_exclusion = 'missing_stage_timestamp') AS excluded_missing_stage_timestamp,
        count(*) FILTER (WHERE stage_exclusion = 'approved_before_purchase') AS excluded_approved_before_purchase,
        count(*) FILTER (WHERE stage_exclusion = 'carrier_before_purchase') AS excluded_carrier_before_purchase,
        count(*) FILTER (WHERE stage_exclusion = 'carrier_before_approval') AS excluded_carrier_before_approval,
        count(*) FILTER (WHERE stage_exclusion = 'delivered_before_carrier') AS excluded_delivered_before_carrier,
        avg(approval_days) FILTER (WHERE stage_exclusion IS NULL) AS avg_approval_days,
        avg(dispatch_days) FILTER (WHERE stage_exclusion IS NULL) AS avg_dispatch_days,
        avg(transit_days) FILTER (WHERE stage_exclusion IS NULL) AS avg_transit_days,
        avg(delivery_days) FILTER (WHERE stage_exclusion IS NULL) AS avg_delivery_days
    FROM scoped
    GROUP BY scope, delivery_status
),
gaps AS (
    SELECT
        scope,
        'late_minus_on_time' AS delivery_status,
        max(avg_approval_days) FILTER (WHERE delivery_status = 'late')
            - max(avg_approval_days) FILTER (WHERE delivery_status = 'on_time') AS avg_approval_days,
        max(avg_dispatch_days) FILTER (WHERE delivery_status = 'late')
            - max(avg_dispatch_days) FILTER (WHERE delivery_status = 'on_time') AS avg_dispatch_days,
        max(avg_transit_days) FILTER (WHERE delivery_status = 'late')
            - max(avg_transit_days) FILTER (WHERE delivery_status = 'on_time') AS avg_transit_days,
        max(avg_delivery_days) FILTER (WHERE delivery_status = 'late')
            - max(avg_delivery_days) FILTER (WHERE delivery_status = 'on_time') AS avg_delivery_days
    FROM by_outcome
    GROUP BY scope
),
-- BY NAME leaves the order counts NULL on the gap rows.
combined AS (
    SELECT
        scope, delivery_status, eligible_orders, decomposed_orders,
        excluded_missing_stage_timestamp, excluded_approved_before_purchase,
        excluded_carrier_before_purchase, excluded_carrier_before_approval,
        excluded_delivered_before_carrier,
        avg_approval_days, avg_dispatch_days, avg_transit_days, avg_delivery_days
    FROM by_outcome
    UNION ALL BY NAME
    SELECT scope, delivery_status, avg_approval_days, avg_dispatch_days, avg_transit_days, avg_delivery_days
    FROM gaps
)
SELECT
    scope,
    delivery_status,
    eligible_orders,
    decomposed_orders,
    excluded_missing_stage_timestamp,
    excluded_approved_before_purchase,
    excluded_carrier_before_purchase,
    excluded_carrier_before_approval,
    excluded_delivered_before_carrier,
    round(avg_approval_days, 2) AS avg_approval_days,
    round(avg_dispatch_days, 2) AS avg_dispatch_days,
    round(avg_transit_days, 2) AS avg_transit_days,
    round(avg_delivery_days, 2) AS avg_delivery_days
FROM combined
ORDER BY
    scope <> 'all',
    scope,
    CASE delivery_status WHEN 'late' THEN 1 WHEN 'on_time' THEN 2 ELSE 3 END;
