-- Orders not in status 'delivered' that still have a customer delivery date.
SELECT count(*) AS violations
FROM raw_orders
WHERE order_status IS DISTINCT FROM 'delivered'
  AND order_delivered_customer_date IS NOT NULL;
