-- Orders with more than one review.
SELECT count(*) AS violations
FROM (
    SELECT order_id
    FROM raw_order_reviews
    GROUP BY order_id
    HAVING count(*) > 1
);
