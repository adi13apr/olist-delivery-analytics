-- Distinct product categories with no English translation.
SELECT count(DISTINCT p.product_category_name) AS violations
FROM raw_products p
WHERE p.product_category_name IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM raw_category_translation t
      WHERE t.product_category_name = p.product_category_name
  );
