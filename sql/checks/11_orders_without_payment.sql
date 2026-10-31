-- Distinct orders with no payment row.
SELECT count(DISTINCT o.order_id) AS violations
FROM raw_orders o
WHERE NOT EXISTS (SELECT 1 FROM raw_order_payments p WHERE p.order_id = o.order_id);
