-- Staging views over the raw_ tables.
-- Nothing is filtered out here: every raw row appears in its staging view.
-- Orders unfit for delivery metrics stay in stg_orders with an exclusion_reason.

-- One row per raw order row. delivery_days, estimated_days and is_late are only
-- filled for orders eligible for delivery metrics (exclusion_reason IS NULL).
CREATE OR REPLACE VIEW stg_orders AS
WITH classified AS (
    SELECT
        *,
        -- First matching rule wins, so each excluded row has exactly one reason.
        CASE
            WHEN count(*) OVER (PARTITION BY order_id) > 1 THEN 'duplicate_order_id'
            WHEN order_status IS DISTINCT FROM 'delivered' THEN 'status_not_delivered'
            WHEN order_purchase_timestamp IS NULL THEN 'missing_purchase_date'
            WHEN order_delivered_customer_date IS NULL THEN 'missing_delivered_date'
            WHEN order_estimated_delivery_date IS NULL THEN 'missing_estimated_date'
            WHEN order_delivered_customer_date < order_purchase_timestamp THEN 'delivered_before_purchase'
        END AS exclusion_reason
    FROM raw_orders
)
SELECT
    order_id,
    customer_id,
    order_status,
    order_purchase_timestamp,
    order_approved_at,
    order_delivered_carrier_date,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    exclusion_reason,
    exclusion_reason IS NULL AS is_delivery_metric_eligible,
    -- Fractional days, rounded to 2 decimals.
    CASE WHEN exclusion_reason IS NULL THEN
        round(date_diff('second', order_purchase_timestamp, order_delivered_customer_date) / 86400.0, 2)
    END AS delivery_days,
    CASE WHEN exclusion_reason IS NULL THEN
        round(date_diff('second', order_purchase_timestamp, order_estimated_delivery_date) / 86400.0, 2)
    END AS estimated_days,
    -- Compared by date: the estimated date is always stored at 00:00:00, so a
    -- timestamp comparison would mark every delivery on the promised day as late.
    CASE WHEN exclusion_reason IS NULL THEN
        order_delivered_customer_date::DATE > order_estimated_delivery_date::DATE
    END AS is_late
FROM classified;

-- Every exclusion reason with its order count, including reasons with zero orders.
CREATE OR REPLACE VIEW stg_delivery_exclusions AS
WITH reasons (sort_order, exclusion_reason) AS (
    VALUES
        (1, 'duplicate_order_id'),
        (2, 'status_not_delivered'),
        (3, 'missing_purchase_date'),
        (4, 'missing_delivered_date'),
        (5, 'missing_estimated_date'),
        (6, 'delivered_before_purchase')
)
SELECT
    r.sort_order,
    r.exclusion_reason,
    count(o.order_id) AS orders
FROM reasons r
LEFT JOIN stg_orders o USING (exclusion_reason)
GROUP BY ALL
ORDER BY r.sort_order;

-- raw rows = staging rows = eligible + excluded. is_balanced must always be true.
CREATE OR REPLACE VIEW v_delivery_reconciliation AS
WITH counts AS (
    SELECT
        (SELECT count(*) FROM raw_orders) AS raw_order_rows,
        (SELECT count(*) FROM stg_orders) AS stg_order_rows,
        (SELECT count(*) FROM stg_orders WHERE is_delivery_metric_eligible) AS eligible_orders,
        (SELECT count(*) FROM stg_orders WHERE NOT is_delivery_metric_eligible) AS excluded_orders,
        (SELECT sum(orders) FROM stg_delivery_exclusions) AS excluded_by_reason
)
SELECT
    *,
    raw_order_rows = stg_order_rows
        AND stg_order_rows = eligible_orders + excluded_orders
        AND excluded_orders = excluded_by_reason AS is_balanced
FROM counts;

-- Items whose order_id is missing from raw_orders are kept and flagged;
-- join to orders only where has_matching_order.
CREATE OR REPLACE VIEW stg_order_items AS
SELECT
    i.*,
    EXISTS (SELECT 1 FROM raw_orders o WHERE o.order_id = i.order_id) AS has_matching_order
FROM raw_order_items i;

-- review_id is not unique in the source (one review_id can cover several orders);
-- (review_id, order_id) is the key. is_latest_for_order picks one review per
-- order for order-level analysis.
CREATE OR REPLACE VIEW stg_reviews AS
SELECT
    *,
    count(*) OVER (PARTITION BY order_id) AS reviews_for_order,
    count(*) OVER (PARTITION BY review_id) AS orders_for_review_id,
    row_number() OVER (
        PARTITION BY order_id
        ORDER BY review_answer_timestamp DESC NULLS LAST,
                 review_creation_date DESC NULLS LAST,
                 review_id
    ) = 1 AS is_latest_for_order
FROM raw_order_reviews;

CREATE OR REPLACE VIEW stg_customers AS
SELECT * FROM raw_customers;

CREATE OR REPLACE VIEW stg_sellers AS
SELECT * FROM raw_sellers;

CREATE OR REPLACE VIEW stg_payments AS
SELECT * FROM raw_order_payments;

-- category: English name, else the Portuguese name when no translation exists,
-- else 'uncategorized' when the product has no category.
CREATE OR REPLACE VIEW stg_products AS
SELECT
    p.product_id,
    p.product_category_name,
    t.product_category_name_english,
    coalesce(t.product_category_name_english, p.product_category_name, 'uncategorized') AS category,
    p.product_name_lenght AS product_name_length,
    p.product_description_lenght AS product_description_length,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm
FROM raw_products p
LEFT JOIN raw_category_translation t USING (product_category_name);
