-- Products with no category.
SELECT count(*) AS violations
FROM raw_products
WHERE product_category_name IS NULL;
