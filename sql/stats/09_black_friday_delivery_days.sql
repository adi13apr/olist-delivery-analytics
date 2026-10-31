-- Order-level sample for the Black Friday delivery-days significance test in
-- scripts/significance.py. Not exported: row level.
-- One row per eligible order (stg_orders.is_delivery_metric_eligible) placed in
-- the baseline or event period of int_black_friday_periods.
SELECT
    p.period,
    o.order_id,
    o.delivery_days
FROM int_black_friday_periods p
JOIN int_orders o
  ON o.order_purchase_timestamp::DATE BETWEEN p.start_date AND p.end_date
WHERE o.is_delivery_metric_eligible
ORDER BY p.period, o.order_id;
