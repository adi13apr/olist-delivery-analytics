import pytest

import checks
import quality_report

# Bad rows planted in tests/fixtures/ for each check. Every count must be > 0,
# so each check is proven to catch the problem it looks for.
EXPECTED_VIOLATIONS = {
    "01_duplicate_order_id": 1,              # o08 appears twice
    "02_orphan_order_items": 1,              # item for o99, which has no order
    "03_delivered_missing_delivery_date": 1,  # o04
    "04_delivery_before_purchase": 1,        # o05
    "05_multiple_reviews_per_order": 1,      # o02 has r02a and r02b
    "06_review_id_reused": 1,                # r10 on o03 and o09
    "07_orders_without_review": 2,           # o07, o34
    "08_carrier_before_purchase": 1,         # o09
    "09_customer_before_carrier": 1,         # o10
    "10_undelivered_with_delivery_date": 1,  # o06 is canceled but has a delivery date
    "11_orders_without_payment": 1,          # o07
    "12_zero_value_payments": 1,             # o04 voucher of 0.00
    "13_undefined_payment_type": 1,          # o05
    "14_products_missing_category": 1,       # p03
    "15_categories_missing_translation": 1,  # pc_gamer
}

EXPECTED_EXCLUSIONS = {
    "duplicate_order_id": 2,  # both o08 rows
    "status_not_delivered": 6,  # o06, o07, o23, o27, o30, o31
    "missing_purchase_date": 1,  # o12
    "missing_delivered_date": 1,  # o04
    "missing_estimated_date": 1,  # o11
    "delivered_before_purchase": 1,  # o05
}

# order_id -> (delivery_days, estimated_days, is_late), worked out by hand.
EXPECTED_METRICS = {
    "o01": (4.25, 8.58, False),
    "o02": (10.5, 7.67, True),
    "o03": (7.25, 6.5, False),  # delivered 18:00 on the estimated date: on time
    "o09": (6.0, 10.58, False),
    "o10": (3.5, 1.58, True),
    # Phase 2 rows: every timestamp is on the hour or half hour, so the values are exact.
    "o20": (5.0, 9.58, False),
    "o21": (4.0, 8.58, False),
    "o22": (6.0, 8.58, False),
    "o24": (8.0, 5.58, True),
    "o25": (7.0, 10.58, False),
    "o26": (9.0, 6.42, True),
    "o28": (12.0, 8.04, True),
    "o29": (6.0, 9.98, False),
    "o32": (5.0, 7.58, False),
    "o33": (3.0, 9.58, False),
    "o34": (10.0, 7.58, True),
}


def test_every_check_has_planted_violations():
    assert set(EXPECTED_VIOLATIONS) == {c.id for c in checks.CHECKS}
    assert all(n > 0 for n in EXPECTED_VIOLATIONS.values())


def test_registry_matches_sql_files():
    files = {p.stem for p in checks.CHECKS_DIR.glob("*.sql")}
    assert files == {c.id for c in checks.CHECKS}


@pytest.mark.parametrize("check", checks.CHECKS, ids=lambda c: c.id)
def test_check_catches_planted_rows(con, check):
    assert checks.run_check(con, check) == EXPECTED_VIOLATIONS[check.id]


def test_exclusions_by_reason(con):
    rows = dict(con.execute("SELECT exclusion_reason, orders FROM stg_delivery_exclusions").fetchall())
    assert rows == EXPECTED_EXCLUSIONS


def test_reconciliation_balances(con):
    raw, eligible, excluded, balanced = con.execute(
        "SELECT raw_order_rows, eligible_orders, excluded_orders, is_balanced FROM v_delivery_reconciliation"
    ).fetchone()
    assert (raw, eligible, excluded, balanced) == (28, 16, 12, True)


def test_delivery_metrics(con):
    rows = con.execute(
        "SELECT order_id, delivery_days, estimated_days, is_late FROM stg_orders "
        "WHERE is_delivery_metric_eligible ORDER BY order_id"
    ).fetchall()
    actual = {r[0]: r[1:] for r in rows}
    assert actual.keys() == EXPECTED_METRICS.keys()
    for order_id, (days, est, late) in EXPECTED_METRICS.items():
        assert actual[order_id] == (pytest.approx(days), pytest.approx(est), late), order_id


def test_excluded_orders_have_no_metrics(con):
    assert con.execute(
        "SELECT count(*) FROM stg_orders WHERE NOT is_delivery_metric_eligible "
        "AND (delivery_days IS NOT NULL OR estimated_days IS NOT NULL OR is_late IS NOT NULL)"
    ).fetchone()[0] == 0


def test_latest_review_per_order(con):
    latest = dict(con.execute(
        "SELECT order_id, review_id FROM stg_reviews WHERE is_latest_for_order"
    ).fetchall())
    assert latest["o02"] == "r02b"
    assert len(latest) == con.execute("SELECT count(DISTINCT order_id) FROM raw_order_reviews").fetchone()[0]


def test_orphan_items_flagged(con):
    orphans = con.execute("SELECT order_id FROM stg_order_items WHERE NOT has_matching_order").fetchall()
    assert orphans == [("o99",)]


def test_product_category_fallbacks(con):
    categories = dict(con.execute("SELECT product_id, category FROM stg_products").fetchall())
    assert categories == {"p01": "perfumery", "p02": "art", "p03": "uncategorized", "p04": "pc_gamer",
                          "p05": "health_beauty"}


def test_report_renders(con):
    report = quality_report.build_report(con)
    assert "| 28 | 16 | 12 | yes |" in report
    for check in checks.CHECKS:
        assert f"`{check.id}`" in report
