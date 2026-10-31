-- order_items rows whose order_id has no matching order.
SELECT count(*) AS violations
FROM raw_order_items i
WHERE NOT EXISTS (SELECT 1 FROM raw_orders o WHERE o.order_id = i.order_id);
