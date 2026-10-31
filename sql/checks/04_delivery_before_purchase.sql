-- Orders delivered to the customer before they were purchased.
SELECT count(*) AS violations
FROM raw_orders
WHERE order_delivered_customer_date < order_purchase_timestamp;
