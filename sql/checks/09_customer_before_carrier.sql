-- Orders delivered to the customer before the carrier picked them up.
SELECT count(*) AS violations
FROM raw_orders
WHERE order_delivered_customer_date < order_delivered_carrier_date;
