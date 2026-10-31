"""Significance test for Black Friday 2017 delivery days (event vs baseline).

Mann-Whitney U rather than Welch's t-test: delivery days are right-skewed with
a long tail of very slow parcels. Welch compares means, which a few extreme
orders can move; Mann-Whitney is rank based, so it asks whether event orders
tend to take longer than baseline orders without being driven by the tail.

The effect size is reported alongside the p-value, because with thousands of
orders a tiny difference is "significant":
    prob_event_slower = U / (n_event * n_baseline), the probability that a random
                        event order took longer than a random baseline order
                        (ties count half); 0.5 means no difference.
    rank_biserial     = 2 * prob_event_slower - 1, from -1 to 1.

This is event analysis, not an A/B test: there is no control group and orders
were not randomised, so a difference cannot be attributed to the promotion.

Usage:
    python scripts/significance.py [--db olist.duckdb]
"""

import argparse
import statistics
import sys
from pathlib import Path

import duckdb
from scipy.stats import mannwhitneyu

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SQL = ROOT / "sql" / "stats" / "09_black_friday_delivery_days.sql"

COLUMNS = [
    "test",
    "n_baseline",
    "n_event",
    "median_baseline_days",
    "median_event_days",
    "median_diff_days",
    "mean_baseline_days",
    "mean_event_days",
    "u_statistic",
    "p_value",
    "prob_event_slower",
    "rank_biserial",
]


def format_p(p):
    """Four decimals, or scientific notation when that would round to 0."""
    return round(p, 4) if p >= 0.0001 else f"{p:.2E}"


def black_friday_test(con):
    """Return (columns, [row]) comparing event vs baseline delivery days."""
    rows = con.execute(SAMPLE_SQL.read_text(encoding="utf-8")).fetchall()
    days = {"baseline": [], "event": []}
    for period, _, delivery_days in rows:
        days[period].append(delivery_days)
    baseline, event = days["baseline"], days["event"]
    if not baseline or not event:
        raise ValueError("Black Friday sample is empty for one of the periods")

    result = mannwhitneyu(event, baseline, alternative="two-sided")
    prob_event_slower = result.statistic / (len(event) * len(baseline))
    row = [
        "mann_whitney_u_two_sided",
        len(baseline),
        len(event),
        round(statistics.median(baseline), 2),
        round(statistics.median(event), 2),
        round(statistics.median(event) - statistics.median(baseline), 2),
        round(statistics.fmean(baseline), 2),
        round(statistics.fmean(event), 2),
        round(float(result.statistic), 1),
        format_p(float(result.pvalue)),
        round(prob_event_slower, 4),
        round(2 * prob_event_slower - 1, 4),
    ]
    return COLUMNS, [row]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=ROOT / "olist.duckdb", type=Path)
    args = parser.parse_args(argv)

    if not args.db.exists():
        print(f"{args.db} not found; run scripts/load.py first.", file=sys.stderr)
        return 1
    with duckdb.connect(str(args.db), read_only=True) as con:
        columns, rows = black_friday_test(con)
    for name, value in zip(columns, rows[0]):
        print(f"  {name:<22} {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
