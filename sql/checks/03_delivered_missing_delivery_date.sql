-- Orders with status 'delivered' but no customer delivery date.
SELECT count(*) AS violations
FROM raw_orders
WHERE order_status = 'delivered'
  AND order_delivered_customer_date IS NULL;
