-- Business question: In which seller states do parcels leave the seller late
-- most often?
-- Grain: one row per seller state.
-- Metrics (item level, one row per order item):
--   items_handed_over      items whose order has a usable carrier handover date
--   items_dispatched_late  of those, items handed over after order_items.shipping_limit_date
--                          (timestamps compared; the deadline has a real time of day)
--   late_dispatch_rate     items_dispatched_late / items_handed_over
-- Carrier date handling: same as 08a. Carrier dates before the purchase or after
-- the customer delivery are unreliable (Phase 1 checks 08 and 09). Those items
-- are excluded from the rate and counted in items_excluded_unreliable_carrier_date.
-- Items never handed over are not counted.
-- Threshold: states need at least 30 handed-over items (variable
-- min_seller_state_items, default 30).
WITH items AS (
    SELECT
        s.seller_state,
        i.shipping_limit_date,
        o.order_delivered_carrier_date AS carrier_date,
        CASE
            WHEN o.order_delivered_carrier_date IS NULL THEN 'not_handed_over'
            WHEN o.order_purchase_timestamp IS NULL
              OR o.order_delivered_carrier_date < o.order_purchase_timestamp THEN 'unreliable'
            WHEN o.order_delivered_carrier_date > o.order_delivered_customer_date THEN 'unreliable'
            ELSE 'valid'
        END AS carrier_date_status
    FROM stg_order_items i
    JOIN int_orders o USING (order_id)
    LEFT JOIN stg_sellers s USING (seller_id)
),
by_state AS (
    SELECT
        seller_state,
        count(*) FILTER (WHERE carrier_date_status = 'valid') AS items_handed_over,
        count(*) FILTER (WHERE carrier_date_status = 'valid'
                           AND carrier_date > shipping_limit_date) AS items_dispatched_late,
        count(*) FILTER (WHERE carrier_date_status = 'unreliable') AS items_excluded_unreliable_carrier_date
    FROM items
    GROUP BY seller_state
)
SELECT
    seller_state,
    items_handed_over,
    items_dispatched_late,
    round(items_dispatched_late / items_handed_over, 4) AS late_dispatch_rate,
    items_excluded_unreliable_carrier_date
FROM by_state
WHERE items_handed_over >= coalesce(getvariable('min_seller_state_items'), 30)
ORDER BY late_dispatch_rate DESC, items_handed_over DESC, seller_state;
