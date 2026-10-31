-- Distinct orders with no review.
SELECT count(DISTINCT o.order_id) AS violations
FROM raw_orders o
WHERE NOT EXISTS (SELECT 1 FROM raw_order_reviews r WHERE r.order_id = o.order_id);
