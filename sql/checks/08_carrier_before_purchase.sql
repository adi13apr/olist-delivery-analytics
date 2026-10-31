-- Orders handed to the carrier before they were purchased.
SELECT count(*) AS violations
FROM raw_orders
WHERE order_delivered_carrier_date < order_purchase_timestamp;
