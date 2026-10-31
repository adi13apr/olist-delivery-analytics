-- Payment rows with a value of zero or less.
SELECT count(*) AS violations
FROM raw_order_payments
WHERE payment_value <= 0;
