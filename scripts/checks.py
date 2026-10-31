"""Data-quality checks: one SQL file per check in sql/checks/, plus the decision taken.

Each SQL file returns a single row with one column, `violations`.
"""

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT / "sql" / "checks"


@dataclass(frozen=True)
class Check:
    id: str  # SQL file name without .sql
    title: str
    unit: str
    required: bool  # one of the checks the project brief asked for
    decision: str

    @property
    def path(self):
        return CHECKS_DIR / f"{self.id}.sql"


CHECKS = [
    Check(
        "01_duplicate_order_id", "order_id is unique in orders", "order_ids", True,
        "Every row sharing a duplicated order_id is kept in stg_orders and excluded from "
        "delivery metrics with reason `duplicate_order_id`, since there is no rule for "
        "picking the right copy.",
    ),
    Check(
        "02_orphan_order_items", "order_items with no matching order", "item rows", True,
        "Kept in stg_order_items with `has_matching_order = false`; excluded from any "
        "analysis that joins items to orders.",
    ),
    Check(
        "03_delivered_missing_delivery_date", "Delivered orders missing a delivery date", "orders", True,
        "Kept in stg_orders and excluded from delivery metrics with reason "
        "`missing_delivered_date`; still counted in order volumes.",
    ),
    Check(
        "04_delivery_before_purchase", "Delivery before purchase", "orders", True,
        "Excluded from delivery metrics with reason `delivered_before_purchase` "
        "(a negative delivery time is impossible, so one of the timestamps is wrong).",
    ),
    Check(
        "05_multiple_reviews_per_order", "Multiple reviews per order", "orders", True,
        "All reviews are kept in stg_reviews. Order-level analysis uses the latest review "
        "(`is_latest_for_order`: latest answer timestamp, then latest creation date).",
    ),
    Check(
        "06_review_id_reused", "review_id shared by several orders", "review_ids", False,
        "review_id is not a key in this dataset. (review_id, order_id) is unique and is "
        "used as the key; stg_reviews carries `orders_for_review_id`.",
    ),
    Check(
        "07_orders_without_review", "Orders with no review", "orders", False,
        "Kept. Review metrics are computed over reviewed orders only; a missing review is "
        "never treated as a score.",
    ),
    Check(
        "08_carrier_before_purchase", "Carrier handoff before purchase", "orders", False,
        "Kept and still eligible for delivery metrics, which use only the purchase, "
        "delivered and estimated dates. The carrier date is unreliable for these orders, "
        "so they must be excluded from any future carrier-leg metric.",
    ),
    Check(
        "09_customer_before_carrier", "Delivered to customer before carrier pickup", "orders", False,
        "Kept and still eligible for delivery metrics (purchase-to-delivery is consistent). "
        "Same caveat as above for carrier-leg metrics.",
    ),
    Check(
        "10_undelivered_with_delivery_date", "Non-delivered status with a delivery date", "orders", False,
        "order_status is treated as the source of truth: these orders are excluded from "
        "delivery metrics with reason `status_not_delivered`.",
    ),
    Check(
        "11_orders_without_payment", "Orders with no payment", "orders", False,
        "Kept. Not used by delivery metrics; payment analysis will report it as unpaid.",
    ),
    Check(
        "12_zero_value_payments", "Payments with value <= 0", "payment rows", False,
        "Kept as recorded (vouchers and undefined payments). Not used by delivery metrics.",
    ),
    Check(
        "13_undefined_payment_type", "payment_type = 'not_defined'", "payment rows", False,
        "Kept as recorded. Not used by delivery metrics.",
    ),
    Check(
        "14_products_missing_category", "Products with no category", "products", False,
        "Kept; stg_products labels them `uncategorized`.",
    ),
    Check(
        "15_categories_missing_translation", "Categories with no English translation", "categories", False,
        "Kept; stg_products falls back to the Portuguese category name.",
    ),
]


def run_check(con, check):
    return con.execute(check.path.read_text(encoding="utf-8")).fetchone()[0]


def run_checks(con):
    """Return {check id: violation count} for every registered check."""
    return {check.id: run_check(con, check) for check in CHECKS}
