-- review_id values attached to more than one order.
SELECT count(*) AS violations
FROM (
    SELECT review_id
    FROM raw_order_reviews
    GROUP BY review_id
    HAVING count(DISTINCT order_id) > 1
);
