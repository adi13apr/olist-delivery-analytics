-- order_id values that appear on more than one row of raw_orders.
SELECT count(*) AS violations
FROM (
    SELECT order_id
    FROM raw_orders
    GROUP BY order_id
    HAVING count(*) > 1
);
