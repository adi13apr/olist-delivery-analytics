-- Business question: Which product categories drive revenue, and how
-- concentrated is it (Pareto view)?
-- Grain: one row per product category, ordered by GMV.
-- Metrics:
--   gmv                   sum of order_items.price (freight excluded) for items in orders
--                         that are neither canceled nor unavailable
--   orders                distinct such orders with at least one item in the category
--   gmv_share             category gmv / total gmv
--   cumulative_gmv_share  running SUM() OVER the categories sorted by gmv descending
-- Category names come from stg_products.category: English where a translation
-- exists, the Portuguese name for the 2 categories without one
-- (category_name_source = 'portuguese_untranslated'), and 'uncategorized' as its
-- own group for products with no category.
-- Threshold: none. GMV is a total, not a rate, so a small category is small, not noisy.
WITH category_gmv AS (
    SELECT
        coalesce(p.category, 'unknown_product') AS category,
        CASE
            WHEN p.product_id IS NULL THEN 'unknown_product'
            WHEN p.product_category_name IS NULL THEN 'uncategorized'
            WHEN p.product_category_name_english IS NULL THEN 'portuguese_untranslated'
            ELSE 'english'
        END AS category_name_source,
        count(DISTINCT o.order_id) AS orders,
        count(*) AS items,
        sum(i.price) AS gmv
    FROM int_orders o
    JOIN stg_order_items i USING (order_id)
    LEFT JOIN stg_products p USING (product_id)
    WHERE o.is_gmv_order
    GROUP BY ALL
)
SELECT
    row_number() OVER (ORDER BY gmv DESC, category) AS gmv_rank,
    category,
    category_name_source,
    orders,
    items,
    round(gmv, 2) AS gmv,
    round(gmv / sum(gmv) OVER (), 4) AS gmv_share,
    round(
        sum(gmv) OVER (ORDER BY gmv DESC, category ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / sum(gmv) OVER (),
        4
    ) AS cumulative_gmv_share
FROM category_gmv
ORDER BY gmv_rank;
