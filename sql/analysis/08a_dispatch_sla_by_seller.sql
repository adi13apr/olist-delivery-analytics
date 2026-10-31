-- Business question: Which sellers hand parcels to the carrier after their
-- shipping deadline?
-- Grain: one row per seller.
-- Metrics (item level, one row per order item):
--   items_handed_over      items whose order has a usable carrier handover date
--   items_dispatched_late  of those, items handed over after order_items.shipping_limit_date.
--                          Compared as timestamps: unlike the estimated delivery
--                          date, shipping_limit_date carries a real time of day.
--   late_dispatch_rate     items_dispatched_late / items_handed_over
-- Carrier date handling (Phase 1, DATA_QUALITY.md checks 08 and 09): the carrier
-- date is order level. When it is before the purchase, or after the customer
-- delivery, it is unreliable. Those items are excluded from the rate and
-- counted in items_excluded_unreliable_carrier_date. Items never handed over
-- (no carrier date, e.g. canceled orders) are not counted at all.
-- Threshold: sellers need at least 30 handed-over items (variable
-- min_seller_items, default 30).
WITH items AS (
    SELECT
        i.seller_id,
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
),
by_seller AS (
    SELECT
        seller_id,
        count(*) FILTER (WHERE carrier_date_status = 'valid') AS items_handed_over,
        count(*) FILTER (WHERE carrier_date_status = 'valid'
                           AND carrier_date > shipping_limit_date) AS items_dispatched_late,
        count(*) FILTER (WHERE carrier_date_status = 'unreliable') AS items_excluded_unreliable_carrier_date
    FROM items
    GROUP BY seller_id
)
SELECT
    b.seller_id,
    s.seller_state,
    b.items_handed_over,
    b.items_dispatched_late,
    round(b.items_dispatched_late / b.items_handed_over, 4) AS late_dispatch_rate,
    b.items_excluded_unreliable_carrier_date
FROM by_seller b
LEFT JOIN stg_sellers s USING (seller_id)
WHERE b.items_handed_over >= coalesce(getvariable('min_seller_items'), 30)
ORDER BY late_dispatch_rate DESC, b.items_handed_over DESC, b.seller_id;
