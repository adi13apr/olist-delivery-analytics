-- Payment rows with payment_type 'not_defined'.
SELECT count(*) AS violations
FROM raw_order_payments
WHERE payment_type = 'not_defined';
