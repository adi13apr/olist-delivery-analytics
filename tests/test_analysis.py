"""Phase 2 analysis queries, run on the fixture and checked against values worked out by hand.

The real thresholds (30 orders, 10% of the median month) are far above what a
fixture of a few dozen rows can reach, so TEST_THRESHOLDS lowers each one
through its DuckDB variable. The test_default_* tests run with the real
defaults to prove those are what the queries use when nothing is set.

Planted rows (tests/fixtures/, orders o20-o34), all timestamps on the hour or
half hour so stage and delivery times are exact:
  o20  2017-09  only order in the month (sparse first month)
  o34  2018-02  only order in the month (sparse last month); late; no review
  o21, o22, o24          Black Friday baseline, delivered 4, 6, 8 days (o24 late)
  o23  canceled (with an item), baseline
  o30, o31  shipped, baseline; o31 handed to the carrier after its shipping limit
  o25, o26, o28          event, delivered 7, 9, 12 days (o26, o28 late)
  o27  unavailable, no items, event
  o29  2017-11-28 00:30, just after the event window
  o25 is customer c25 with the same customer_unique_id (u21) as o21: a repeat customer
  o24  both items handed to the carrier a day after their shipping limit
  o32  handed to the carrier before payment approval
  o03 (Phase 1) holds the uncategorized product p03
"""

import datetime
import decimal

import duckdb
import pytest

import export

TEST_THRESHOLDS = {
    "min_month_share_of_median": 0.5,  # median month = 2.5 orders, so 1-order months drop out
    "min_state_week_orders": 2,
    "min_state_orders": 2,
    "min_seller_orders": 4,  # s03 has 3 eligible orders: filtered
    "min_category_orders": 2,  # uncategorized has 1 order: filtered
    "min_seller_items": 5,  # s03 has 4 handed-over items: filtered
    "min_seller_state_items": 2,
}

EXPORT_NAMES = [
    "01_monthly_kpis",
    "02_wow_delivery_by_state",
    "03a_sla_breach_by_customer_state",
    "03b_sla_breach_by_seller",
    "04_reviews_late_vs_on_time",
    "05_category_pareto",
    "06_repeat_customers",
    "07a_fill_rate_by_month",
    "07b_fill_rate_by_category",
    "08a_dispatch_sla_by_seller",
    "08b_dispatch_sla_by_seller_state",
    "09_black_friday",
    "09b_black_friday_significance",
    "10_late_root_cause",
]


def connect(db, variables):
    con = duckdb.connect(str(db), read_only=True)
    for name, value in variables.items():
        con.execute(f"SET VARIABLE {name} = {value}")
    return con


def as_dicts(results):
    return {name: [dict(zip(cols, row)) for row in rows] for name, (cols, rows) in results.items()}


@pytest.fixture(scope="module")
def results(fixture_load):
    db, _ = fixture_load
    with connect(db, TEST_THRESHOLDS) as con:
        return as_dicts(export.run_analyses(con))


@pytest.fixture(scope="module")
def default_results(fixture_load):
    db, _ = fixture_load
    with connect(db, {}) as con:
        return as_dicts(export.run_analyses(con))


def plain(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, datetime.date):
        return value.isoformat()
    return value


def assert_rows(actual, expected, abs_tol=1e-9):
    """Compare row by row, in order, on the columns given in `expected`."""
    assert len(actual) == len(expected), [tuple(r.values()) for r in actual]
    for got, want in zip(actual, expected):
        for column, value in want.items():
            got_value = plain(got[column])
            if isinstance(value, float):
                assert got_value == pytest.approx(value, abs=abs_tol), (column, got)
            else:
                assert got_value == value, (column, got)


# --- shared definitions --------------------------------------------------

def months(con):
    return [(m.isoformat()[:7], t, r) for m, t, r in
            con.execute("SELECT month, is_trend_month, exclusion_reason FROM int_months").fetchall()]


def test_trend_months_default_threshold(fixture_load):
    # Month orders: 2017-09 1, 10 3, 11 8, 12 2, 2018-01 10, 02 1 (median 2.5).
    # Default 10% of median = 0.25: every month qualifies.
    with connect(fixture_load[0], {}) as con:
        assert all(t for _, t, _ in months(con))


def test_trend_months_drop_sparse_first_and_last(fixture_load):
    # 50% of 2.5 = 1.25: the two 1-order months fail.
    with connect(fixture_load[0], {"min_month_share_of_median": 0.5}) as con:
        assert months(con) == [
            ("2017-09", False, "below_volume_threshold"),
            ("2017-10", True, None),
            ("2017-11", True, None),
            ("2017-12", True, None),
            ("2018-01", True, None),
            ("2018-02", False, "below_volume_threshold"),
        ]


def test_trend_months_keep_longest_run(fixture_load):
    # 100% of 2.5: December (2) fails too, splitting Oct-Nov (2 months) from Jan (1).
    with connect(fixture_load[0], {"min_month_share_of_median": 1.0}) as con:
        assert months(con) == [
            ("2017-09", False, "below_volume_threshold"),
            ("2017-10", True, None),
            ("2017-11", True, None),
            ("2017-12", False, "below_volume_threshold"),
            ("2018-01", False, "outside_longest_run"),
            ("2018-02", False, "below_volume_threshold"),
        ]


def test_duplicate_order_ids_left_out_of_int_orders(con):
    assert con.execute("SELECT count(*) FROM int_orders WHERE order_id = 'o08'").fetchone()[0] == 0


# --- one test per analysis query ----------------------------------------

def test_01_monthly_kpis(results):
    # Nov: GMV = o24 103.90 + o25 240 + o26/o28/o29/o31 4 x 58.90 + o30 45 = 624.50 over 7
    # GMV orders (o27 unavailable); eligible days 8, 7, 9, 12, 6 -> mean 8.4, median 8;
    # on time o25, o29 = 2/5.
    # Jan: 10 orders (o08 duplicate left out, o12 has no purchase date); GMV orders exclude
    # o06 canceled = 9, including o04/o05/o07/o11 with no items (GMV 0); GMV = o01 178.90 +
    # o02 58.90 + o03 35.50 + o09 120 + o10 58.90 = 452.20; days 4.25, 10.5, 7.25, 6, 3.5.
    assert_rows(results["01_monthly_kpis"], [
        dict(month_start="2017-10-01", orders=3, gmv_orders=2, gmv=165.00, aov=82.50,
             eligible_orders=2, avg_delivery_days=5.0, median_delivery_days=5.0, on_time_rate=1.0),
        dict(month_start="2017-11-01", orders=8, gmv_orders=7, gmv=624.50, aov=89.21,
             eligible_orders=5, avg_delivery_days=8.4, median_delivery_days=8.0, on_time_rate=0.4),
        dict(month_start="2017-12-01", orders=2, gmv_orders=2, gmv=165.00, aov=82.50,
             eligible_orders=2, avg_delivery_days=4.0, median_delivery_days=4.0, on_time_rate=1.0),
        dict(month_start="2018-01-01", orders=10, gmv_orders=9, gmv=452.20, aov=50.24,
             eligible_orders=5, avg_delivery_days=6.3, median_delivery_days=6.0, on_time_rate=0.6),
    ])


def test_02_wow_delivery_by_state(results):
    # Only SP has weeks with >= 2 eligible orders inside the Oct-Jan window:
    # w/c Nov 20 o25 7 + o26 9; Nov 27 o28 12 + o29 6; Dec 4 o32 5 + o33 3;
    # Jan 1 o01 4.25 + o02 10.5 + o03 7.25. Jan 1 follows a gap, so no change.
    flagged = dict(state_max_wow_increase_days=1.0, state_increase_rank=1, is_flagged_state=True)
    assert_rows(results["02_wow_delivery_by_state"], [
        dict(customer_state="SP", week_start="2017-11-20", eligible_orders=2, avg_delivery_days=8.0,
             prev_week_avg_delivery_days=None, wow_change_days=None, **flagged),
        dict(customer_state="SP", week_start="2017-11-27", eligible_orders=2, avg_delivery_days=9.0,
             prev_week_avg_delivery_days=8.0, wow_change_days=1.0, **flagged),
        dict(customer_state="SP", week_start="2017-12-04", eligible_orders=2, avg_delivery_days=4.0,
             prev_week_avg_delivery_days=9.0, wow_change_days=-5.0, **flagged),
        dict(customer_state="SP", week_start="2018-01-01", eligible_orders=3, avg_delivery_days=7.33,
             prev_week_avg_delivery_days=None, wow_change_days=None, **flagged),
    ])


def test_03a_sla_breach_by_customer_state(results):
    # MG: o24, o34 both late. SP: 11 eligible, late o02, o26, o28. RJ, BA, RS have 1 each.
    assert_rows(results["03a_sla_breach_by_customer_state"], [
        dict(customer_state="MG", eligible_orders=2, late_orders=2, late_rate=1.0, breach_rank=1),
        dict(customer_state="SP", eligible_orders=11, late_orders=3, late_rate=0.2727, breach_rank=2),
    ])


def test_03b_sla_breach_by_seller(results):
    # s01: o01 o02 o09 o20 o21 o24 o26 o29 o32 o33, late o02 o24 o26.
    # s02: o01 o03 o10 o25, late o10. o01 counts for both sellers.
    assert_rows(results["03b_sla_breach_by_seller"], [
        dict(seller_id="s01", seller_state="SP", eligible_orders=10, late_orders=3, late_rate=0.3, rank_in_state=1),
        dict(seller_id="s02", seller_state="SP", eligible_orders=4, late_orders=1, late_rate=0.25, rank_in_state=2),
    ])


def test_04_reviews_late_vs_on_time(results):
    # Late: o02 3 (latest review r02b, not r02a's 1), o10 2, o24 2, o26 1, o28 1, o34 none.
    # On time: o01 5, o03 4, o09 5, o20 5, o21 4, o22 5, o25 5, o29 4, o32 5, o33 4.
    assert_rows(results["04_reviews_late_vs_on_time"], [
        dict(delivery_status="late", eligible_orders=6, reviewed_orders=5, orders_without_review=1,
             avg_review_score=1.8, low_score_orders=4, low_score_share=0.8),
        dict(delivery_status="on_time", eligible_orders=10, reviewed_orders=10, orders_without_review=0,
             avg_review_score=4.6, low_score_orders=0, low_score_share=0.0),
    ])


def test_05_category_pareto(results):
    # GMV orders only (o23 canceled excluded, o08 duplicate excluded, so pc_gamer is absent).
    # art 6 x 120 = 720; perfumery 10 x 58.90 = 589; health_beauty 4 x 45 = 180;
    # uncategorized 35.50 (o03). Total 1,524.50.
    assert_rows(results["05_category_pareto"], [
        dict(gmv_rank=1, category="art", category_name_source="english", orders=5, items=6,
             gmv=720.00, gmv_share=0.4723, cumulative_gmv_share=0.4723),
        dict(gmv_rank=2, category="perfumery", category_name_source="english", orders=10, items=10,
             gmv=589.00, gmv_share=0.3864, cumulative_gmv_share=0.8586),
        dict(gmv_rank=3, category="health_beauty", category_name_source="english", orders=4, items=4,
             gmv=180.00, gmv_share=0.1181, cumulative_gmv_share=0.9767),
        dict(gmv_rank=4, category="uncategorized", category_name_source="uncategorized", orders=1, items=1,
             gmv=35.50, gmv_share=0.0233, cumulative_gmv_share=1.0),
    ])


def test_06_repeat_customers(results):
    # 23 GMV orders from 22 customer_unique_ids; u21 placed o21 (120) and o25 (240).
    assert_rows(results["06_repeat_customers"], [
        dict(segment="one_time", customers=21, orders=21, gmv=1164.50, orders_per_customer=1.0,
             customer_share=0.9545, gmv_share=0.7639),
        dict(segment="repeat", customers=1, orders=2, gmv=360.00, orders_per_customer=2.0,
             customer_share=0.0455, gmv_share=0.2361),
    ])


def test_07a_fill_rate_by_month(results):
    # Oct: o23 canceled of 3. Nov: o27 unavailable of 8. Jan: o06 canceled of 10.
    assert_rows(results["07a_fill_rate_by_month"], [
        dict(month_start="2017-10-01", orders=3, canceled_orders=1, unavailable_orders=0,
             canceled_rate=0.3333, unavailable_rate=0.0, not_fulfilled_rate=0.3333),
        dict(month_start="2017-11-01", orders=8, canceled_orders=0, unavailable_orders=1,
             canceled_rate=0.0, unavailable_rate=0.125, not_fulfilled_rate=0.125),
        dict(month_start="2017-12-01", orders=2, canceled_orders=0, unavailable_orders=0,
             canceled_rate=0.0, unavailable_rate=0.0, not_fulfilled_rate=0.0),
        dict(month_start="2018-01-01", orders=10, canceled_orders=1, unavailable_orders=0,
             canceled_rate=0.1, unavailable_rate=0.0, not_fulfilled_rate=0.1),
    ])


def test_07b_fill_rate_by_category(results):
    # No items: o04 o05 o06 (canceled) o07 o11 o12 o27 (unavailable).
    # health_beauty: o22 o23 (canceled) o24 o30 o33. o24 also counts under perfumery.
    assert_rows(results["07b_fill_rate_by_category"], [
        dict(category="(no items recorded)", orders=7, canceled_orders=1, unavailable_orders=1,
             canceled_rate=0.1429, unavailable_rate=0.1429, not_fulfilled_rate=0.2857),
        dict(category="health_beauty", orders=5, canceled_orders=1, unavailable_orders=0,
             canceled_rate=0.2, unavailable_rate=0.0, not_fulfilled_rate=0.2),
        dict(category="perfumery", orders=10, canceled_orders=0, unavailable_orders=0, not_fulfilled_rate=0.0),
        dict(category="art", orders=5, canceled_orders=0, unavailable_orders=0, not_fulfilled_rate=0.0),
    ])


def test_08a_dispatch_sla_by_seller(results):
    # s01: 10 usable items, both o24 items late; o09 (carrier before purchase) excluded.
    # s02: 5 usable items, o31 late; o10 (delivered before carrier pickup) excluded;
    #      o23 never handed over, not counted.
    assert_rows(results["08a_dispatch_sla_by_seller"], [
        dict(seller_id="s01", seller_state="SP", items_handed_over=10, items_dispatched_late=2,
             late_dispatch_rate=0.2, items_excluded_unreliable_carrier_date=1),
        dict(seller_id="s02", seller_state="SP", items_handed_over=5, items_dispatched_late=1,
             late_dispatch_rate=0.2, items_excluded_unreliable_carrier_date=1),
    ])


def test_08b_dispatch_sla_by_seller_state(results):
    # RJ = s03: o22, o28 (late), o30, o34 (late). SP = s01 + s02.
    assert_rows(results["08b_dispatch_sla_by_seller_state"], [
        dict(seller_state="RJ", items_handed_over=4, items_dispatched_late=2,
             late_dispatch_rate=0.5, items_excluded_unreliable_carrier_date=0),
        dict(seller_state="SP", items_handed_over=15, items_dispatched_late=3,
             late_dispatch_rate=0.2, items_excluded_unreliable_carrier_date=2),
    ])


def test_09_black_friday(results):
    # Baseline (28 days): o21 o22 o23(canceled) o24 o30 o31; GMV 120 + 45 + 103.90 + 45 + 58.90
    #   = 372.80 over 5 orders; delivered 4, 6, 8 days, o24 late.
    # Event (4 days): o25 o26 o27(unavailable) o28; GMV 240 + 58.90 + 58.90 = 357.80 over 3;
    #   delivered 7, 9, 12 days, o26 and o28 late. o29 (Nov 28 00:30) is outside both.
    rows = {r["metric"]: r for r in results["09_black_friday"]}
    assert list(rows) == ["days_in_period", "orders", "orders_per_day", "gmv", "gmv_per_day",
                          "gmv_orders", "aov", "eligible_orders", "avg_delivery_days",
                          "median_delivery_days", "late_rate"]
    expected = {
        "days_in_period": (28, 4, -24, -0.8571),
        "orders": (6, 4, -2, -0.3333),
        "orders_per_day": (0.21, 1.0, 0.79, 3.6667),
        "gmv": (372.80, 357.80, -15.0, -0.0402),
        "gmv_per_day": (13.31, 89.45, 76.14, 5.7183),
        "gmv_orders": (5, 3, -2, -0.4),
        "aov": (74.56, 119.27, 44.71, 0.5996),
        "eligible_orders": (3, 3, 0, 0.0),
        "avg_delivery_days": (6.0, 9.33, 3.33, 0.5556),
        "median_delivery_days": (6.0, 9.0, 3.0, 0.5),
        "late_rate": (0.3333, 0.6667, 0.3333, 1.0),
    }
    for metric, (baseline, event, abs_change, pct_change) in expected.items():
        r = rows[metric]
        assert (r["baseline"], r["event"], r["abs_change"], r["pct_change"]) == pytest.approx(
            (baseline, event, abs_change, pct_change)), metric


def test_09b_black_friday_significance(results):
    # Event 7, 9, 12 vs baseline 4, 6, 8. U(event) counts event > baseline pairs:
    # 7 beats 2, 9 and 12 beat 3 each -> U = 8 of 9 pairs. Exact two-sided p for
    # n = 3, 3: U >= 8 in 2 of C(6,3) = 20 rank orders, doubled = 0.2.
    # prob_event_slower = 8/9; rank-biserial = 2 * 8/9 - 1 = 7/9.
    assert_rows(results["09b_black_friday_significance"], [
        dict(test="mann_whitney_u_two_sided", n_baseline=3, n_event=3,
             median_baseline_days=6.0, median_event_days=9.0, median_diff_days=3.0,
             mean_baseline_days=6.0, mean_event_days=9.0 + 1 / 3, u_statistic=8.0,
             p_value=0.2, prob_event_slower=0.8889, rank_biserial=0.7778),
    ], abs_tol=0.005)


def test_10_late_root_cause(results):
    # Stages in days (approval, dispatch, transit). Phase 1 orders:
    #   o01 15min, 22h45m, 3d7h   o02 30min, 25h30m, 9d10h   o03 10min, 19h50m, 6d10h
    # Planted: o20 .5 1 3.5 | o21 .5 1 2.5 | o22 .5 1.5 4 | o24 .5 3.5 4 | o25 .5 1.5 5
    #          o26 1 2 6 | o28 .5 3.5 8 | o29 .5 1 4.5 | o33 .5 .5 2 | o34 .5 2.5 7
    # Not decomposed: o09 carrier before purchase, o10 delivered before carrier,
    # o32 carrier before approval.
    # all/late = o02 o24 o26 o28 o34; all/on_time = o01 o03 o20 o21 o22 o25 o29 o33.
    # SP (flagged in 02): late o02 o26 o28; on time o01 o03 o20 o21 o25 o29 o33 (+ o32 excluded).
    # Unrounded expectations; the query rounds to 2 decimals, hence abs_tol=0.0051.
    no_exclusions = dict(excluded_missing_stage_timestamp=0, excluded_approved_before_purchase=0)
    gap_counts = dict(eligible_orders=None, decomposed_orders=None, excluded_carrier_before_approval=None)
    assert_rows(results["10_late_root_cause"], [
        dict(scope="all", delivery_status="late", eligible_orders=6, decomposed_orders=5, **no_exclusions,
             excluded_carrier_before_purchase=0, excluded_carrier_before_approval=0,
             excluded_delivered_before_carrier=1,
             avg_approval_days=2.5208333 / 5, avg_dispatch_days=12.5625 / 5,
             avg_transit_days=34.4166667 / 5, avg_delivery_days=9.9),
        dict(scope="all", delivery_status="on_time", eligible_orders=10, decomposed_orders=8, **no_exclusions,
             excluded_carrier_before_purchase=1, excluded_carrier_before_approval=1,
             excluded_delivered_before_carrier=0,
             avg_approval_days=3.0173611 / 8, avg_dispatch_days=8.2743056 / 8,
             avg_transit_days=31.2083334 / 8, avg_delivery_days=5.3125),
        dict(scope="all", delivery_status="late_minus_on_time", **gap_counts,
             avg_approval_days=0.1269966, avg_dispatch_days=1.4782118,
             avg_transit_days=2.9822916, avg_delivery_days=4.5875),
        dict(scope="SP", delivery_status="late", eligible_orders=3, decomposed_orders=3, **no_exclusions,
             excluded_carrier_before_approval=0,
             avg_approval_days=1.5208333 / 3, avg_dispatch_days=6.5625 / 3,
             avg_transit_days=23.4166667 / 3, avg_delivery_days=10.5),
        dict(scope="SP", delivery_status="on_time", eligible_orders=8, decomposed_orders=7, **no_exclusions,
             excluded_carrier_before_approval=1,
             avg_approval_days=2.5173611 / 7, avg_dispatch_days=6.7743056 / 7,
             avg_transit_days=27.2083334 / 7, avg_delivery_days=36.5 / 7),
        dict(scope="SP", delivery_status="late_minus_on_time", **gap_counts,
             avg_approval_days=0.1473214, avg_dispatch_days=1.2197421,
             avg_transit_days=3.9186508, avg_delivery_days=5.2857143),
    ], abs_tol=0.0051)


# --- real default thresholds --------------------------------------------

@pytest.mark.parametrize("name", [
    "02_wow_delivery_by_state",
    "03a_sla_breach_by_customer_state",
    "03b_sla_breach_by_seller",
    "07b_fill_rate_by_category",
    "08a_dispatch_sla_by_seller",
    "08b_dispatch_sla_by_seller_state",
])
def test_default_threshold_of_30_filters_every_fixture_group(default_results, name):
    assert default_results[name] == []


def test_default_trend_window_keeps_all_fixture_months(default_results):
    assert [r["month_start"].isoformat() for r in default_results["01_monthly_kpis"]] == [
        "2017-09-01", "2017-10-01", "2017-11-01", "2017-12-01", "2018-01-01", "2018-02-01"]


def test_default_root_cause_has_no_flagged_states(default_results):
    assert {r["scope"] for r in default_results["10_late_root_cause"]} == {"all"}


# --- query conventions and export format --------------------------------

@pytest.mark.parametrize("path", export.analysis_files(), ids=lambda p: p.stem)
def test_query_starts_with_business_question(path):
    assert path.read_text(encoding="utf-8").startswith("-- Business question:")


@pytest.mark.parametrize("path", export.analysis_files(), ids=lambda p: p.stem)
def test_query_has_no_select_star(path):
    code = "\n".join(line.split("--")[0] for line in path.read_text(encoding="utf-8").splitlines())
    tokens = code.replace(",", " , ").split()
    assert "*" not in tokens and not any(t.endswith(".*") for t in tokens)


def test_export_files_are_sheets_friendly(fixture_load, tmp_path):
    with connect(fixture_load[0], TEST_THRESHOLDS) as con:
        written = export.export_all(con, tmp_path)
    assert sorted(written) == [f"{n}.csv" for n in EXPORT_NAMES]
    for name in written:
        data = (tmp_path / name).read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf"), name
        assert b"\r" not in data, name
        data.decode("utf-8")
        header = data.split(b"\n", 1)[0].decode()
        assert header and "index" not in header.split(","), name
    monthly = (tmp_path / "01_monthly_kpis.csv").read_text(encoding="utf-8").splitlines()
    assert monthly[0] == ("month_start,orders,gmv_orders,gmv,aov,eligible_orders,"
                          "avg_delivery_days,median_delivery_days,on_time_rate")
    # gmv is DECIMAL (keeps 2 places); aov and the averages are DOUBLE (no trailing zeros).
    assert monthly[1] == "2017-10-01,3,2,165.00,82.5,2,5,5,1"
    wow = (tmp_path / "02_wow_delivery_by_state.csv").read_text(encoding="utf-8").splitlines()
    assert wow[1] == "SP,2017-11-20,2,8,,,1,1,TRUE"


def test_export_refuses_row_level_output(fixture_load, tmp_path, monkeypatch):
    monkeypatch.setattr(export, "MAX_ROWS", 3)
    with connect(fixture_load[0], TEST_THRESHOLDS) as con, pytest.raises(export.ExportError):
        export.export_all(con, tmp_path)
